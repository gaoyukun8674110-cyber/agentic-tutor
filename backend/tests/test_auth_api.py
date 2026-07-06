import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.config import settings
from app.database import Base, get_db
from app.utils.errors import http_exception_handler


class AuthApiTests(unittest.TestCase):
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
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        settings.JWT_SECRET = self.previous_secret
        settings.DEBUG = self.previous_debug

    def test_register_creates_user_without_logging_in(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password-123", "email": "alice@example.com"},
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["user"]["username"], "alice")
        self.assertEqual(payload["user"]["email"], "alice@example.com")
        self.assertNotIn("access_token", payload)
        self.assertIsNone(response.cookies.get(settings.COOKIE_REFRESH_NAME))

    def test_register_rejects_duplicate_username(self):
        self.client.post("/api/auth/register", json={"username": "alice", "password": "password-123"})

        response = self.client.post("/api/auth/register", json={"username": "alice", "password": "password-123"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "username_taken")

    def test_login_returns_access_token_and_http_only_refresh_cookie(self):
        self.client.post("/api/auth/register", json={"username": "alice", "password": "password-123"})

        response = self.client.post("/api/auth/login", json={"username": "alice", "password": "password-123"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["token_type"], "bearer")
        self.assertEqual(payload["expires_in"], 900)
        self.assertEqual(payload["user"]["username"], "alice")
        self.assertTrue(payload["access_token"])
        set_cookie = response.headers["set-cookie"]
        self.assertIn(f"{settings.COOKIE_REFRESH_NAME}=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("Path=/api/auth", set_cookie)

    def test_login_rejects_wrong_password_without_revealing_user_existence(self):
        self.client.post("/api/auth/register", json={"username": "alice", "password": "password-123"})

        response = self.client.post("/api/auth/login", json={"username": "alice", "password": "wrong-password"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "invalid_credentials")

    def test_login_rate_limits_repeated_bad_credentials_by_ip_and_username(self):
        self.client.post("/api/auth/register", json={"username": "rateuser", "password": "password-123"})

        for _ in range(5):
            response = self.client.post(
                "/api/auth/login",
                json={"username": "rateuser", "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 401)

        limited_response = self.client.post(
            "/api/auth/login",
            json={"username": "rateuser", "password": "wrong-password"},
        )

        self.assertEqual(limited_response.status_code, 429)
        self.assertEqual(limited_response.json()["detail"]["code"], "rate_limited")

    def test_refresh_rotates_cookie_and_rejects_old_refresh_token(self):
        self.client.post("/api/auth/register", json={"username": "alice", "password": "password-123"})
        login_response = self.client.post("/api/auth/login", json={"username": "alice", "password": "password-123"})
        old_refresh = login_response.cookies[settings.COOKIE_REFRESH_NAME]

        refresh_response = self.client.post("/api/auth/refresh")

        self.assertEqual(refresh_response.status_code, 200)
        self.assertTrue(refresh_response.json()["access_token"])
        new_refresh = refresh_response.cookies[settings.COOKIE_REFRESH_NAME]
        self.assertNotEqual(old_refresh, new_refresh)

        self.client.cookies.set(settings.COOKIE_REFRESH_NAME, old_refresh, path="/api/auth")
        replay_response = self.client.post("/api/auth/refresh")

        self.assertEqual(replay_response.status_code, 401)
        self.assertEqual(replay_response.json()["detail"]["code"], "invalid_refresh")

    def test_logout_revokes_refresh_cookie_idempotently(self):
        self.client.post("/api/auth/register", json={"username": "alice", "password": "password-123"})
        self.client.post("/api/auth/login", json={"username": "alice", "password": "password-123"})

        response = self.client.post("/api/auth/logout")
        second_response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(second_response.status_code, 204)
        self.assertIn(f"{settings.COOKIE_REFRESH_NAME}=", response.headers["set-cookie"])
        self.assertIn("Max-Age=0", response.headers["set-cookie"])

    def test_me_requires_bearer_access_token(self):
        self.client.post("/api/auth/register", json={"username": "alice", "password": "password-123"})
        login_response = self.client.post("/api/auth/login", json={"username": "alice", "password": "password-123"})
        token = login_response.json()["access_token"]

        response = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "alice")


if __name__ == "__main__":
    unittest.main()
