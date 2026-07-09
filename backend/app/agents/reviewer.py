"""Reviewer specialist for learning report generation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.config import settings
from app.models.student import ReviewReport


class ReviewerAgent(BaseAgent):
    name = "reviewer"
    allowed_tools = ["learner_store"]

    def __init__(self, llm: Any | None = None):
        self.llm = llm

    def run(self, ctx: AgentContext, payload: dict) -> AgentResult:
        student_id = int(payload.get("student_id") or ctx.student_id or 0)
        if not student_id:
            raise ValueError("student_id is required for review generation")

        snapshot = dict(payload.get("learner_snapshot") or {})
        if not snapshot and ctx.tools and ctx.tools.has("learner_store"):
            snapshot = ctx.tools.get("learner_store").snapshot(student_id)

        weak_skills = list(snapshot.get("weak_skills") or [])
        period = str(payload.get("period") or datetime.now().strftime("%Y-W%W"))
        summary = self._build_fallback_summary(weak_skills)
        if self.llm and payload.get("resolved") and not settings.E2E_MOCK_LLM:
            summary = (
                self._llm_summary(
                    resolved=payload["resolved"],
                    weak_skills=weak_skills,
                    user_id=ctx.user_id,
                    session_id=ctx.session_id,
                    analytics=payload.get("analytics"),
                )
                or summary
            )

        report = {
            "summary": summary,
            "weak_skills": weak_skills,
            "target_skills": [
                {
                    "skill_id": skill["skill_id"],
                    "skill_name": skill.get("skill_name"),
                    "source": "weak",
                }
                for skill in weak_skills
            ],
            "review_threshold": settings.REVIEW_MASTERY_THRESHOLD,
            "learner_snapshot": snapshot,
        }

        db = payload.get("db")
        report_id = None
        if db is not None:
            review_report = ReviewReport(
                student_id=student_id,
                period=period,
                report=report,
                created_at=datetime.now().isoformat(),
                acknowledged=False,
            )
            db.add(review_report)
            db.commit()
            db.refresh(review_report)
            report_id = review_report.id

        return AgentResult(
            content=summary,
            state_updates={"review_report": report, "review_report_id": report_id},
            used_tools=["learner_store"],
            agent_type="reviewer",
        )

    @staticmethod
    def _build_fallback_summary(weak_skills: list[dict[str, Any]]) -> str:
        if not weak_skills:
            return "本轮复盘没有发现明显薄弱知识点，建议保持当前节奏并做少量巩固题。"
        names = [str(skill.get("skill_name") or skill.get("skill_id")) for skill in weak_skills[:3]]
        return f"建议优先复习：{', '.join(names)}。这些知识点的有效掌握度偏低，适合安排专项巩固。"

    def _llm_summary(
        self,
        *,
        resolved: Any,
        weak_skills: list[dict[str, Any]],
        user_id: str,
        session_id: int | None,
        analytics: Any,
    ) -> str | None:
        prompt = "请为 AI Tutor 学生生成一段简短复盘建议，基于以下薄弱知识点，输出 120 字以内中文：\n" f"{weak_skills}"
        result = self.llm.complete_chat(
            resolved=resolved,
            messages=[{"role": "user", "content": prompt}],
            prompt_profile="coach",
            tutor_context={"task": "review_report"},
            agent_type=f"agent:reviewer:{resolved.provider_id}",
            user_id=user_id,
            session_id=session_id,
            analytics=analytics,
            max_tokens=180,
            temperature=0.4,
        )
        if "error" in result:
            return None
        return result.get("message", {}).get("content")
