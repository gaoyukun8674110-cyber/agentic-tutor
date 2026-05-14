import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.llm import router as llm_router
from app.api.student import router as student_router
from app.config import settings
from app.database import Base, get_db
from app.services.chat_history import ChatHistoryService
from app.utils.errors import http_exception_handler


class MultiUserIsolationTests(unittest.TestCase):
    def setUp(self):
        self.previous_secret = settings.JWT_SECRET
        self.previous_debug = settings.DEBUG
        settings.JWT_SECRET = "test-secret-with-at-least-32-bytes!!"
        settings.DEBUG = True

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.SessionLocal()

        app = FastAPI()
        app.add_exception_handler(StarletteHTTPException, http_exception_handler)

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_db
        app.include_router(auth_router)
        app.include_router(dashboard_router)
        app.include_router(llm_router)
        app.include_router(student_router)
        self.client = TestClient(app)

        self.alice_token = self._register_and_login("alice")
        self.bob_token = self._register_and_login("bob")

    def tearDown(self):
        self.db.close()
        settings.JWT_SECRET = self.previous_secret
        settings.DEBUG = self.previous_debug

    def _register_and_login(self, username: str) -> str:
        self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "password-123"},
        )
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "password-123"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access_token"]

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_dashboard_tasks_are_scoped_to_authenticated_user(self):
        created = self.client.post(
            "/api/dashboard/tasks",
            headers=self._auth(self.alice_token),
            json={"subject": "Math", "task": "Alice-only task", "duration": 25},
        )
        self.assertEqual(created.status_code, 200)

        bob_response = self.client.get("/api/dashboard/tasks", headers=self._auth(self.bob_token))
        alice_response = self.client.get("/api/dashboard/tasks", headers=self._auth(self.alice_token))

        self.assertEqual(bob_response.status_code, 200)
        self.assertEqual(alice_response.status_code, 200)
        self.assertEqual(bob_response.json()["tasks"], [])
        self.assertEqual(alice_response.json()["tasks"][0]["task"], "Alice-only task")

    def test_student_routes_reject_other_user_path_parameters(self):
        response = self.client.get(
            "/api/student/alice/mastery",
            headers=self._auth(self.bob_token),
        )

        self.assertEqual(response.status_code, 403)

    def test_tutor_conversations_are_scoped_to_authenticated_user(self):
        service = ChatHistoryService(self.db)
        alice_chat = service.save_exchange(
            conversation_id=None,
            user_message="Alice statistics question",
            assistant_message="Alice scoped answer",
            prompt_profile="socratic",
            provider="linkapi",
            model="claude-haiku",
            training_mode="focus",
            user_id="alice",
        )
        bob_chat = service.save_exchange(
            conversation_id=None,
            user_message="Bob probability question",
            assistant_message="Bob scoped answer",
            prompt_profile="socratic",
            provider="linkapi",
            model="claude-haiku",
            training_mode="focus",
            user_id="bob",
        )

        response = self.client.get("/api/llm/conversations", headers=self._auth(self.alice_token))

        self.assertEqual(response.status_code, 200)
        conversation_ids = [item["id"] for item in response.json()["conversations"]]
        self.assertIn(alice_chat["id"], conversation_ids)
        self.assertNotIn(bob_chat["id"], conversation_ids)


if __name__ == "__main__":
    unittest.main()
