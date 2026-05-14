"""训练相关 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.training_engine import TrainingEngine
from app.services.analytics import AnalyticsService
from app.models.session import LearningGoal

router = APIRouter(prefix="/api/training", tags=["training"], dependencies=[Depends(get_current_user)])


class SessionCreate(BaseModel):
    target_skills: Optional[List[str]] = None
    target_chapter: Optional[str] = None
    learning_goal: str = "consolidation"
    duration_minutes: int = 25


class AnswerSubmit(BaseModel):
    answer: str
    time_spent: float
    hint_count: int = 0


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
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/start", response_model=dict)
def start_session(session_id: int, db: Session = Depends(get_db)):
    """开始 Session"""
    engine = TrainingEngine(db)
    analytics = AnalyticsService(db)
    
    try:
        session = engine.start_session(session_id)
        
        analytics.log_behavior(
            log_type="session",
            action="start_session",
            session_id=session_id,
        )
        
        return {
            "session_id": session.id,
            "status": session.status.value,
            "started_at": session.started_at,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions/{session_id}/next", response_model=dict)
def get_next_question(
    session_id: int,
    exclude_question_ids: Optional[List[int]] = None,
    db: Session = Depends(get_db),
):
    """获取下一题"""
    engine = TrainingEngine(db)
    
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
):
    """提交答案"""
    engine = TrainingEngine(db)
    analytics = AnalyticsService(db)
    llm_service = None  # 可以注入
    
    try:
        result = engine.submit_answer(
            session_id=session_id,
            question_id=question_id,
            answer=answer_data.answer,
            time_spent=answer_data.time_spent,
            hint_count=answer_data.hint_count,
        )
        
        # 记录日志
        from app.models.session import TrainingSession
        from app.models.student import Student
        session = db.query(TrainingSession).filter(
            TrainingSession.id == session_id
        ).first()
        
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
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/complete", response_model=dict)
def complete_session(session_id: int, db: Session = Depends(get_db)):
    """完成 Session"""
    engine = TrainingEngine(db)
    analytics = AnalyticsService(db)
    
    try:
        session = engine.complete_session(session_id)
        
        analytics.log_behavior(
            log_type="session",
            action="complete_session",
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
        raise HTTPException(status_code=400, detail=str(e))

