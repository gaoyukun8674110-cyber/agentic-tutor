import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.materials import router as materials_router
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.materials import HashEmbeddingProvider, MaterialService
from tests.pgvector_helpers import make_pgvector_session_factory


class MaterialsApiTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.SessionLocal = make_pgvector_session_factory()
        self.db = self.SessionLocal()
        self.tmpdir = tempfile.TemporaryDirectory()

        self.previous_upload_dir = settings.RAG_UPLOAD_DIR
        self.previous_max_upload_size_mb = settings.MAX_UPLOAD_SIZE_MB
        settings.RAG_UPLOAD_DIR = self.tmpdir.name
        settings.MAX_UPLOAD_SIZE_MB = 1

        self.db.add(
            User(
                id=1,
                username="alice",
                email=None,
                password_hash="hash",
                is_active=True,
                created_at="now",
                updated_at="now",
            )
        )
        self.db.commit()

        app = FastAPI()

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: User(
            id=1,
            username="alice",
            email=None,
            is_active=True,
            created_at="now",
            updated_at="now",
        )
        app.include_router(materials_router)
        self.client = TestClient(app)

    def tearDown(self):
        settings.RAG_UPLOAD_DIR = self.previous_upload_dir
        settings.MAX_UPLOAD_SIZE_MB = self.previous_max_upload_size_mb
        self.db.close()
        self.engine.dispose()
        self.tmpdir.cleanup()

    def _material_service(self, db):
        return MaterialService(
            db,
            embedding_provider=HashEmbeddingProvider(dimensions=settings.RAG_VECTOR_DIM),
            upload_dir=Path(self.tmpdir.name),
        )

    def test_upload_list_and_search_materials(self):
        with patch("app.api.materials.MaterialService", side_effect=self._material_service):
            upload_response = self.client.post(
                "/api/materials/upload",
                params={"user_id": "bob"},
                files={"file": ("probability.txt", b"Bayes theorem uses posterior probability.", "text/plain")},
            )

            self.assertEqual(upload_response.status_code, 200)
            material = upload_response.json()
            self.assertEqual(material["filename"], "probability.txt")
            self.assertEqual(material["status"], "pending")
            self.assertEqual(material["embedding_mode"], "hash")

            list_response = self.client.get("/api/materials", params={"user_id": "bob"})
            self.assertEqual(list_response.status_code, 200)
            listed_material = list_response.json()["materials"][0]
            self.assertEqual(listed_material["id"], material["id"])
            self.assertEqual(listed_material["status"], "ready")
            self.assertGreaterEqual(listed_material["chunk_count"], 1)
            self.assertEqual(listed_material["embedding_mode"], "hash")

            search_response = self.client.post(
                "/api/materials/search",
                params={"user_id": "bob"},
                json={"query": "posterior probability", "top_k": 2},
            )
            self.assertEqual(search_response.status_code, 200)
            search_payload = search_response.json()
            self.assertEqual(search_payload["embedding_mode"], "hash")
            results = search_payload["chunks"]
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["material_id"], material["id"])
            self.assertIn("posterior probability", results[0]["content"])
            self.assertEqual(results[0]["embedding_mode"], "hash")

    def test_upload_rejects_oversized_file(self):
        response = self.client.post(
            "/api/materials/upload",
            files={"file": ("large.txt", b"x" * (2 * 1024 * 1024), "text/plain")},
        )

        self.assertEqual(response.status_code, 413)

    def test_upload_rejects_mismatched_pdf_signature(self):
        response = self.client.post(
            "/api/materials/upload",
            files={"file": ("notes.pdf", b"not really a pdf", "application/pdf")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("PDF", response.json()["detail"]["user_message"])


if __name__ == "__main__":
    unittest.main()
