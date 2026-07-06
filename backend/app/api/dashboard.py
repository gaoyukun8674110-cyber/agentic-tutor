"""Dashboard API endpoints."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])
TaskPriority = Literal["high", "medium", "low"]


class DashboardTaskCreate(BaseModel):
    subject: str = "Study"
    task: str
    duration: int = Field(default=25, ge=1, le=600)
    priority: TaskPriority = "medium"
    scheduled_date: str | None = None


class DashboardTaskUpdate(BaseModel):
    subject: str | None = None
    task: str | None = None
    duration: int | None = Field(default=None, ge=1, le=600)
    priority: TaskPriority | None = None
    completed: bool | None = None
    scheduled_date: str | None = None


class PomodoroLogCreate(BaseModel):
    mode: str = "work"
    duration_minutes: int = Field(default=25, ge=1, le=600)


@router.get("/summary", response_model=dict)
def dashboard_summary(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return persisted dashboard data for the current user."""
    service = DashboardService(db)
    return service.get_summary(user_id=current_user.username, days=days)


@router.get("/tasks", response_model=dict)
def dashboard_tasks(
    scheduled_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List dashboard tasks from the backend database."""
    service = DashboardService(db)
    return {"tasks": service.list_tasks(user_id=current_user.username, scheduled_date=scheduled_date)}


@router.post("/tasks", response_model=dict)
def create_dashboard_task(
    request: DashboardTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a persisted dashboard task."""
    service = DashboardService(db)
    scheduled_date = request.scheduled_date or date.today().isoformat()
    return service.create_task(
        user_id=current_user.username,
        subject=request.subject,
        task=request.task,
        duration=request.duration,
        priority=request.priority,
        scheduled_date=scheduled_date,
    )


@router.patch("/tasks/{task_id}", response_model=dict)
def update_dashboard_task(
    task_id: int,
    request: DashboardTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a persisted dashboard task."""
    service = DashboardService(db)
    try:
        return service.update_task(
            task_id=task_id,
            user_id=current_user.username,
            subject=request.subject,
            task=request.task,
            duration=request.duration,
            priority=request.priority,
            completed=request.completed,
            scheduled_date=request.scheduled_date,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/tasks/{task_id}", response_model=dict)
def delete_dashboard_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a persisted dashboard task."""
    service = DashboardService(db)
    if not service.delete_task(task_id=task_id, user_id=current_user.username):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}


@router.post("/pomodoro", response_model=dict)
def log_pomodoro(
    request: PomodoroLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist a completed Pomodoro/focus block."""
    service = DashboardService(db)
    return service.log_pomodoro(
        user_id=current_user.username,
        mode=request.mode,
        duration_minutes=request.duration_minutes,
    )
