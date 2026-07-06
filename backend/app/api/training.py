"""训练相关 API"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.session import LearningGoal, TrainingSession
from app.models.student import Student
from app.models.user import User
from app.services.analytics import AnalyticsService
from app.services.training_engine import TrainingEngine

router = APIRouter(prefix="/api/training", tags=["training"], dependencies=[Depends(get_current_user)])


class SessionCreate(BaseModel):
    target_skills: list[str] | None = None
    target_chapter: str | None = None
    learning_goal: str = "consolidation"
    duration_minutes: int = 25


class AnswerSubmit(BaseModel):
    answer: str
    time_spent: float
    hint_count: int = 0


def _require_session(session_id: int, current_user: User, db: Session) -> TrainingSession:
    session = (
        db.query(TrainingSession)
        .join(Student, Student.id == TrainingSession.student_id)
        .filter(TrainingSession.id == session_id, Student.user_id == current_user.username)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions", response_model=dict)
def create_session(
    session_data: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建训练 Session"""
    engine = TrainingEngine(db)
    analytics = AnalyticsService(db)

    # 获取或创建学生
    from app.services.student_model import StudentModelService

    student_service = StudentModelService(db)
    student = student_service.get_or_create_student(current_user.username)

    try:
        session = engine.create_session(
            student_id=student.id,
            target_skills=session_data.target_skills,
            target_chapter=session_data.target_chapter,
            learning_goal=LearningGoal(session_data.learning_goal),
            duration_minutes=session_data.duration_minutes,
        )

        analytics.log_behavior(
            log_type="session",
            action="create_session",
            user_id=current_user.username,
            session_id=session.id,
        )

        return {
            "session_id": session.id,
            "status": session.status.value,
            "message": "Session created successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/sessions/{session_id}/start", response_model=dict)
def start_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """开始 Session"""
    engine = TrainingEngine(db)
    analytics = AnalyticsService(db)
    _require_session(session_id, current_user, db)

    try:
        session = engine.start_session(session_id)

        analytics.log_behavior(
            log_type="session",
            action="start_session",
            user_id=current_user.username,
            session_id=session_id,
        )

        return {
            "session_id": session.id,
            "status": session.status.value,
            "started_at": session.started_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/sessions/{session_id}/next", response_model=dict)
def get_next_question(
    session_id: int,
    exclude_question_ids: list[int] | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取下一题"""
    engine = TrainingEngine(db)
    _require_session(session_id, current_user, db)

    result = engine.get_next_question(session_id, exclude_question_ids)

    if not result:
        raise HTTPException(status_code=404, detail="No more questions or session ended")

    return result


@router.post("/sessions/{session_id}/answer", response_model=dict)
def submit_answer(
    session_id: int,
    question_id: int,
    answer_data: AnswerSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交答案"""
    engine = TrainingEngine(db)
    analytics = AnalyticsService(db)
    session = _require_session(session_id, current_user, db)

    try:
        result = engine.submit_answer(
            session_id=session_id,
            question_id=question_id,
            answer=answer_data.answer,
            time_spent=answer_data.time_spent,
            hint_count=answer_data.hint_count,
        )

        # 记录日志
        student = db.query(Student).filter(Student.id == session.student_id).first() if session else None

        analytics.log_answer(
            user_id=student.user_id if student else None,
            session_id=session_id,
            question_id=question_id,
            is_correct=result["is_correct"],
            time_spent=answer_data.time_spent,
            hint_count=answer_data.hint_count,
        )

        # 更新题目统计
        analytics.update_question_stat(
            question_id=question_id,
            is_correct=result["is_correct"],
            time_spent=answer_data.time_spent,
            hint_count=answer_data.hint_count,
        )

        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/sessions/{session_id}/complete", response_model=dict)
def complete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """完成 Session"""
    engine = TrainingEngine(db)
    analytics = AnalyticsService(db)
    _require_session(session_id, current_user, db)

    try:
        session = engine.complete_session(session_id)

        analytics.log_behavior(
            log_type="session",
            action="complete_session",
            user_id=current_user.username,
            session_id=session_id,
        )

        return {
            "session_id": session.id,
            "status": session.status.value,
            "completed_at": session.completed_at,
            "total_questions": session.total_questions,
            "correct_count": session.correct_count,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
