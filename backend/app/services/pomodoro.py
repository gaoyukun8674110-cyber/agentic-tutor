"""番茄钟服务 - 时间管理、间隔重复、学习节奏"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.session import SessionStatus, TrainingSession
from app.models.student import StudentMastery


class PomodoroService:
    """番茄钟服务"""

    def __init__(self, db: Session):
        self.db = db

    def get_session_time_remaining(self, session_id: int) -> dict[str, Any] | None:
        """获取 Session 剩余时间"""
        session = self.db.query(TrainingSession).filter(TrainingSession.id == session_id).first()

        if not session or session.status != SessionStatus.IN_PROGRESS:
            return None

        if not session.started_at:
            return None

        # 计算剩余时间
        started = datetime.fromisoformat(session.started_at)
        elapsed = (datetime.now() - started).total_seconds() / 60  # 分钟
        remaining = max(0, session.duration_minutes - elapsed)

        return {
            "session_id": session_id,
            "elapsed_minutes": elapsed,
            "remaining_minutes": remaining,
            "total_minutes": session.duration_minutes,
            "progress_percent": (elapsed / session.duration_minutes * 100) if session.duration_minutes > 0 else 0,
        }

    def should_wrap_up(self, session_id: int, threshold_minutes: int = 5) -> bool:
        """判断是否应该收尾（剩余时间少于阈值）"""
        time_info = self.get_session_time_remaining(session_id)
        if not time_info:
            return False

        return time_info["remaining_minutes"] <= threshold_minutes

    def get_spaced_repetition_plan(
        self,
        student_id: int,
        days_ahead: int = 7,
    ) -> list[dict[str, Any]]:
        """生成间隔重复复习计划"""
        # 获取所有掌握度记录
        masteries = self.db.query(StudentMastery).filter(StudentMastery.student_id == student_id).all()

        review_plan = []
        now = datetime.now()

        for mastery in masteries:
            if not mastery.last_practiced_at:
                continue

            last_practiced = datetime.fromisoformat(mastery.last_practiced_at)
            days_since = (now - last_practiced).days

            # 根据掌握度和时间间隔决定是否需要复习
            should_review = False
            review_priority = 0

            if mastery.mastery_score < 0.5:
                # 掌握度低，需要频繁复习
                if days_since >= 1:
                    should_review = True
                    review_priority = 3  # 高优先级
            elif mastery.mastery_score < 0.7:
                # 掌握度中等，3天复习一次
                if days_since >= 3:
                    should_review = True
                    review_priority = 2
            elif mastery.mastery_score < 0.9:
                # 掌握度较好，7天复习一次
                if days_since >= 7:
                    should_review = True
                    review_priority = 1
            else:
                # 掌握度很高，14天复习一次
                if days_since >= 14:
                    should_review = True
                    review_priority = 0

            if should_review:
                review_plan.append(
                    {
                        "skill_id": mastery.skill_id,
                        "skill_name": mastery.skill_name,
                        "mastery_score": mastery.mastery_score,
                        "days_since_practice": days_since,
                        "priority": review_priority,
                        "recommended_review_date": (now + timedelta(days=1)).isoformat(),
                    }
                )

        # 按优先级排序
        review_plan.sort(key=lambda x: x["priority"], reverse=True)

        return review_plan

    def check_fatigue_signals(
        self,
        session_id: int,
        recent_answers: list[dict[str, Any]],  # [{"is_correct": bool, "time_spent": float}]
    ) -> dict[str, Any]:
        """检测疲劳信号"""
        if len(recent_answers) < 3:
            return {"is_fatigued": False, "signals": []}

        # 分析最近几题的表现
        recent = recent_answers[-5:]  # 最近5题

        error_rate = sum(1 for a in recent if not a["is_correct"]) / len(recent)
        avg_time = sum(a["time_spent"] for a in recent) / len(recent)

        # 如果前面有数据，比较
        if len(recent_answers) >= 10:
            earlier = recent_answers[-10:-5]
            earlier_avg_time = sum(a["time_spent"] for a in earlier) / len(earlier)

            # 用时明显变长（增加50%以上）
            time_increase = (avg_time - earlier_avg_time) / earlier_avg_time if earlier_avg_time > 0 else 0
        else:
            time_increase = 0

        signals = []
        is_fatigued = False

        if error_rate > 0.6:
            signals.append("high_error_rate")
            is_fatigued = True

        if time_increase > 0.5:
            signals.append("increasing_time")
            is_fatigued = True

        return {
            "is_fatigued": is_fatigued,
            "signals": signals,
            "error_rate": error_rate,
            "average_time": avg_time,
            "recommendation": "take_break" if is_fatigued else "continue",
        }

    def get_daily_pomodoro_reminder(self, student_id: int) -> dict[str, Any] | None:
        """获取每日番茄钟提醒"""
        # 这里可以集成日历/通知系统
        # 简化实现：返回建议
        return {
            "student_id": student_id,
            "recommended_sessions_today": 3,
            "message": "建议今天完成 3 个番茄钟训练",
        }
