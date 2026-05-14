import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.llm import router as llm_router
from app.config import settings
from app.database import Base, get_db
from app.models.llm_credentials import UserLLMCredential
from app.services.llm_credential_resolver import LLMCredentialResolver
from app.services.llm_credential_service import (
    CredentialAADMismatch,
    LLMCredentialService,
)
from app.utils.errors import http_exception_handler
from tests.auth_helpers import bearer_headers, create_test_user


class LLMCredentialServiceTests(unittest.TestCase):
    def setUp(self):
        self.previous_key = settings.LLM_CREDENTIAL_ENCRYPTION_KEY
        self.previous_previous_keys = settings.LLM_CREDENTIAL_PREVIOUS_KEYS
        self.previous_hmac_key = settings.LLM_FINGERPRINT_HMAC_KEY
        settings.LLM_CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
        settings.LLM_CREDENTIAL_PREVIOUS_KEYS = ""
        settings.LLM_FINGERPRINT_HMAC_KEY = "fingerprint-test-secret"

    def tearDown(self):
        settings.LLM_CREDENTIAL_ENCRYPTION_KEY = self.previous_key
        settings.LLM_CREDENTIAL_PREVIOUS_KEYS = self.previous_previous_keys
        settings.LLM_FINGERPRINT_HMAC_KEY = self.previous_hmac_key

    def test_encrypts_key_with_aad_and_never_stores_plaintext(self):
        service = LLMCredentialService()

        encrypted = service.encrypt_api_key("sk-user-secret", user_id=10, provider_id="linkapi")

        self.assertNotIn("sk-user-secret", encrypted)
        self.assertEqual(
            service.decrypt_api_key(encrypted, user_id=10, provider_id="linkapi"),
            "sk-user-secret",
        )
        with self.assertRaises(CredentialAADMismatch):
            service.decrypt_api_key(encrypted, user_id=11, provider_id="linkapi")

    def test_previous_encryption_keys_can_decrypt_rotated_credentials(self):
        old_key = Fernet.generate_key().decode()
        settings.LLM_CREDENTIAL_ENCRYPTION_KEY = old_key
        old_service = LLMCredentialService()
        encrypted = old_service.encrypt_api_key("sk-rotated", user_id=1, provider_id="openai")

        settings.LLM_CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
        settings.LLM_CREDENTIAL_PREVIOUS_KEYS = old_key
        new_service = LLMCredentialService()

        self.assertEqual(
            new_service.decrypt_api_key(encrypted, user_id=1, provider_id="openai"),
            "sk-rotated",
        )

    def test_fingerprint_is_stable_and_hmac_keyed(self):
        service = LLMCredentialService()
        first = service.fingerprint_api_key("sk-stable")
        second = service.fingerprint_api_key("sk-stable")

        settings.LLM_FINGERPRINT_HMAC_KEY = "different-secret"
        changed = LLMCredentialService().fingerprint_api_key("sk-stable")

        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)


class LLMCredentialApiTests(unittest.TestCase):
    def setUp(self):
        self.previous_secret = settings.JWT_SECRET
        self.previous_key = settings.LLM_CREDENTIAL_ENCRYPTION_KEY
        self.previous_previous_keys = settings.LLM_CREDENTIAL_PREVIOUS_KEYS
        self.previous_hmac_key = settings.LLM_FINGERPRINT_HMAC_KEY
        self.previous_fallback = settings.ALLOW_GLOBAL_LLM_FALLBACK
        settings.JWT_SECRET = "test-secret-with-at-least-32-bytes!!"
        settings.LLM_CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
        settings.LLM_CREDENTIAL_PREVIOUS_KEYS = ""
        settings.LLM_FINGERPRINT_HMAC_KEY = "fingerprint-test-secret"
        settings.ALLOW_GLOBAL_LLM_FALLBACK = False

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.SessionLocal()
        create_test_user(self.db, username="alice")
        create_test_user(self.db, username="bob")

        app = FastAPI()
        app.add_exception_handler(StarletteHTTPException, http_exception_handler)

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_db
        app.include_router(llm_router)
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        settings.JWT_SECRET = self.previous_secret
        settings.LLM_CREDENTIAL_ENCRYPTION_KEY = self.previous_key
        settings.LLM_CREDENTIAL_PREVIOUS_KEYS = self.previous_previous_keys
        settings.LLM_FINGERPRINT_HMAC_KEY = self.previous_hmac_key
        settings.ALLOW_GLOBAL_LLM_FALLBACK = self.previous_fallback

    def test_put_saves_user_credential_without_returning_plaintext_key(self):
        response = self.client.put(
            "/api/llm/credentials/linkapi",
            headers=bearer_headers("alice"),
            json={
                "api_key": "sk-user-secret",
                "base_url": "https://api.linkapi.ai/v1",
                "default_model": "claude-sonnet-4-20250514",
                "is_default": True,
                "is_enabled": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload_text = response.text
        self.assertNotIn("sk-user-secret", payload_text)
        credential = self.db.query(UserLLMCredential).one()
        self.assertEqual(credential.provider_id, "linkapi")
        self.assertNotIn("sk-user-secret", credential.encrypted_api_key)
        self.assertTrue(credential.api_key_fingerprint)

    def test_patch_forbids_api_key_and_keeps_existing_secret(self):
        self.client.put(
            "/api/llm/credentials/openai",
            headers=bearer_headers("alice"),
            json={"api_key": "sk-user-secret", "is_default": True, "is_enabled": True},
        )

        response = self.client.patch(
            "/api/llm/credentials/openai",
            headers=bearer_headers("alice"),
            json={"api_key": "sk-new-secret", "default_model": "gpt-4o-mini"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "api_key_must_use_put")
        credential = self.db.query(UserLLMCredential).one()
        self.assertEqual(
            LLMCredentialService().decrypt_for_provider_call(credential, 1, "openai"),
            "sk-user-secret",
        )

    def test_list_only_returns_current_users_safe_metadata(self):
        self.client.put(
            "/api/llm/credentials/openai",
            headers=bearer_headers("alice"),
            json={"api_key": "sk-alice-secret", "is_default": True, "is_enabled": True},
        )
        self.client.put(
            "/api/llm/credentials/openai",
            headers=bearer_headers("bob"),
            json={"api_key": "sk-bob-secret", "is_default": True, "is_enabled": True},
        )

        response = self.client.get("/api/llm/credentials", headers=bearer_headers("alice"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("sk-alice-secret", response.text)
        self.assertNotIn("sk-bob-secret", response.text)
        credentials = response.json()["credentials"]
        self.assertEqual(len(credentials), 1)
        self.assertEqual(credentials[0]["provider_id"], "openai")

    def test_rejects_private_or_metadata_base_urls(self):
        response = self.client.put(
            "/api/llm/credentials/linkapi",
            headers=bearer_headers("alice"),
            json={"api_key": "sk-user-secret", "base_url": "https://169.254.169.254/v1"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "invalid_provider_base_url")


class LLMCredentialResolverTests(unittest.TestCase):
    def setUp(self):
        self.previous_key = settings.LLM_CREDENTIAL_ENCRYPTION_KEY
        self.previous_hmac_key = settings.LLM_FINGERPRINT_HMAC_KEY
        self.previous_fallback = settings.ALLOW_GLOBAL_LLM_FALLBACK
        self.previous_openai_key = settings.OPENAI_API_KEY
        settings.LLM_CREDENTIAL_ENCRYPTION_KEY = Fernet.generate_key().decode()
        settings.LLM_FINGERPRINT_HMAC_KEY = "fingerprint-test-secret"
        settings.ALLOW_GLOBAL_LLM_FALLBACK = True
        settings.OPENAI_API_KEY = "GLOBAL-MUST-NOT-LEAK"

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.SessionLocal()
        self.user = create_test_user(self.db, username="alice")

    def tearDown(self):
        self.db.close()
        settings.LLM_CREDENTIAL_ENCRYPTION_KEY = self.previous_key
        settings.LLM_FINGERPRINT_HMAC_KEY = self.previous_hmac_key
        settings.ALLOW_GLOBAL_LLM_FALLBACK = self.previous_fallback
        settings.OPENAI_API_KEY = self.previous_openai_key

    def test_user_credential_wins_over_global_fallback(self):
        service = LLMCredentialService(self.db)
        credential = service.put_credential(
            user=self.user,
            provider_id="openai",
            api_key="sk-user-secret",
            base_url=None,
            default_model="gpt-4o-mini",
            is_default=True,
            is_enabled=True,
        )
        self.db.refresh(credential)

        resolved = LLMCredentialResolver(self.db).resolve(self.user, "auto")

        self.assertEqual(resolved.provider_id, "openai")
        self.assertEqual(resolved.source, "user")
        self.assertEqual(resolved.api_key, "sk-user-secret")
        self.assertNotIn("sk-user-secret", repr(resolved))

    def test_fallback_disabled_returns_not_configured_without_global_key(self):
        settings.ALLOW_GLOBAL_LLM_FALLBACK = False

        with self.assertRaisesRegex(ValueError, "llm_provider_not_configured"):
            LLMCredentialResolver(self.db).resolve(self.user, "openai")


class LLMChatCredentialResolutionTests(unittest.TestCase):
    def test_chat_accepts_resolved_provider_and_reports_credential_source(self):
        from app.services.llm_service import LLMService

        class FakeMessage:
            content = "ok"

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        class FakeCompletions:
            def create(self, **kwargs):
                self.kwargs = kwargs
                return FakeResponse()

        class FakeChat:
            def __init__(self):
                self.completions = FakeCompletions()

        class FakeOpenAI:
            instances = []

            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.chat = FakeChat()
                FakeOpenAI.instances.append(self)

        resolved = type(
            "Resolved",
            (),
            {
                "provider_id": "openai",
                "api_key": "sk-user-secret",
                "base_url": "https://api.openai.com/v1",
                "default_model": "gpt-4o-mini",
                "source": "user",
                "fingerprint": "abc123",
                "credential_id": 1,
            },
        )()

        with patch("app.services.llm_service.OpenAI", FakeOpenAI):
            result = LLMService().complete_chat(
                resolved=resolved,
                messages=[{"role": "user", "content": "hello"}],
                prompt_profile="socratic",
                agent_type="tutor_chat:socratic:openai",
                user_id="alice",
                session_id=None,
                analytics=None,
            )

        self.assertEqual(FakeOpenAI.instances[0].kwargs["api_key"], "sk-user-secret")
        self.assertEqual(result["credential_source"], "user")
        self.assertEqual(result["credential_fingerprint"], "abc123")


class SafeLLMErrorTests(unittest.TestCase):
    def test_safe_llm_error_redacts_keys_from_logs_and_response(self):
        from app.utils.errors import safe_llm_error

        with self.assertLogs("ai_tutor", level="ERROR") as logs:
            payload = safe_llm_error(RuntimeError("Authorization: Bearer sk-secret api_key=sk-another-secret"))

        combined_logs = "\n".join(logs.output)
        self.assertEqual(payload["code"], "llm_provider_error")
        self.assertNotIn("sk-secret", str(payload))
        self.assertNotIn("sk-secret", combined_logs)
        self.assertNotIn("sk-another-secret", combined_logs)


if __name__ == "__main__":
    unittest.main()
