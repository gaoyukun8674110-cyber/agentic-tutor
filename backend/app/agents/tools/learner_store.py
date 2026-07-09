"""Learner-store tool wrapping StudentModelService and profile tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.student import LearnerProfile, StudentMastery
from app.services.student_model import StudentModelService


class LearnerStoreTool:
    name = "learner_store"

    def __init__(self, db: Session, student_model: StudentModelService | None = None):
        self.db = db
        self.student_model = student_model or StudentModelService(db)

    def weak_skills(self, student_id: int, k: int = 3) -> list[dict[str, Any]]:
        masteries = self.student_model.get_all_masteries(student_id)
        sorted_masteries = sorted(masteries, key=self.student_model._effective_mastery_score)
        return [
            self._mastery_payload(mastery)
            for mastery in sorted_masteries[:k]
            if self.student_model._effective_mastery_score(mastery) < 0.7
        ]

    def snapshot(self, student_id: int, *, weak_limit: int = 3) -> dict[str, Any]:
        profile = self.db.query(LearnerProfile).filter(LearnerProfile.student_id == student_id).first()
        masteries = self.student_model.get_all_masteries(student_id)
        mastery_payloads = [self._mastery_payload(mastery) for mastery in masteries]
        mastery_payloads.sort(key=lambda item: item["effective_mastery"])

        return {
            "student_id": student_id,
            "weak_skills": [item for item in mastery_payloads[:weak_limit] if item["effective_mastery"] < 0.7],
            "masteries": mastery_payloads,
            "learning_style": dict(profile.learning_style or {}) if profile else {},
            "review_enabled": bool(profile.review_enabled) if profile else True,
            "review_frequency": profile.review_frequency if profile else "weekly",
            "confidence_calibration": dict(profile.confidence_calibration or {}) if profile else {},
        }

    def ensure_profile(self, student_id: int) -> LearnerProfile:
        profile = self.db.query(LearnerProfile).filter(LearnerProfile.student_id == student_id).first()
        if profile:
            return profile
        profile = LearnerProfile(
            student_id=student_id,
            learning_style={},
            review_enabled=True,
            review_frequency="weekly",
            confidence_calibration={},
            updated_at=datetime.now().isoformat(),
        )
        self.db.add(profile)
        self.db.flush()
        return profile

    def _mastery_payload(self, mastery: StudentMastery) -> dict[str, Any]:
        effective_mastery = self.student_model._effective_mastery_score(mastery)
        return {
            "skill_id": mastery.skill_id,
            "skill_name": mastery.skill_name,
            "mastery_score": mastery.mastery_score,
            "effective_mastery": effective_mastery,
            "bkt_p_known": mastery.bkt_p_known,
            "bkt_half_life": mastery.bkt_half_life,
            "last_practiced_at": mastery.last_practiced_at,
            "total_attempts": mastery.total_attempts,
            "total_correct": mastery.total_correct,
        }
