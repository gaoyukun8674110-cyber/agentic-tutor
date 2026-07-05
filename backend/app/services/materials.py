"""Study material ingestion, text extraction, chunking, and retrieval."""

from __future__ import annotations

import hashlib
import html.parser
import json
import math
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from xml.etree import ElementTree

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import settings
from app.models.materials import StudyMaterial, StudyMaterialChunk
from app.services.vector_store import make_vector_store

SUPPORTED_EXTENSIONS = {".txt", ".md", ".docx", ".pdf", ".epub"}
WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class _HtmlTextExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return "\n".join(self.parts)


def normalize_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def extract_text_from_file_bytes(filename: str, content: bytes, content_type: str | None = None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported material file type: {suffix or 'unknown'}")

    if suffix in {".txt", ".md"}:
        return normalize_text(content.decode("utf-8", errors="replace"))
    if suffix == ".docx":
        return _extract_docx_text(content)
    if suffix == ".epub":
        return _extract_epub_text(content)
    if suffix == ".pdf":
        return _extract_pdf_text(content)
    raise ValueError(f"Unsupported material file type: {suffix}")


def _extract_docx_text(content: bytes) -> str:
    with zipfile.ZipFile(PathLikeBytes(content)) as archive:
        document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    texts = [node.text for node in root.iter() if node.tag.endswith("}t") and node.text and node.text.strip()]
    extracted = normalize_text("\n".join(texts))
    if not extracted:
        raise ValueError("No readable text found in DOCX file")
    return extracted


def _extract_epub_text(content: bytes) -> str:
    parts = []
    with zipfile.ZipFile(PathLikeBytes(content)) as archive:
        for name in sorted(archive.namelist()):
            if not name.lower().endswith((".html", ".xhtml", ".htm")):
                continue
            parser = _HtmlTextExtractor()
            parser.feed(archive.read(name).decode("utf-8", errors="replace"))
            text = parser.text()
            if text:
                parts.append(text)
    extracted = normalize_text("\n\n".join(parts))
    if not extracted:
        raise ValueError("No readable text found in EPUB file")
    return extracted


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise ValueError("PDF support requires the pypdf package") from error

    reader = PdfReader(PathLikeBytes(content))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[page {index}]\n{text.strip()}")
    extracted = normalize_text("\n\n".join(pages))
    if not extracted:
        raise ValueError("No readable text found in PDF file; OCR is not supported in RAG v1")
    return extracted


class PathLikeBytes:
    """Small file-like adapter accepted by zipfile and pypdf."""

    def __init__(self, content: bytes):
        import io

        self._buffer = io.BytesIO(content)

    def read(self, *args):
        return self._buffer.read(*args)

    def seek(self, *args):
        return self._buffer.seek(*args)

    def tell(self):
        return self._buffer.tell()

    def seekable(self):
        return True


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[dict[str, Any]]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    chunk_size = max(10, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size // 2))

    chunks = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = max(
                normalized.rfind("\n", start, end),
                normalized.rfind("。", start, end),
                normalized.rfind(".", start, end),
            )
            if boundary > start + chunk_size // 2:
                end = boundary + 1
        content = normalized[start:end].strip()
        if content:
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "content": content,
                    "start_char": start,
                    "end_char": end,
                }
            )
        if end >= len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


class HashEmbeddingProvider:
    """Deterministic local embedding fallback for tests and no-key development."""

    def __init__(self, dimensions: int | None = None):
        configured_dimensions = settings.RAG_EMBEDDING_DIM if dimensions is None else dimensions
        self.dimensions = max(8, configured_dimensions)
        self.mode = "hash"

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = WORD_RE.findall(text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        return normalize_vector(vector)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mode = "openai"

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(model=self.model, input=text, timeout=60)
        return [float(value) for value in response.data[0].embedding]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(model=self.model, input=texts, timeout=60)
        return [[float(value) for value in item.embedding] for item in response.data]


def default_embedding_provider() -> EmbeddingProvider:
    if settings.OPENAI_API_KEY:
        return OpenAIEmbeddingProvider(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            model=settings.RAG_EMBEDDING_MODEL,
        )
    return HashEmbeddingProvider(dimensions=settings.RAG_EMBEDDING_DIM)


def normalize_vector(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [round(value / magnitude, 8) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False))


class MaterialService:
    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider | None = None,
        upload_dir: Path | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self.db = db
        self.embedding_provider = embedding_provider or default_embedding_provider()
        self.upload_dir = upload_dir or Path(settings.RAG_UPLOAD_DIR)
        self.chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.RAG_CHUNK_OVERLAP
        self.vector_store = make_vector_store(self.db)

    @property
    def embedding_mode(self) -> str:
        return str(getattr(self.embedding_provider, "mode", "hash"))

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        embed_batch = getattr(self.embedding_provider, "embed_batch", None)
        if callable(embed_batch):
            return [normalize_vector(vector) for vector in embed_batch(texts)]
        return [normalize_vector(self.embedding_provider.embed(text)) for text in texts]

    def create_material_from_bytes(
        self,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        extracted_text = extract_text_from_file_bytes(filename, content, content_type)
        chunks = chunk_text(extracted_text, chunk_size=self.chunk_size, overlap=self.chunk_overlap)
        if not chunks:
            raise ValueError("No searchable text chunks could be created from this material")

        now = datetime.now().isoformat()
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(content).hexdigest()[:16]
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).name or "material").strip("._") or "material"
        storage_name = f"{digest}-{safe_name}"
        storage_path = self.upload_dir / storage_name
        storage_path.write_bytes(content)

        material = StudyMaterial(
            user_id=user_id,
            filename=Path(filename).name or "material",
            file_type=Path(filename).suffix.lower().lstrip("."),
            content_type=content_type,
            storage_path=str(storage_path),
            status="ready",
            char_count=len(extracted_text),
            chunk_count=len(chunks),
            created_at=now,
            updated_at=now,
        )
        self.db.add(material)
        self.db.flush()

        embeddings = self._embed_texts([chunk["content"] for chunk in chunks])
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            self.db.add(
                StudyMaterialChunk(
                    material_id=material.id,
                    chunk_index=chunk["chunk_index"],
                    content=chunk["content"],
                    source_label=f"{material.filename} · chunk {chunk['chunk_index'] + 1}",
                    embedding_json=json.dumps(embedding),
                    created_at=now,
                )
            )

        self.db.flush()
        chunk_ids = [
            int(chunk_id)
            for (chunk_id,) in self.db.query(StudyMaterialChunk.id)
            .filter(StudyMaterialChunk.material_id == material.id)
            .all()
        ]
        self.vector_store.sync_chunks(self.db, chunk_ids)
        self.db.commit()
        self.db.refresh(material)
        return self._material_payload(material)

    def create_pending_material_from_bytes(
        self,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        extracted_text = extract_text_from_file_bytes(filename, content, content_type)
        chunks = chunk_text(extracted_text, chunk_size=self.chunk_size, overlap=self.chunk_overlap)
        if not chunks:
            raise ValueError("No searchable text chunks could be created from this material")

        now = datetime.now().isoformat()
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(content).hexdigest()[:16]
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).name or "material").strip("._") or "material"
        storage_name = f"{digest}-{safe_name}"
        storage_path = self.upload_dir / storage_name
        storage_path.write_bytes(content)

        material = StudyMaterial(
            user_id=user_id,
            filename=Path(filename).name or "material",
            file_type=Path(filename).suffix.lower().lstrip("."),
            content_type=content_type,
            storage_path=str(storage_path),
            status="pending",
            char_count=len(extracted_text),
            chunk_count=0,
            created_at=now,
            updated_at=now,
        )
        self.db.add(material)
        self.db.commit()
        self.db.refresh(material)
        return self._material_payload(material)

    def fill_material_embeddings(self, material_id: int) -> dict[str, Any]:
        material = self.db.query(StudyMaterial).filter(StudyMaterial.id == material_id).one_or_none()
        if material is None:
            raise ValueError("Material not found")

        try:
            content = Path(material.storage_path).read_bytes()
            extracted_text = extract_text_from_file_bytes(material.filename, content, material.content_type)
            chunks = chunk_text(extracted_text, chunk_size=self.chunk_size, overlap=self.chunk_overlap)
            now = datetime.now().isoformat()
            self.db.query(StudyMaterialChunk).filter(StudyMaterialChunk.material_id == material.id).delete()
            embeddings = self._embed_texts([chunk["content"] for chunk in chunks])
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                self.db.add(
                    StudyMaterialChunk(
                        material_id=material.id,
                        chunk_index=chunk["chunk_index"],
                        content=chunk["content"],
                        source_label=f"{material.filename} chunk {chunk['chunk_index'] + 1}",
                        embedding_json=json.dumps(embedding),
                        created_at=now,
                    )
                )
            material.status = "ready"
            material.error = None
            material.char_count = len(extracted_text)
            material.chunk_count = len(chunks)
            material.updated_at = now
            self.db.flush()
            chunk_ids = [
                int(chunk_id)
                for (chunk_id,) in self.db.query(StudyMaterialChunk.id)
                .filter(StudyMaterialChunk.material_id == material.id)
                .all()
            ]
            self.vector_store.sync_chunks(self.db, chunk_ids)
            self.db.commit()
            self.db.refresh(material)
            return self._material_payload(material)
        except Exception as error:
            material.status = "failed"
            material.error = str(error)
            material.updated_at = datetime.now().isoformat()
            self.db.commit()
            raise

    def list_materials(self, user_id: str | None = None) -> list[dict[str, Any]]:
        query = self.db.query(StudyMaterial)
        if user_id:
            query = query.filter(self._user_scope_filter(user_id))
        return [
            self._material_payload(material)
            for material in query.order_by(StudyMaterial.updated_at.desc(), StudyMaterial.id.desc()).all()
        ]

    def search_materials(
        self,
        query: str,
        user_id: str | None = None,
        material_ids: list[int] | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        cleaned_query = query.strip()
        if not cleaned_query:
            return []
        top_k = max(1, min(top_k or settings.RAG_TOP_K, 10))
        query_vector = normalize_vector(self.embedding_provider.embed(cleaned_query))
        chunk_scores = self.vector_store.search(
            self.db,
            query_vector=query_vector,
            top_k=top_k,
            user_id=user_id,
            material_ids=set(material_ids) if material_ids else None,
        )
        if not chunk_scores:
            return []

        score_by_chunk_id = {chunk_id: score for chunk_id, score in chunk_scores}
        ordered_chunk_ids = [chunk_id for chunk_id, _score in chunk_scores]
        chunks = (
            self.db.query(StudyMaterialChunk)
            .join(StudyMaterial)
            .filter(StudyMaterial.status == "ready", StudyMaterialChunk.id.in_(ordered_chunk_ids))
            .all()
        )
        chunk_by_id = {chunk.id: chunk for chunk in chunks}
        return [
            {
                "chunk_id": chunk_by_id[chunk_id].id,
                "material_id": chunk_by_id[chunk_id].material_id,
                "filename": chunk_by_id[chunk_id].material.filename,
                "source_label": chunk_by_id[chunk_id].source_label,
                "content": chunk_by_id[chunk_id].content,
                "score": score_by_chunk_id[chunk_id],
                "embedding_mode": self.embedding_mode,
            }
            for chunk_id in ordered_chunk_ids
            if chunk_id in chunk_by_id
        ]

    def _user_scope_filter(self, user_id: str):
        return StudyMaterial.user_id == user_id

    def _material_payload(self, material: StudyMaterial) -> dict[str, Any]:
        return {
            "id": material.id,
            "user_id": material.user_id,
            "filename": material.filename,
            "file_type": material.file_type,
            "content_type": material.content_type,
            "status": material.status,
            "error": material.error,
            "char_count": material.char_count,
            "chunk_count": material.chunk_count,
            "created_at": material.created_at,
            "updated_at": material.updated_at,
            "embedding_mode": self.embedding_mode,
        }
