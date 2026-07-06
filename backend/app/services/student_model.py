"""学生模型服务 - 掌握度维护、学习画像、推荐算法"""

from datetime import datetime
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.question import QuestionSkill
from app.models.student import Student, StudentMastery


class StudentModelService:
    """学生模型服务"""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_student(self, user_id: str, username: str | None = None) -> Student:
        """获取或创建学生"""
        student = self.db.query(Student).filter(Student.user_id == user_id).first()
        if not student:
            now = datetime.now().isoformat()
            student = Student(
                user_id=user_id,
                username=username,
                created_at=now,
                updated_at=now,
            )
            self.db.add(student)
            self.db.commit()
            self.db.refresh(student)
        return student

    def get_mastery(self, student_id: int, skill_id: str) -> StudentMastery | None:
        """获取某个知识点的掌握度"""
        return (
            self.db.query(StudentMastery)
            .filter(
                and_(
                    StudentMastery.student_id == student_id,
                    StudentMastery.skill_id == skill_id,
                )
            )
            .first()
        )

    def get_all_masteries(self, student_id: int) -> list[StudentMastery]:
        """获取所有知识点的掌握度"""
        return self.db.query(StudentMastery).filter(StudentMastery.student_id == student_id).all()

    def update_mastery_from_answer(
        self,
        student_id: int,
        question_id: int,
        is_correct: bool,
        time_spent: float,
        hint_count: int,
        error_reason: str | None = None,
    ) -> dict[str, Any]:
        """根据答题结果更新掌握度"""
        # 获取题目关联的知识点
        question_skills = self.db.query(QuestionSkill).filter(QuestionSkill.question_id == question_id).all()

        if not question_skills:
            return {"updated_skills": []}

        updated_skills = []
        now = datetime.now().isoformat()

        for qs in question_skills:
            skill_id = qs.skill_id
            skill_name = qs.skill_name
            weight = qs.weight

            # 获取或创建掌握度记录
            mastery = self.get_mastery(student_id, skill_id)
            if not mastery:
                mastery = StudentMastery(
                    student_id=student_id,
                    skill_id=skill_id,
                    skill_name=skill_name,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(mastery)

            # 更新统计数据
            mastery.total_attempts += 1
            if is_correct:
                mastery.total_correct += 1

            # 计算掌握度分数（简单模型，v1）
            # 可以后续升级为 BKT/DKT 等
            mastery_score = self._calculate_mastery_score(
                mastery.total_attempts,
                mastery.total_correct,
                is_correct,
                time_spent,
                hint_count,
                mastery.mastery_score,
                weight,
            )
            mastery.mastery_score = mastery_score

            # 更新平均用时（移动平均）
            if mastery.average_time == 0:
                mastery.average_time = time_spent
            else:
                mastery.average_time = mastery.average_time * 0.7 + time_spent * 0.3

            # 更新 hint 使用率
            if mastery.total_attempts > 0:
                mastery.hint_usage_rate = (
                    mastery.hint_usage_rate * (mastery.total_attempts - 1) + (1 if hint_count > 0 else 0)
                ) / mastery.total_attempts

            # 更新最近正确率（最近10次）
            # 这里简化处理，实际可以从 StudentAnswer 表统计
            if mastery.total_attempts > 0:
                mastery.recent_correct_rate = mastery.total_correct / mastery.total_attempts

            mastery.last_practiced_at = now
            mastery.updated_at = now

            updated_skills.append(
                {
                    "skill_id": skill_id,
                    "skill_name": skill_name,
                    "mastery_score": mastery_score,
                }
            )

        self.db.commit()
        return {"updated_skills": updated_skills}

    def _calculate_mastery_score(
        self,
        total_attempts: int,
        total_correct: int,
        is_correct: bool,
        time_spent: float,
        hint_count: int,
        current_score: float,
        weight: float,
    ) -> float:
        """计算掌握度分数（0-1）"""
        # 基础正确率
        base_rate = total_correct / total_attempts if total_attempts > 0 else 0.0

        # 本次答题的影响
        if is_correct:
            # 做对了：根据用时和 hint 使用情况调整
            if hint_count == 0:
                delta = 0.1 * weight  # 无 hint 做对，大幅提升
            elif hint_count == 1:
                delta = 0.05 * weight  # 用1次 hint，小幅提升
            else:
                delta = 0.02 * weight  # 多次 hint，微幅提升
        else:
            # 做错了：下降
            delta = -0.05 * weight

        # 应用变化，限制在 0-1 之间
        new_score = current_score + delta
        new_score = max(0.0, min(1.0, new_score))

        # 如果尝试次数足够多，向实际正确率收敛
        if total_attempts >= 5:
            new_score = new_score * 0.7 + base_rate * 0.3

        return new_score

    def get_recommended_skills(
        self,
        student_id: int,
        target_skills: list[str] | None = None,
    ) -> dict[str, Any]:
        """获取推荐出题范围（Zone of Proximal Development）"""
        masteries = self.get_all_masteries(student_id)

        if not masteries:
            # 没有历史数据，返回目标知识点
            return {
                "recommended_skills": target_skills or [],
                "difficulty_suggestion": "easy",
            }

        # 分析掌握度分布
        recommended = []
        review_skills = []
        too_hard_skills = []

        for mastery in masteries:
            score = mastery.mastery_score

            if score < 0.3:
                # 掌握度很低，可能太难
                too_hard_skills.append(
                    {
                        "skill_id": mastery.skill_id,
                        "skill_name": mastery.skill_name,
                        "mastery_score": score,
                    }
                )
            elif 0.3 <= score < 0.7:
                # 适合练习的区间（最近发展区）
                recommended.append(
                    {
                        "skill_id": mastery.skill_id,
                        "skill_name": mastery.skill_name,
                        "mastery_score": score,
                    }
                )
            elif score >= 0.7:
                # 掌握较好，适合复习
                review_skills.append(
                    {
                        "skill_id": mastery.skill_id,
                        "skill_name": mastery.skill_name,
                        "mastery_score": score,
                    }
                )

        # 如果指定了目标知识点，优先考虑
        if target_skills:
            target_masteries = [m for m in masteries if m.skill_id in target_skills]
            if target_masteries:
                recommended = target_masteries

        return {
            "recommended_skills": [s["skill_id"] for s in recommended],
            "review_skills": [s["skill_id"] for s in review_skills],
            "too_hard_skills": [s["skill_id"] for s in too_hard_skills],
            "mastery_map": {m.skill_id: m.mastery_score for m in masteries},
        }

    def get_learning_report(self, student_id: int) -> dict[str, Any]:
        """获取学习报告"""
        masteries = self.get_all_masteries(student_id)
        student = self.db.query(Student).filter(Student.id == student_id).first()

        if not student:
            return {}

        # 按掌握度排序
        sorted_masteries = sorted(masteries, key=lambda m: m.mastery_score)

        # 找出弱项（掌握度最低的3个）
        weak_skills = [
            {
                "skill_id": m.skill_id,
                "skill_name": m.skill_name,
                "mastery_score": m.mastery_score,
            }
            for m in sorted_masteries[:3]
        ]

        # 计算总体统计
        total_skills = len(masteries)
        avg_mastery = sum(m.mastery_score for m in masteries) / total_skills if total_skills > 0 else 0.0

        return {
            "student_id": student_id,
            "total_skills_practiced": total_skills,
            "average_mastery": avg_mastery,
            "weak_skills": weak_skills,
            "mastery_distribution": {
                "excellent": len([m for m in masteries if m.mastery_score >= 0.8]),
                "good": len([m for m in masteries if 0.6 <= m.mastery_score < 0.8]),
                "fair": len([m for m in masteries if 0.4 <= m.mastery_score < 0.6]),
                "poor": len([m for m in masteries if m.mastery_score < 0.4]),
            },
            "total_sessions": student.total_sessions,
            "total_questions": student.total_questions,
            "overall_correct_rate": (
                student.total_correct / student.total_questions if student.total_questions > 0 else 0.0
            ),
        }
