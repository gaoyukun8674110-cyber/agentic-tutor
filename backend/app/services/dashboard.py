"""Dashboard aggregation and persistence service."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_history import TutorConversation
from app.models.dashboard import DashboardTask, PomodoroLog
from app.models.session import TrainingSession
from app.models.student import Student, StudentAnswer


class DashboardService:
    """Build dashboard data from persisted backend records."""

    def __init__(self, db: Session):
        self.db = db

    def create_task(
        self,
        user_id: str,
        subject: str,
        task: str,
        duration: int,
        priority: str,
        scheduled_date: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = self._now(now)
        item = DashboardTask(
            user_id=user_id,
            subject=subject.strip() or "Study",
            task=task.strip(),
            duration=max(1, int(duration)),
            priority=priority or "medium",
            scheduled_date=scheduled_date,
            completed=False,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self._task_payload(item)

    def update_task(
        self,
        task_id: int,
        user_id: str,
        subject: str | None = None,
        task: str | None = None,
        duration: int | None = None,
        priority: str | None = None,
        completed: bool | None = None,
        scheduled_date: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        item = self._get_task(task_id, user_id)
        if not item:
            raise ValueError("Task not found")

        timestamp = self._now(now)
        if subject is not None:
            item.subject = subject.strip() or "Study"
        if task is not None:
            item.task = task.strip()
        if duration is not None:
            item.duration = max(1, int(duration))
        if priority is not None:
            item.priority = priority
        if scheduled_date is not None:
            item.scheduled_date = scheduled_date
        if completed is not None and completed != item.completed:
            item.completed = completed
            item.completed_at = timestamp if completed else None

        item.updated_at = timestamp
        self.db.commit()
        self.db.refresh(item)
        return self._task_payload(item)

    def delete_task(self, task_id: int, user_id: str) -> bool:
        item = self._get_task(task_id, user_id)
        if not item:
            return False
        self.db.delete(item)
        self.db.commit()
        return True

    def list_tasks(self, user_id: str, scheduled_date: str | None = None) -> list[dict[str, Any]]:
        query = self.db.query(DashboardTask).filter(DashboardTask.user_id == user_id)
        if scheduled_date:
            query = query.filter(DashboardTask.scheduled_date == scheduled_date)
        return [
            self._task_payload(item)
            for item in query.order_by(DashboardTask.created_at.asc(), DashboardTask.id.asc()).all()
        ]

    def log_pomodoro(
        self,
        user_id: str,
        mode: str,
        duration_minutes: int,
        completed_at: datetime | None = None,
    ) -> dict[str, Any]:
        completed = completed_at or datetime.now()
        timestamp = completed.isoformat()
        item = PomodoroLog(
            user_id=user_id,
            mode=mode,
            duration_minutes=max(1, int(duration_minutes)),
            completed_at=timestamp,
            created_at=timestamp,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return {
            "id": item.id,
            "user_id": item.user_id,
            "mode": item.mode,
            "duration_minutes": item.duration_minutes,
            "completed_at": item.completed_at,
        }

    def get_summary(self, user_id: str, today: date | None = None, days: int = 7) -> dict[str, Any]:
        current_day = today or date.today()
        window_days = max(1, min(days, 31))
        week_days = [current_day - timedelta(days=offset) for offset in range(window_days - 1, -1, -1)]
        today_key = current_day.isoformat()
        today_tasks = self.list_tasks(user_id=user_id, scheduled_date=today_key)
        today_completed_tasks = [task for task in today_tasks if task["completed"]]
        today_focus_minutes = self._focus_minutes_for_day(user_id, current_day)
        today_pomodoros = self._pomodoro_count_for_day(user_id, current_day)

        weekly_data = [
            {
                "date": day.isoformat(),
                "day": day.strftime("%a"),
                "hours": round(self._focus_minutes_for_day(user_id, day) / 60, 2),
                "tasks": self._completed_task_count_for_day(user_id, day),
            }
            for day in week_days
        ]

        return {
            "user_id": user_id,
            "today": {
                "date": today_key,
                "focus_minutes": today_focus_minutes,
                "completed_pomodoros": today_pomodoros,
                "completed_tasks": len(today_completed_tasks),
                "total_tasks": len(today_tasks),
            },
            "streak_days": self._streak_days(user_id, current_day),
            "tasks": today_tasks,
            "weekly_data": weekly_data,
            "calendar_events": self._calendar_events(user_id, week_days[0], week_days[-1]),
        }

    def _get_task(self, task_id: int, user_id: str) -> DashboardTask | None:
        return (
            self.db.query(DashboardTask).filter(DashboardTask.id == task_id, DashboardTask.user_id == user_id).first()
        )

    def _focus_minutes_for_day(self, user_id: str, target_day: date) -> int:
        start, end = self._day_bounds(target_day)
        pomodoro_minutes = (
            sum(
                item.duration_minutes
                for item in self.db.query(PomodoroLog)
                .filter(
                    PomodoroLog.user_id == user_id,
                    PomodoroLog.completed_at >= start,
                    PomodoroLog.completed_at < end,
                )
                .all()
            )
            or 0
        )
        session_minutes = (
            sum(
                session.duration_minutes
                for session in self.db.query(TrainingSession)
                .join(Student, TrainingSession.student_id == Student.id)
                .filter(
                    Student.user_id == user_id,
                    TrainingSession.completed_at >= start,
                    TrainingSession.completed_at < end,
                )
                .all()
            )
            or 0
        )
        return int(pomodoro_minutes + session_minutes)

    def _pomodoro_count_for_day(self, user_id: str, target_day: date) -> int:
        start, end = self._day_bounds(target_day)
        return (
            self.db.query(PomodoroLog)
            .filter(
                PomodoroLog.user_id == user_id,
                PomodoroLog.mode == "work",
                PomodoroLog.completed_at >= start,
                PomodoroLog.completed_at < end,
            )
            .count()
        )

    def _completed_task_count_for_day(self, user_id: str, target_day: date) -> int:
        key = target_day.isoformat()
        return (
            self.db.query(DashboardTask)
            .filter(
                DashboardTask.user_id == user_id,
                DashboardTask.scheduled_date == key,
                DashboardTask.completed.is_(True),
            )
            .count()
        )

    def _streak_days(self, user_id: str, current_day: date) -> int:
        active_dates = self._activity_dates(user_id)
        streak = 0
        day = current_day
        while day.isoformat() in active_dates:
            streak += 1
            day -= timedelta(days=1)
        return streak

    def _activity_dates(self, user_id: str) -> set[str]:
        dates: set[str] = set()
        for item in self.db.query(PomodoroLog).filter(PomodoroLog.user_id == user_id).all():
            dates.add(item.completed_at[:10])
        for item in (
            self.db.query(DashboardTask)
            .filter(
                DashboardTask.user_id == user_id,
                DashboardTask.completed_at.isnot(None),
            )
            .all()
        ):
            dates.add(item.completed_at[:10])
        for answer in (
            self.db.query(StudentAnswer)
            .join(Student, StudentAnswer.student_id == Student.id)
            .filter(Student.user_id == user_id)
            .all()
        ):
            dates.add(answer.created_at[:10])
        for session in (
            self.db.query(TrainingSession)
            .join(Student, TrainingSession.student_id == Student.id)
            .filter(
                Student.user_id == user_id,
                TrainingSession.completed_at.isnot(None),
            )
            .all()
        ):
            dates.add(session.completed_at[:10])
        for conversation in self.db.query(TutorConversation).filter(TutorConversation.user_id == user_id).all():
            dates.add(conversation.updated_at[:10])
        return dates

    def _calendar_events(self, user_id: str, start_day: date, end_day: date) -> list[dict[str, Any]]:
        start, _ = self._day_bounds(start_day)
        _, end = self._day_bounds(end_day)
        events: list[dict[str, Any]] = []

        tasks = (
            self.db.query(DashboardTask)
            .filter(
                DashboardTask.user_id == user_id,
                DashboardTask.scheduled_date >= start_day.isoformat(),
                DashboardTask.scheduled_date <= end_day.isoformat(),
            )
            .order_by(DashboardTask.scheduled_date.asc(), DashboardTask.id.asc())
            .all()
        )
        for task in tasks:
            events.append(
                {
                    "id": f"task-{task.id}",
                    "type": "task",
                    "date": task.scheduled_date,
                    "time": "",
                    "title": task.task,
                    "subtitle": task.subject,
                    "completed": task.completed,
                }
            )

        conversations = (
            self.db.query(TutorConversation)
            .filter(
                TutorConversation.user_id == user_id,
                TutorConversation.updated_at >= start,
                TutorConversation.updated_at < end,
            )
            .order_by(TutorConversation.updated_at.asc())
            .all()
        )
        for conversation in conversations:
            events.append(
                {
                    "id": f"chat-{conversation.id}",
                    "type": "chat",
                    "date": conversation.updated_at[:10],
                    "time": conversation.updated_at[11:16] if len(conversation.updated_at) >= 16 else "",
                    "title": conversation.title,
                    "subtitle": "Tutor chat",
                    "completed": True,
                }
            )

        return events

    def _task_payload(self, item: DashboardTask) -> dict[str, Any]:
        return {
            "id": item.id,
            "user_id": item.user_id,
            "subject": item.subject,
            "task": item.task,
            "duration": item.duration,
            "priority": item.priority,
            "completed": item.completed,
            "scheduled_date": item.scheduled_date,
            "completed_at": item.completed_at,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _day_bounds(target_day: date) -> tuple[str, str]:
        start = datetime.combine(target_day, datetime.min.time())
        end = start + timedelta(days=1)
        return start.isoformat(), end.isoformat()

    @staticmethod
    def _now(now: datetime | None) -> str:
        return (now or datetime.now()).isoformat()
