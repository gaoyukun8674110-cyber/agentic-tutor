import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.config import settings
from app.services.materials import (
    HashEmbeddingProvider,
    MaterialService,
    chunk_text,
    extract_text_from_file_bytes,
)
from tests.auth_helpers import create_test_user
from tests.pgvector_helpers import make_pgvector_session_factory


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
        self.engine, self.SessionLocal = make_pgvector_session_factory()

    def tearDown(self):
        self.engine.dispose()

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

    def test_material_service_uploads_chunks_and_searches_relevant_context(self):
        db = self.SessionLocal()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                service = MaterialService(
                    db,
                    embedding_provider=HashEmbeddingProvider(dimensions=settings.RAG_VECTOR_DIM),
                    upload_dir=Path(tmpdir),
                    chunk_size=120,
                    chunk_overlap=20,
                )
                create_test_user(db, username="learner-1")
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

            self.assertEqual(material["filename"], "probability-notes.txt")
            self.assertEqual(material["status"], "ready")
            self.assertGreaterEqual(material["chunk_count"], 1)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["material_id"], material["id"])
            self.assertIn("posterior probability", results[0]["content"])
            self.assertGreater(results[0]["score"], 0)
        finally:
            db.close()

    def test_material_search_uses_database_similarity_instead_of_recent_chunk_window(self):
        db = self.SessionLocal()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                service = MaterialService(
                    db,
                    embedding_provider=HashEmbeddingProvider(dimensions=settings.RAG_VECTOR_DIM),
                    upload_dir=Path(tmpdir),
                    chunk_size=200,
                    chunk_overlap=20,
                )
                create_test_user(db, username="learner-1")
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

    def test_material_search_honors_material_id_filters_with_database_similarity(self):
        db = self.SessionLocal()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                service = MaterialService(
                    db,
                    embedding_provider=HashEmbeddingProvider(dimensions=settings.RAG_VECTOR_DIM),
                    upload_dir=Path(tmpdir),
                    chunk_size=200,
                    chunk_overlap=20,
                )
                create_test_user(db, username="learner-1")
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
                    embedding_provider=HashEmbeddingProvider(dimensions=settings.RAG_VECTOR_DIM),
                    upload_dir=Path(tmpdir),
                    chunk_size=200,
                    chunk_overlap=20,
                )
                create_test_user(db, username="alice")
                create_test_user(db, username="bob")
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
