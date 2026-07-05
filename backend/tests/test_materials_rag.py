import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app.models.materials import StudyMaterial, StudyMaterialChunk
from app.services.materials import (
    HashEmbeddingProvider,
    MaterialService,
    chunk_text,
    extract_text_from_file_bytes,
)


def build_docx_bytes(paragraphs):
    document_xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        "<w:body>"
        + "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
        + "</w:body></w:document>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def build_epub_bytes(chapters):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        for index, chapter in enumerate(chapters, start=1):
            archive.writestr(
                f"OEBPS/chapter{index}.xhtml",
                f"<html><body><h1>Chapter {index}</h1><p>{chapter}</p></body></html>",
            )
    return output.getvalue()


def build_pdf_bytes(text):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    stream = DecodedStreamObject()
    escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream.set_data(f"BT /F1 12 Tf 10 100 Td ({escaped_text}) Tj ET".encode())
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    page[NameObject("/Contents")] = stream
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class MaterialRagTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def test_extract_text_supports_txt_markdown_docx_pdf_and_epub(self):
        self.assertIn(
            "Bayes theorem",
            extract_text_from_file_bytes("notes.txt", b"Bayes theorem uses priors.", "text/plain"),
        )
        self.assertIn(
            "gradient descent",
            extract_text_from_file_bytes("lesson.md", b"# Lesson\n\nGradient descent", "text/markdown").lower(),
        )
        self.assertIn(
            "Posterior probability",
            extract_text_from_file_bytes(
                "chapter.docx",
                build_docx_bytes(["Posterior probability", "Prior probability"]),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        )
        self.assertIn(
            "industrial defect",
            extract_text_from_file_bytes(
                "book.epub",
                build_epub_bytes(["industrial defect segmentation"]),
                "application/epub+zip",
            ),
        )
        self.assertIn(
            "posterior probability",
            extract_text_from_file_bytes(
                "paper.pdf",
                build_pdf_bytes("Bayes PDF posterior probability"),
                "application/pdf",
            ),
        )

    def test_chunk_text_preserves_source_order_and_limits_size(self):
        text = "alpha beta gamma delta epsilon zeta"

        chunks = chunk_text(text, chunk_size=18, overlap=6)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["chunk_index"], 0)
        self.assertLessEqual(len(chunks[0]["content"]), 18)
        self.assertIn("alpha", chunks[0]["content"])

    def test_default_hash_embedding_uses_configured_pgvector_dimension(self):
        self.assertEqual(getattr(settings, "RAG_EMBEDDING_DIM", None), 1536)

        provider = HashEmbeddingProvider()

        self.assertEqual(provider.dimensions, settings.RAG_EMBEDDING_DIM)
        self.assertEqual(len(provider.embed("posterior probability")), settings.RAG_EMBEDDING_DIM)

    def test_material_service_uploads_chunks_and_searches_relevant_context(self):
        db = self.SessionLocal()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                service = MaterialService(
                    db,
                    embedding_provider=HashEmbeddingProvider(dimensions=32),
                    upload_dir=Path(tmpdir),
                    chunk_size=120,
                    chunk_overlap=20,
                )
                material = service.create_material_from_bytes(
                    filename="probability-notes.txt",
                    content=b"Bayes theorem connects prior probability, likelihood, and posterior probability.",
                    content_type="text/plain",
                    user_id="learner-1",
                )

                results = service.search_materials(
                    query="posterior prior probability",
                    user_id="learner-1",
                    top_k=3,
                )

                legacy_index_name = ".vector" + "-index.json"
                self.assertFalse((Path(tmpdir) / legacy_index_name).exists())

            self.assertEqual(material["filename"], "probability-notes.txt")
            self.assertEqual(material["status"], "ready")
            self.assertGreaterEqual(material["chunk_count"], 1)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["material_id"], material["id"])
            self.assertIn("posterior probability", results[0]["content"])
            self.assertGreater(results[0]["score"], 0)
        finally:
            db.close()

    def test_bruteforce_vector_store_orders_and_filters_candidates(self):
        from app.services.vector_store import BruteForceVectorStore

        db = self.SessionLocal()
        try:
            material_one = StudyMaterial(
                user_id="alice",
                filename="alice-ready.txt",
                file_type="txt",
                content_type="text/plain",
                storage_path="alice-ready.txt",
                status="ready",
                char_count=10,
                chunk_count=2,
                created_at="now",
                updated_at="now",
            )
            material_two = StudyMaterial(
                user_id="alice",
                filename="alice-other.txt",
                file_type="txt",
                content_type="text/plain",
                storage_path="alice-other.txt",
                status="ready",
                char_count=10,
                chunk_count=1,
                created_at="now",
                updated_at="now",
            )
            material_bob = StudyMaterial(
                user_id="bob",
                filename="bob-ready.txt",
                file_type="txt",
                content_type="text/plain",
                storage_path="bob-ready.txt",
                status="ready",
                char_count=10,
                chunk_count=1,
                created_at="now",
                updated_at="now",
            )
            material_pending = StudyMaterial(
                user_id="alice",
                filename="alice-pending.txt",
                file_type="txt",
                content_type="text/plain",
                storage_path="alice-pending.txt",
                status="pending",
                char_count=10,
                chunk_count=1,
                created_at="now",
                updated_at="now",
            )
            db.add_all([material_one, material_two, material_bob, material_pending])
            db.flush()
            db.add_all(
                [
                    StudyMaterialChunk(
                        material_id=material_one.id,
                        chunk_index=0,
                        content="best match",
                        source_label="best match",
                        embedding_json="[1.0, 0.0, 0.0]",
                        created_at="now",
                    ),
                    StudyMaterialChunk(
                        material_id=material_one.id,
                        chunk_index=1,
                        content="second match",
                        source_label="second match",
                        embedding_json="[0.8, 0.6, 0.0]",
                        created_at="now",
                    ),
                    StudyMaterialChunk(
                        material_id=material_two.id,
                        chunk_index=0,
                        content="filtered material",
                        source_label="filtered material",
                        embedding_json="[0.0, 1.0, 0.0]",
                        created_at="now",
                    ),
                    StudyMaterialChunk(
                        material_id=material_bob.id,
                        chunk_index=0,
                        content="wrong user",
                        source_label="wrong user",
                        embedding_json="[1.0, 0.0, 0.0]",
                        created_at="now",
                    ),
                    StudyMaterialChunk(
                        material_id=material_pending.id,
                        chunk_index=0,
                        content="not ready",
                        source_label="not ready",
                        embedding_json="[1.0, 0.0, 0.0]",
                        created_at="now",
                    ),
                ]
            )
            db.commit()

            store = BruteForceVectorStore()

            results = store.search(
                db,
                query_vector=[1.0, 0.0, 0.0],
                top_k=5,
                user_id="alice",
                material_ids={material_one.id},
            )

            self.assertEqual([score for _chunk_id, score in results], [1.0, 0.8])
            self.assertEqual(len(results), 2)
        finally:
            db.close()

    def test_vector_store_factory_uses_bruteforce_for_sqlite(self):
        from app.services.vector_store import BruteForceVectorStore, make_vector_store

        db = self.SessionLocal()
        try:
            self.assertIsInstance(make_vector_store(db), BruteForceVectorStore)
        finally:
            db.close()

    def test_material_search_uses_similarity_store_instead_of_recent_chunk_window(self):
        db = self.SessionLocal()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                service = MaterialService(
                    db,
                    embedding_provider=HashEmbeddingProvider(dimensions=48),
                    upload_dir=Path(tmpdir),
                    chunk_size=200,
                    chunk_overlap=20,
                )
                older_material = service.create_material_from_bytes(
                    filename="older-probability.txt",
                    content=b"Posterior probability updates a prior after observing evidence in Bayes theorem.",
                    content_type="text/plain",
                    user_id="learner-1",
                )
                service.create_material_from_bytes(
                    filename="recent-geometry.txt",
                    content=b"Triangles, circles, and trapezoids are geometry topics.",
                    content_type="text/plain",
                    user_id="learner-1",
                )
                service.create_material_from_bytes(
                    filename="recent-history.txt",
                    content=b"Ancient dynasties and empires shaped world history.",
                    content_type="text/plain",
                    user_id="learner-1",
                )
                service.create_material_from_bytes(
                    filename="recent-biology.txt",
                    content=b"Cell membranes and mitochondria are biology concepts.",
                    content_type="text/plain",
                    user_id="learner-1",
                )

                results = service.search_materials(
                    query="How does posterior probability update a prior?",
                    user_id="learner-1",
                    top_k=2,
                )

            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0]["material_id"], older_material["id"])
            self.assertIn("Posterior probability", results[0]["content"])
        finally:
            db.close()

    def test_material_search_honors_material_id_filters_with_similarity_store(self):
        db = self.SessionLocal()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                service = MaterialService(
                    db,
                    embedding_provider=HashEmbeddingProvider(dimensions=48),
                    upload_dir=Path(tmpdir),
                    chunk_size=200,
                    chunk_overlap=20,
                )
                bayes_material = service.create_material_from_bytes(
                    filename="bayes.txt",
                    content=b"Posterior probability is central to Bayes theorem.",
                    content_type="text/plain",
                    user_id="learner-1",
                )
                algebra_material = service.create_material_from_bytes(
                    filename="algebra.txt",
                    content=b"Linear equations and variables belong to algebra.",
                    content_type="text/plain",
                    user_id="learner-1",
                )

                filtered_results = service.search_materials(
                    query="posterior probability",
                    user_id="learner-1",
                    material_ids=[algebra_material["id"]],
                    top_k=2,
                )
                included_results = service.search_materials(
                    query="posterior probability",
                    user_id="learner-1",
                    material_ids=[bayes_material["id"]],
                    top_k=2,
                )

            self.assertTrue(all(result["material_id"] == algebra_material["id"] for result in filtered_results))
            self.assertEqual(len(included_results), 1)
            self.assertEqual(included_results[0]["material_id"], bayes_material["id"])
        finally:
            db.close()

    def test_material_search_is_scoped_to_current_user(self):
        db = self.SessionLocal()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                service = MaterialService(
                    db,
                    embedding_provider=HashEmbeddingProvider(dimensions=48),
                    upload_dir=Path(tmpdir),
                    chunk_size=200,
                    chunk_overlap=20,
                )
                alice_material = service.create_material_from_bytes(
                    filename="alice-statistics.txt",
                    content=b"Bayes theorem uses posterior probability and prior probability.",
                    content_type="text/plain",
                    user_id="alice",
                )
                service.create_material_from_bytes(
                    filename="bob-statistics.txt",
                    content=b"Bob also studies posterior probability.",
                    content_type="text/plain",
                    user_id="bob",
                )

                listed = service.list_materials(user_id="alice")
                results = service.search_materials(
                    query="posterior probability",
                    user_id="alice",
                    top_k=2,
                )

            self.assertEqual([item["id"] for item in listed], [alice_material["id"]])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["material_id"], alice_material["id"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
