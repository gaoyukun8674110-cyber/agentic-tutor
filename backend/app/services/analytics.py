"""分析服务 - 行为日志、统计分析、A/B 测试"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.analytics import BehaviorLog, QuestionStat, SkillStat
from app.models.student import StudentAnswer


class AnalyticsService:
    """分析服务"""

    def __init__(self, db: Session):
        self.db = db

    def log_behavior(
        self,
        log_type: str,
        action: str,
        user_id: str | None = None,
        session_id: int | None = None,
        question_id: int | None = None,
        details: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BehaviorLog:
        """记录行为日志"""
        log = BehaviorLog(
            log_type=log_type,
            action=action,
            user_id=user_id,
            session_id=session_id,
            question_id=question_id,
            details=details or {},
            metadata_=metadata or {},
            created_at=datetime.now().isoformat(),
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def log_api_call(
        self,
        endpoint: str,
        method: str,
        user_id: str | None = None,
        duration_ms: float | None = None,
        status_code: int | None = None,
        error: str | None = None,
    ):
        """记录 API 调用"""
        return self.log_behavior(
            log_type="api_call",
            action=f"{method} {endpoint}",
            user_id=user_id,
            metadata={
                "endpoint": endpoint,
                "method": method,
                "duration_ms": duration_ms,
                "status_code": status_code,
                "error": error,
            },
        )

    def log_answer(
        self,
        user_id: str,
        session_id: int,
        question_id: int,
        is_correct: bool,
        time_spent: float,
        hint_count: int,
    ):
        """记录答题行为"""
        return self.log_behavior(
            log_type="answer",
            action="submit_answer",
            user_id=user_id,
            session_id=session_id,
            question_id=question_id,
            details={
                "is_correct": is_correct,
                "time_spent": time_spent,
                "hint_count": hint_count,
            },
        )

    def log_llm_call(
        self,
        user_id: str | None,
        session_id: int | None,
        agent_type: str,
        prompt_length: int,
        response_length: int,
        duration_ms: float,
    ):
        """记录 LLM 调用"""
        return self.log_behavior(
            log_type="llm_call",
            action=f"call_{agent_type}",
            user_id=user_id,
            session_id=session_id,
            metadata={
                "agent_type": agent_type,
                "prompt_length": prompt_length,
                "response_length": response_length,
                "duration_ms": duration_ms,
            },
        )

    def update_question_stat(self, question_id: int, is_correct: bool, time_spent: float, hint_count: int):
        """更新题目统计"""
        stat = self.db.query(QuestionStat).filter(QuestionStat.question_id == question_id).first()

        if not stat:
            stat = QuestionStat(
                question_id=question_id,
                updated_at=datetime.now().isoformat(),
            )
            self.db.add(stat)

        stat.exposure_count += 1
        stat.answer_count += 1

        if is_correct:
            stat.correct_count += 1

        # 更新正确率
        stat.correct_rate = stat.correct_count / stat.answer_count if stat.answer_count > 0 else 0.0

        # 更新平均用时（移动平均）
        if stat.average_time == 0:
            stat.average_time = time_spent
        else:
            stat.average_time = stat.average_time * 0.7 + time_spent * 0.3

        # 更新 hint 使用率
        stat.hint_usage_rate = (
            stat.hint_usage_rate * (stat.answer_count - 1) + (1 if hint_count > 0 else 0)
        ) / stat.answer_count

        stat.updated_at = datetime.now().isoformat()
        self.db.commit()

    def get_question_stats(self, question_id: int) -> dict[str, Any] | None:
        """获取题目统计"""
        stat = self.db.query(QuestionStat).filter(QuestionStat.question_id == question_id).first()

        if not stat:
            return None

        return {
            "question_id": question_id,
            "exposure_count": stat.exposure_count,
            "answer_count": stat.answer_count,
            "correct_count": stat.correct_count,
            "correct_rate": stat.correct_rate,
            "average_time": stat.average_time,
            "hint_usage_rate": stat.hint_usage_rate,
            "quality_score": stat.quality_score,
        }

    def get_problematic_questions(
        self,
        min_attempts: int = 10,
        max_correct_rate: float = 0.3,
    ) -> list[dict[str, Any]]:
        """找出有质量问题的题目"""
        problematic = (
            self.db.query(QuestionStat)
            .filter(
                QuestionStat.answer_count >= min_attempts,
                QuestionStat.correct_rate <= max_correct_rate,
            )
            .all()
        )

        return [
            {
                "question_id": stat.question_id,
                "correct_rate": stat.correct_rate,
                "answer_count": stat.answer_count,
                "quality_score": stat.quality_score,
            }
            for stat in problematic
        ]

    def update_skill_stat(self, skill_id: str, skill_name: str, is_correct: bool, time_spent: float):
        """更新知识点统计"""
        stat = self.db.query(SkillStat).filter(SkillStat.skill_id == skill_id).first()

        if not stat:
            stat = SkillStat(
                skill_id=skill_id,
                skill_name=skill_name,
                updated_at=datetime.now().isoformat(),
            )
            self.db.add(stat)

        stat.total_attempts += 1
        if is_correct:
            stat.total_correct += 1

        stat.overall_correct_rate = stat.total_correct / stat.total_attempts if stat.total_attempts > 0 else 0.0

        if stat.average_time == 0:
            stat.average_time = time_spent
        else:
            stat.average_time = stat.average_time * 0.7 + time_spent * 0.3

        stat.updated_at = datetime.now().isoformat()
        self.db.commit()

    def get_skill_stats(self, skill_id: str) -> dict[str, Any] | None:
        """获取知识点统计"""
        stat = self.db.query(SkillStat).filter(SkillStat.skill_id == skill_id).first()

        if not stat:
            return None

        return {
            "skill_id": skill_id,
            "skill_name": stat.skill_name,
            "total_attempts": stat.total_attempts,
            "total_correct": stat.total_correct,
            "overall_correct_rate": stat.overall_correct_rate,
            "average_time": stat.average_time,
            "common_errors": stat.common_errors or [],
        }

    def get_system_stats(
        self,
        days: int = 7,
    ) -> dict[str, Any]:
        """获取系统级统计"""
        since = datetime.now() - timedelta(days=days)
        since_str = since.isoformat()

        # 活跃用户数
        active_users = (
            self.db.query(func.count(func.distinct(BehaviorLog.user_id)))
            .filter(
                BehaviorLog.created_at >= since_str,
                BehaviorLog.user_id.isnot(None),
            )
            .scalar()
            or 0
        )

        # 总 Session 数
        from app.models.session import TrainingSession

        total_sessions = (
            self.db.query(func.count(TrainingSession.id))
            .filter(
                TrainingSession.created_at >= since_str,
            )
            .scalar()
            or 0
        )

        # 总答题数
        total_answers = (
            self.db.query(func.count(StudentAnswer.id))
            .filter(
                StudentAnswer.created_at >= since_str,
            )
            .scalar()
            or 0
        )

        # 平均 Session 时长（简化）
        completed_sessions = (
            self.db.query(TrainingSession)
            .filter(
                TrainingSession.status == "completed",
                TrainingSession.created_at >= since_str,
            )
            .all()
        )

        avg_duration = (
            sum(s.duration_minutes for s in completed_sessions) / len(completed_sessions) if completed_sessions else 0
        )

        return {
            "period_days": days,
            "active_users": active_users,
            "total_sessions": total_sessions,
            "total_answers": total_answers,
            "average_session_duration_minutes": avg_duration,
        }

    def get_ab_test_results(
        self,
        strategy_a_name: str,
        strategy_b_name: str,
        days: int = 7,
    ) -> dict[str, Any]:
        """A/B 测试结果对比（简化实现）"""
        # 实际应该从日志中提取策略版本信息
        # 这里简化处理
        return {
            "strategy_a": strategy_a_name,
            "strategy_b": strategy_b_name,
            "period_days": days,
            "note": "需要在实际日志中记录策略版本信息",
        }
