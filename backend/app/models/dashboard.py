"""Dashboard persistence models."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String

from app.database import Base


class DashboardTask(Base):
    """A planned study task shown on the dashboard."""

    __tablename__ = "dashboard_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), ForeignKey("users.username", ondelete="CASCADE"), nullable=False, index=True)
    subject = Column(String(120), nullable=False)
    task = Column(String(500), nullable=False)
    duration = Column(Integer, default=25, nullable=False)
    priority = Column(String(20), default="medium", nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    scheduled_date = Column(String(10), nullable=False, index=True)
    completed_at = Column(String(50), nullable=True, index=True)
    created_at = Column(String(50), nullable=False, index=True)
    updated_at = Column(String(50), nullable=False, index=True)


class PomodoroLog(Base):
    """One completed Pomodoro/focus block."""

    __tablename__ = "pomodoro_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), ForeignKey("users.username", ondelete="CASCADE"), nullable=False, index=True)
    mode = Column(String(30), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    completed_at = Column(String(50), nullable=False, index=True)
    created_at = Column(String(50), nullable=False, index=True)
