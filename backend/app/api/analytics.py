"""分析相关 API"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(require_admin)])


@router.get("/question/{question_id}/stats", response_model=dict)
def get_question_stats(question_id: int, db: Session = Depends(get_db)):
    """获取题目统计"""
    service = AnalyticsService(db)
    stats = service.get_question_stats(question_id)

    if not stats:
        return {"message": "No statistics available for this question"}

    return stats


@router.get("/skill/{skill_id}/stats", response_model=dict)
def get_skill_stats(skill_id: str, db: Session = Depends(get_db)):
    """获取知识点统计"""
    service = AnalyticsService(db)
    stats = service.get_skill_stats(skill_id)

    if not stats:
        return {"message": "No statistics available for this skill"}

    return stats


@router.get("/system/stats", response_model=dict)
def get_system_stats(days: int = 7, db: Session = Depends(get_db)):
    """获取系统统计"""
    service = AnalyticsService(db)
    stats = service.get_system_stats(days)

    return stats


@router.get("/problematic-questions", response_model=dict)
def get_problematic_questions(
    min_attempts: int = 10,
    max_correct_rate: float = 0.3,
    db: Session = Depends(get_db),
):
    """获取有质量问题的题目"""
    service = AnalyticsService(db)
    questions = service.get_problematic_questions(min_attempts, max_correct_rate)

    return {
        "count": len(questions),
        "questions": questions,
    }
