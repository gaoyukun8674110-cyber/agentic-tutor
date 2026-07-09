"""Active review report generation and optional APScheduler integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.agents.base import AgentContext
from app.agents.reviewer import ReviewerAgent
from app.agents.tools import LearnerStoreTool, ToolRegistry
from app.config import settings
from app.models.student import LearnerProfile, ReviewReport, Student, StudentAnswer
from app.services.llm_service import LLMService

try:  # pragma: no cover - exercised when dependency is installed in deployment.
    from apscheduler.schedulers.background import BackgroundScheduler
except Exception:  # pragma: no cover
    BackgroundScheduler = None


class ReviewSchedulerService:
    def __init__(self, db: Session, llm: LLMService | None = None, tools: ToolRegistry | None = None):
        self.db = db
        self.llm = llm or LLMService()
        self.tools = tools or ToolRegistry({"learner_store": LearnerStoreTool(db)})
        if not self.tools.has("learner_store"):
            self.tools.register("learner_store", LearnerStoreTool(db))
        self.reviewer = ReviewerAgent(self.llm)

    def run_for_student(
        self,
        student_id: int,
        *,
        user_id: str,
        resolved: Any | None = None,
        analytics: Any | None = None,
        force: bool = False,
    ) -> ReviewReport | None:
        student = self.db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return None
        if not force and not self.should_generate_review(student_id):
            return None

        result = self.reviewer.run(
            AgentContext(
                user_id=user_id,
                student_id=student_id,
                learner_snapshot={},
                signals={},
                tools=self.tools,
            ),
            {
                "student_id": student_id,
                "db": self.db,
                "resolved": resolved,
                "analytics": analytics,
            },
        )
        report_id = result.state_updates.get("review_report_id")
        if not report_id:
            return None
        return self.db.query(ReviewReport).filter(ReviewReport.id == report_id).first()

    def should_generate_review(self, student_id: int) -> bool:
        profile = self.db.query(LearnerProfile).filter(LearnerProfile.student_id == student_id).first()
        if profile and not profile.review_enabled:
            return False
        if not self._frequency_allows_review(student_id, profile.review_frequency if profile else "weekly"):
            return False
        return (
            self._has_low_effective_mastery(student_id)
            or self._has_consecutive_errors(student_id)
            or self._last_review_is_stale(student_id)
        )

    def _has_low_effective_mastery(self, student_id: int) -> bool:
        snapshot = self.tools.get("learner_store").snapshot(student_id)
        return any(
            float(skill.get("effective_mastery") or 0.0) < settings.REVIEW_MASTERY_THRESHOLD
            for skill in snapshot.get("masteries", [])
        )

    def _has_consecutive_errors(self, student_id: int, threshold: int = 3) -> bool:
        answers = (
            self.db.query(StudentAnswer)
            .filter(StudentAnswer.student_id == student_id)
            .order_by(StudentAnswer.created_at.desc())
            .limit(threshold)
            .all()
        )
        return len(answers) >= threshold and all(not answer.is_correct for answer in answers)

    def _last_review_is_stale(self, student_id: int) -> bool:
        latest = (
            self.db.query(ReviewReport)
            .filter(ReviewReport.student_id == student_id)
            .order_by(ReviewReport.created_at.desc())
            .first()
        )
        if not latest:
            return True
        try:
            created_at = datetime.fromisoformat(latest.created_at)
        except ValueError:
            return True
        return datetime.now(created_at.tzinfo) - created_at >= timedelta(days=7)

    def _frequency_allows_review(self, student_id: int, review_frequency: str) -> bool:
        latest = (
            self.db.query(ReviewReport)
            .filter(ReviewReport.student_id == student_id)
            .order_by(ReviewReport.created_at.desc())
            .first()
        )
        if not latest:
            return True
        try:
            created_at = datetime.fromisoformat(latest.created_at)
        except ValueError:
            return True
        frequency_days = {"daily": 1, "weekly": 7, "monthly": 30}.get((review_frequency or "weekly").lower(), 7)
        return datetime.now(created_at.tzinfo) - created_at >= timedelta(days=frequency_days)


class ReviewScheduler:
    def __init__(self, session_factory: sessionmaker, llm: LLMService):
        self.session_factory = session_factory
        self.llm = llm
        self.scheduler = BackgroundScheduler() if BackgroundScheduler else None

    def start(self) -> None:
        if not self.scheduler:
            return
        self.scheduler.add_job(
            self.run_due_reviews, "interval", hours=6, id="agentic_review_due", replace_existing=True
        )
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def run_due_reviews(self) -> None:
        db = self.session_factory()
        try:
            service = ReviewSchedulerService(db, llm=self.llm)
            students = db.query(Student).all()
            for student in students:
                service.run_for_student(student.id, user_id=student.user_id)
        finally:
            db.close()
