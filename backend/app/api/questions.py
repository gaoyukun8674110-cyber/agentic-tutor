"""题目相关 API"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.question import DifficultyLevel, QuestionType
from app.services.question_bank import QuestionBankService

router = APIRouter(prefix="/api/questions", tags=["questions"], dependencies=[Depends(get_current_user)])


class QuestionCreate(BaseModel):
    content: str
    correct_answer: str
    standard_solution: str
    question_type: str
    difficulty: str
    skills: list[dict]
    tags: list[str] | None = None
    options: list[str] | None = None
    solution_steps: list[dict] | None = None
    source: str | None = None
    chapter: str | None = None
    prerequisites: list[str] | None = None


class QuestionSearch(BaseModel):
    skill_ids: list[str] | None = None
    difficulty: str | None = None
    question_type: str | None = None
    chapter: str | None = None
    exclude_question_ids: list[int] | None = None
    limit: int | None = None
    random: bool = False


@router.post("/", response_model=dict)
def create_question(question: QuestionCreate, db: Session = Depends(get_db)):
    """创建题目"""
    service = QuestionBankService(db)

    try:
        q = service.create_question(
            content=question.content,
            correct_answer=question.correct_answer,
            standard_solution=question.standard_solution,
            question_type=QuestionType(question.question_type),
            difficulty=DifficultyLevel(question.difficulty),
            skills=question.skills,
            tags=question.tags,
            options=question.options,
            solution_steps=question.solution_steps,
            source=question.source,
            chapter=question.chapter,
            prerequisites=question.prerequisites,
        )
        return {"id": q.id, "message": "Question created successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{question_id}", response_model=dict)
def get_question(question_id: int, db: Session = Depends(get_db)):
    """获取题目"""
    service = QuestionBankService(db)
    question = service.get_question(question_id)

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    return {
        "id": question.id,
        "content": question.content,
        "options": question.options,
        "question_type": question.question_type.value,
        "difficulty": question.difficulty.value,
        "skills": [{"skill_id": s.skill_id, "skill_name": s.skill_name} for s in question.skills],
        "tags": [t.tag for t in question.tags],
    }


@router.get("/{question_id}/solution", response_model=dict)
def get_solution(question_id: int, db: Session = Depends(get_db)):
    """获取标准解"""
    service = QuestionBankService(db)
    solution = service.get_standard_solution(question_id)

    if not solution:
        raise HTTPException(status_code=404, detail="Question not found")

    return solution


@router.post("/search", response_model=dict)
def search_questions(search: QuestionSearch, db: Session = Depends(get_db)):
    """搜索题目"""
    service = QuestionBankService(db)

    questions = service.search_questions(
        skill_ids=search.skill_ids,
        difficulty=DifficultyLevel(search.difficulty) if search.difficulty else None,
        question_type=QuestionType(search.question_type) if search.question_type else None,
        chapter=search.chapter,
        exclude_question_ids=search.exclude_question_ids,
        limit=search.limit,
        random=search.random,
    )

    return {
        "count": len(questions),
        "questions": [
            {
                "id": q.id,
                "content": q.content,
                "question_type": q.question_type.value,
                "difficulty": q.difficulty.value,
            }
            for q in questions
        ],
    }
