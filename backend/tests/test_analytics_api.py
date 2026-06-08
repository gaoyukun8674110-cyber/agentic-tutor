import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.analytics import router as analytics_router
from app.api.deps import get_current_user
from app.models.user import User


def fake_user() -> User:
    return User(id=1, username="alice", email=None, is_active=True, created_at="now", updated_at="now")


class AnalyticsApiAuthTests(unittest.TestCase):
    def test_non_admin_user_cannot_read_global_analytics(self):
        app = FastAPI()
        app.dependency_overrides[get_current_user] = fake_user
        app.include_router(analytics_router)
        client = TestClient(app)

        response = client.get("/api/analytics/system/stats")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
