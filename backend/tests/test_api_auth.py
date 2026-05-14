import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.llm import router as llm_router
from app.models.user import User


def fake_user() -> User:
    return User(id=1, username="alice", email=None, is_active=True, created_at="now", updated_at="now")


class ApiAuthTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.dependency_overrides[get_current_user] = fake_user
        app.include_router(llm_router)
        self.client = TestClient(app)

    def test_api_requires_bearer_access_token(self):
        app = FastAPI()
        app.include_router(llm_router)
        client = TestClient(app)

        response = client.get("/api/llm/providers")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "unauthorized")
        self.assertEqual(response.json()["detail"]["user_message"], "Missing access token")

    def test_api_rejects_invalid_bearer_token(self):
        app = FastAPI()
        app.include_router(llm_router)
        client = TestClient(app)

        response = client.get("/api/llm/providers", headers={"Authorization": "Bearer wrong"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "invalid_token")

    def test_api_accepts_authenticated_user_dependency(self):
        response = self.client.get("/api/llm/providers")

        self.assertEqual(response.status_code, 200)
        self.assertIn("providers", response.json())

    def test_provider_metadata_reuses_app_scoped_llm_service(self):
        instances = []

        class FakeLLMService:
            def __init__(self):
                instances.append(self)

            def get_provider_metadata(self):
                return {"providers": []}

        app = FastAPI()
        app.dependency_overrides[get_current_user] = fake_user
        app.include_router(llm_router)

        with patch("app.api.llm.LLMService", FakeLLMService):
            client = TestClient(app)
            response_one = client.get("/api/llm/providers")
            response_two = client.get("/api/llm/providers")

        self.assertEqual(response_one.status_code, 200)
        self.assertEqual(response_two.status_code, 200)
        self.assertEqual(len(instances), 1)


if __name__ == "__main__":
    unittest.main()
