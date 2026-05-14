import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.config import settings
from app.database import Base, get_db
from app.api.materials import router as materials_router
from app.models.user import User


class MaterialsApiTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.SessionLocal()
        self.tmpdir = tempfile.TemporaryDirectory()

        self.previous_upload_dir = settings.RAG_UPLOAD_DIR
        self.previous_openai_key = settings.OPENAI_API_KEY
        self.previous_max_upload_size_mb = settings.MAX_UPLOAD_SIZE_MB
        settings.RAG_UPLOAD_DIR = self.tmpdir.name
        settings.OPENAI_API_KEY = ""
        settings.MAX_UPLOAD_SIZE_MB = 1

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
        settings.OPENAI_API_KEY = self.previous_openai_key
        settings.MAX_UPLOAD_SIZE_MB = self.previous_max_upload_size_mb
        self.db.close()
        self.tmpdir.cleanup()

    def test_upload_list_and_search_materials(self):
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
