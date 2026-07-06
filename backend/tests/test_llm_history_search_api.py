import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.llm import router as llm_router
from app.config import settings
from app.database import Base, get_db
from app.models.user import User
from app.services.chat_history import ChatHistoryService


class LlmHistorySearchApiTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.SessionLocal()

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
        app.include_router(llm_router)
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()

    def test_search_conversations_endpoint_returns_matching_history(self):
        service = ChatHistoryService(self.db)
        created = service.save_exchange(
            conversation_id=None,
            user_message="Probability question",
            assistant_message="Posterior probability updates the prior.",
            prompt_profile="socratic",
            provider="linkapi",
            model="claude-haiku",
            training_mode="focus",
            user_id="alice",
        )

        response = self.client.get(
            "/api/llm/conversations/search",
            params={"query": "posterior", "user_id": "bob"},
        )

        self.assertEqual(response.status_code, 200)
        conversations = response.json()["conversations"]
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]["id"], created["id"])

    def test_conversations_endpoint_hides_other_users_history(self):
        service = ChatHistoryService(self.db)
        created = service.save_exchange(
            conversation_id=None,
            user_message="bob statistics conversation",
            assistant_message="scoped to bob",
            prompt_profile="three_stage",
            provider="linkapi",
            model="claude-haiku",
            training_mode="focus",
            user_id="bob",
        )

        response = self.client.get("/api/llm/conversations")

        self.assertEqual(response.status_code, 200)
        conversations = response.json()["conversations"]
        self.assertNotIn(created["id"], [item["id"] for item in conversations])

    def test_e2e_mock_chat_persists_conversation_without_provider_credentials(self):
        previous = settings.E2E_MOCK_LLM
        settings.E2E_MOCK_LLM = True
        try:
            response = self.client.post(
                "/api/llm/chat",
                json={
                    "provider": "auto",
                    "prompt_profile": "three_stage",
                    "messages": [{"role": "user", "content": "Explain Bayes rule"}],
                    "tutor_context": {"mode": "focus"},
                },
            )
        finally:
            settings.E2E_MOCK_LLM = previous

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider"], "e2e-mock")
        self.assertIn("conversation_id", body)
        self.assertEqual(body["exchange_count"], 1)
        self.assertEqual([message["role"] for message in body["messages"]], ["user", "assistant"])

        history_response = self.client.get("/api/llm/conversations")
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json()["conversations"][0]["id"], body["conversation_id"])

    def test_export_conversation_endpoint_returns_markdown(self):
        service = ChatHistoryService(self.db)
        created = service.save_exchange(
            conversation_id=None,
            user_message="请解释置信区间",
            assistant_message="置信区间是用抽样过程构造出的区间。",
            prompt_profile="three_stage",
            provider="linkapi",
            model="claude-haiku",
            training_mode="focus",
            user_id="alice",
        )

        response = self.client.get(
            f"/api/llm/conversations/{created['id']}/export",
            params={"user_id": "bob"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["filename"], "置信区间训练.md")
        self.assertIn("# 置信区间训练", body["content"])
        self.assertIn("请解释置信区间", body["content"])


if __name__ == "__main__":
    unittest.main()
