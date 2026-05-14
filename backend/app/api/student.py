"""学生相关 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.deps import get_current_user, require_matching_user
from app.database import get_db
from app.models.user import User
from app.services.student_model import StudentModelService
from app.services.pomodoro import PomodoroService

router = APIRouter(prefix="/api/student", tags=["student"], dependencies=[Depends(get_current_user)])


@router.get("/{user_id}/mastery", response_model=dict)
def get_mastery(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取掌握度"""
    require_matching_user(user_id, current_user)
    service = StudentModelService(db)
    student = service.get_or_create_student(user_id)
    
    masteries = service.get_all_masteries(student.id)
    
    return {
        "user_id": user_id,
        "masteries": [
            {
                "skill_id": m.skill_id,
                "skill_name": m.skill_name,
                "mastery_score": m.mastery_score,
                "total_attempts": m.total_attempts,
                "total_correct": m.total_correct,
                "recent_correct_rate": m.recent_correct_rate,
            }
            for m in masteries
        ],
    }


@router.get("/{user_id}/recommendations", response_model=dict)
def get_recommendations(
    user_id: str,
    target_skills: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取推荐出题范围"""
    require_matching_user(user_id, current_user)
    service = StudentModelService(db)
    student = service.get_or_create_student(user_id)
    
    target_list = target_skills.split(",") if target_skills else None
    
    recommendations = service.get_recommended_skills(student.id, target_list)
    
    return recommendations


@router.get("/{user_id}/report", response_model=dict)
def get_learning_report(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取学习报告"""
    require_matching_user(user_id, current_user)
    service = StudentModelService(db)
    student = service.get_or_create_student(user_id)
    
    report = service.get_learning_report(student.id)
    
    return report


@router.get("/{user_id}/review-plan", response_model=dict)
def get_review_plan(
    user_id: str,
    days_ahead: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取复习计划"""
    require_matching_user(user_id, current_user)
    service = StudentModelService(db)
    pomodoro = PomodoroService(db)
    student = service.get_or_create_student(user_id)
    
    plan = pomodoro.get_spaced_repetition_plan(student.id, days_ahead)
    
    return {
        "user_id": user_id,
        "review_plan": plan,
    }

