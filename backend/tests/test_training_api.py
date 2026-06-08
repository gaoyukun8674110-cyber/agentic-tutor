import unittest
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_current_user
from app.api.training import router as training_router
from app.database import Base, get_db
from app.models.session import LearningGoal, SessionStatus, TrainingSession
from app.models.student import Student
from app.models.user import User


def fake_user() -> User:
    return User(id=1, username="alice", email=None, is_active=True, created_at="now", updated_at="now")


class TrainingApiOwnershipTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        self.db = self.SessionLocal()
        now = datetime(2026, 5, 1, 9, 0).isoformat()
        self.db.add(User(username="alice", password_hash="x", is_active=True, created_at=now, updated_at=now))
        self.db.add(User(username="bob", password_hash="x", is_active=True, created_at=now, updated_at=now))
        bob = Student(user_id="bob", username="Bob", created_at=now, updated_at=now)
        self.db.add(bob)
        self.db.flush()
        self.foreign_session = TrainingSession(
            student_id=bob.id,
            learning_goal=LearningGoal.CONSOLIDATION,
            duration_minutes=25,
            status=SessionStatus.PENDING,
            session_plan={"phases": []},
            created_at=now,
            updated_at=now,
        )
        self.db.add(self.foreign_session)
        self.db.commit()

        app = FastAPI()
        app.dependency_overrides[get_current_user] = fake_user

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_db
        app.include_router(training_router)
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()

    def test_session_routes_hide_sessions_owned_by_another_user(self):
        session_id = self.foreign_session.id

        responses = [
            self.client.post(f"/api/training/sessions/{session_id}/start"),
            self.client.get(f"/api/training/sessions/{session_id}/next"),
            self.client.post(
                f"/api/training/sessions/{session_id}/answer",
                params={"question_id": 1},
                json={"answer": "x", "time_spent": 1},
            ),
            self.client.post(f"/api/training/sessions/{session_id}/complete"),
        ]

        self.assertEqual([response.status_code for response in responses], [404, 404, 404, 404])


if __name__ == "__main__":
    unittest.main()
