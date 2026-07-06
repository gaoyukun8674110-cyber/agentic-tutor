"""题库服务 - 题目存储、检索、标准解管理"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.question import (
    DifficultyLevel,
    PrerequisiteSkill,
    Question,
    QuestionSkill,
    QuestionStatus,
    QuestionTag,
    QuestionType,
)


class QuestionBankService:
    """题库服务"""

    def __init__(self, db: Session):
        self.db = db

    def create_question(
        self,
        content: str,
        correct_answer: str,
        standard_solution: str,
        question_type: QuestionType,
        difficulty: DifficultyLevel,
        skills: list[dict[str, Any]],  # [{"skill_id": "xxx", "skill_name": "xxx", "weight": 1.0}]
        tags: list[str] | None = None,
        options: list[str] | None = None,
        solution_steps: list[dict] | None = None,
        source: str | None = None,
        chapter: str | None = None,
        prerequisites: list[str] | None = None,
    ) -> Question:
        """创建题目"""
        now = datetime.now().isoformat()

        question = Question(
            content=content,
            options=options,
            correct_answer=correct_answer,
            standard_solution=standard_solution,
            solution_steps=solution_steps,
            question_type=question_type,
            difficulty=difficulty,
            status=QuestionStatus.ACTIVE,
            source=source,
            chapter=chapter,
            created_at=now,
            updated_at=now,
        )
        self.db.add(question)
        self.db.flush()

        # 添加标签
        if tags:
            for tag in tags:
                self.db.add(QuestionTag(question_id=question.id, tag=tag))

        # 添加知识点关联
        for skill in skills:
            self.db.add(
                QuestionSkill(
                    question_id=question.id,
                    skill_id=skill["skill_id"],
                    skill_name=skill["skill_name"],
                    weight=skill.get("weight", 1.0),
                )
            )

        # 添加先修知识点
        if prerequisites:
            for skill_id in prerequisites:
                self.db.add(
                    PrerequisiteSkill(
                        question_id=question.id,
                        prerequisite_skill_id=skill_id,
                    )
                )

        self.db.commit()
        self.db.refresh(question)
        return question

    def get_question(self, question_id: int) -> Question | None:
        """获取单个题目"""
        return self.db.query(Question).filter(Question.id == question_id).first()

    def update_question(self, question_id: int, **kwargs) -> Question | None:
        """更新题目"""
        question = self.get_question(question_id)
        if not question:
            return None

        # 更新字段
        for key, value in kwargs.items():
            if hasattr(question, key):
                setattr(question, key, value)

        question.updated_at = datetime.now().isoformat()
        self.db.commit()
        self.db.refresh(question)
        return question

    def delete_question(self, question_id: int) -> bool:
        """删除题目（软删除，改为下线状态）"""
        question = self.get_question(question_id)
        if not question:
            return False

        question.status = QuestionStatus.INACTIVE
        question.updated_at = datetime.now().isoformat()
        self.db.commit()
        return True

    def search_questions(
        self,
        skill_ids: list[str] | None = None,
        difficulty: DifficultyLevel | None = None,
        question_type: QuestionType | None = None,
        chapter: str | None = None,
        exclude_question_ids: list[int] | None = None,
        limit: int | None = None,
        random: bool = False,
    ) -> list[Question]:
        """按条件检索题目"""
        query = self.db.query(Question).filter(Question.status == QuestionStatus.ACTIVE)

        # 按知识点过滤
        if skill_ids:
            query = query.join(QuestionSkill).filter(QuestionSkill.skill_id.in_(skill_ids))

        # 按难度过滤
        if difficulty:
            query = query.filter(Question.difficulty == difficulty)

        # 按题型过滤
        if question_type:
            query = query.filter(Question.question_type == question_type)

        # 按章节过滤
        if chapter:
            query = query.filter(Question.chapter == chapter)

        # 排除已做过的题
        if exclude_question_ids:
            query = query.filter(~Question.id.in_(exclude_question_ids))

        # 随机排序
        if random:
            query = query.order_by(Question.id)  # SQLite 简单随机，生产环境可用 func.random()

        # 限制数量
        if limit:
            query = query.limit(limit)

        return query.all()

    def get_standard_solution(self, question_id: int) -> dict[str, Any] | None:
        """获取标准解和分步解"""
        question = self.get_question(question_id)
        if not question:
            return None

        return {
            "correct_answer": question.correct_answer,
            "standard_solution": question.standard_solution,
            "solution_steps": question.solution_steps,
        }

    def get_questions_by_ids(self, question_ids: list[int]) -> list[Question]:
        """批量获取题目"""
        return self.db.query(Question).filter(Question.id.in_(question_ids)).all()
