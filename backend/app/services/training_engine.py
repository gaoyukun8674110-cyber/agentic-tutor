"""训练引擎 - Session 编排、动态出题、教学策略"""

import random
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.question import DifficultyLevel
from app.models.session import LearningGoal, SessionQuestion, SessionStatus, TrainingSession
from app.models.student import Student, StudentAnswer
from app.services.pomodoro import PomodoroService
from app.services.question_bank import QuestionBankService
from app.services.student_model import StudentModelService


class TrainingEngine:
    """训练引擎"""

    def __init__(self, db: Session):
        self.db = db
        self.question_bank = QuestionBankService(db)
        self.student_model = StudentModelService(db)
        self.pomodoro = PomodoroService(db)

    def create_session(
        self,
        student_id: int,
        target_skills: list[str] | None = None,
        target_chapter: str | None = None,
        learning_goal: LearningGoal = LearningGoal.CONSOLIDATION,
        duration_minutes: int = 25,
    ) -> TrainingSession:
        """创建训练 Session"""
        now = datetime.now().isoformat()

        # 获取学生掌握度画像
        mastery_info = self.student_model.get_recommended_skills(student_id, target_skills)

        # 生成 Session 计划（粗框架）
        session_plan = self._generate_session_plan(
            duration_minutes,
            learning_goal,
            mastery_info,
        )

        session = TrainingSession(
            student_id=student_id,
            target_skills=target_skills,
            target_chapter=target_chapter,
            learning_goal=learning_goal,
            duration_minutes=duration_minutes,
            status=SessionStatus.PENDING,
            session_plan=session_plan,
            created_at=now,
            updated_at=now,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        return session

    def start_session(self, session_id: int) -> TrainingSession:
        """开始 Session"""
        session = self.db.query(TrainingSession).filter(TrainingSession.id == session_id).first()

        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.status = SessionStatus.IN_PROGRESS
        session.started_at = datetime.now().isoformat()
        session.updated_at = datetime.now().isoformat()
        self.db.commit()
        self.db.refresh(session)

        return session

    def get_next_question(
        self,
        session_id: int,
        exclude_question_ids: list[int] | None = None,
    ) -> dict[str, Any] | None:
        """获取下一题（核心逻辑）"""
        session = self.db.query(TrainingSession).filter(TrainingSession.id == session_id).first()

        if not session or session.status != SessionStatus.IN_PROGRESS:
            return None

        # 检查时间
        time_info = self.pomodoro.get_session_time_remaining(session_id)
        if not time_info or time_info["remaining_minutes"] <= 0:
            return None

        # 检查是否应该收尾
        if self.pomodoro.should_wrap_up(session_id, threshold_minutes=3):
            return {"action": "wrap_up", "message": "时间快到了，进入总结阶段"}

        # 获取已做过的题目
        answered_questions = (
            self.db.query(SessionQuestion)
            .filter(
                SessionQuestion.session_id == session_id,
                SessionQuestion.is_answered.is_(True),
            )
            .all()
        )

        answered_q_ids = [sq.question_id for sq in answered_questions]
        if exclude_question_ids:
            answered_q_ids.extend(exclude_question_ids)

        # 分析当前 Session 表现
        recent_answers = self._get_recent_answers(session_id, limit=5)

        # 决定出题策略
        strategy = self._decide_strategy(
            session,
            recent_answers,
            time_info,
        )

        # 从题库检索候选题
        candidate_questions = self.question_bank.search_questions(
            skill_ids=strategy["target_skills"],
            difficulty=strategy["difficulty"],
            exclude_question_ids=answered_q_ids,
            limit=10,
            random=True,
        )

        if not candidate_questions:
            return None

        # 选择一题
        selected_question = random.choice(candidate_questions)

        # 记录到 Session
        sequence = len(answered_questions) + 1
        session_question = SessionQuestion(
            session_id=session_id,
            question_id=selected_question.id,
            sequence=sequence,
            reason=strategy["reason"],
            created_at=datetime.now().isoformat(),
        )
        self.db.add(session_question)
        self.db.commit()

        return {
            "question_id": selected_question.id,
            "content": selected_question.content,
            "options": selected_question.options,
            "question_type": selected_question.question_type.value,
            "sequence": sequence,
            "reason": strategy["reason"],
        }

    def submit_answer(
        self,
        session_id: int,
        question_id: int,
        answer: str,
        time_spent: float,
        hint_count: int = 0,
    ) -> dict[str, Any]:
        """提交答案并处理结果"""
        # 获取题目和标准答案
        question = self.question_bank.get_question(question_id)
        if not question:
            return {"error": "Question not found"}

        # 判题（简化：实际应该用更复杂的逻辑）
        is_correct = self._judge_answer(question, answer)

        # 更新 Session 统计
        session = self.db.query(TrainingSession).filter(TrainingSession.id == session_id).first()

        session.total_questions += 1
        if is_correct:
            session.correct_count += 1
        session.hint_usage_count += hint_count

        # 更新 SessionQuestion
        session_question = (
            self.db.query(SessionQuestion)
            .filter(
                SessionQuestion.session_id == session_id,
                SessionQuestion.question_id == question_id,
            )
            .first()
        )

        if session_question:
            session_question.is_answered = True
            session_question.answered_at = datetime.now().isoformat()

        # 记录答题
        student_answer = StudentAnswer(
            student_id=session.student_id,
            question_id=question_id,
            session_id=session_id,
            answer=answer,
            is_correct=is_correct,
            time_spent=time_spent,
            hint_count=hint_count,
            created_at=datetime.now().isoformat(),
        )
        self.db.add(student_answer)

        # 更新学生模型
        mastery_update = self.student_model.update_mastery_from_answer(
            student_id=session.student_id,
            question_id=question_id,
            is_correct=is_correct,
            time_spent=time_spent,
            hint_count=hint_count,
        )

        self.db.commit()

        # 决定下一步
        next_action = self._decide_next_action(session_id, is_correct, recent_answers=[])

        return {
            "is_correct": is_correct,
            "correct_answer": question.correct_answer,
            "mastery_update": mastery_update,
            "next_action": next_action,
        }

    def _generate_session_plan(
        self,
        duration_minutes: int,
        learning_goal: LearningGoal,
        mastery_info: dict[str, Any],
    ) -> dict[str, Any]:
        """生成 Session 计划"""
        if learning_goal == LearningGoal.BEGINNER:
            # 入门：更多基础题
            phases = [
                {"type": "warmup", "duration": duration_minutes * 0.3, "difficulty": "easy"},
                {"type": "practice", "duration": duration_minutes * 0.5, "difficulty": "easy"},
                {"type": "review", "duration": duration_minutes * 0.2, "difficulty": "easy"},
            ]
        elif learning_goal == LearningGoal.EXAM_PREP:
            # 考前冲刺：更多综合题
            phases = [
                {"type": "warmup", "duration": duration_minutes * 0.2, "difficulty": "medium"},
                {"type": "practice", "duration": duration_minutes * 0.6, "difficulty": "hard"},
                {"type": "review", "duration": duration_minutes * 0.2, "difficulty": "medium"},
            ]
        else:
            # 巩固：平衡
            phases = [
                {"type": "warmup", "duration": duration_minutes * 0.25, "difficulty": "easy"},
                {"type": "practice", "duration": duration_minutes * 0.55, "difficulty": "medium"},
                {"type": "review", "duration": duration_minutes * 0.2, "difficulty": "medium"},
            ]

        return {"phases": phases, "target_skills": mastery_info.get("recommended_skills", [])}

    def _decide_strategy(
        self,
        session: TrainingSession,
        recent_answers: list[dict[str, Any]],
        time_info: dict[str, Any],
    ) -> dict[str, Any]:
        """决定出题策略"""
        # 分析最近表现
        if len(recent_answers) >= 3:
            consecutive_correct = sum(1 for a in recent_answers[-3:] if a["is_correct"])
            consecutive_errors = sum(1 for a in recent_answers[-3:] if not a["is_correct"])
        else:
            consecutive_correct = 0
            consecutive_errors = 0

        # 获取推荐知识点
        mastery_info = self.student_model.get_recommended_skills(
            session.student_id,
            session.target_skills,
        )

        target_skills = mastery_info.get("recommended_skills", [])

        # 决定难度
        if consecutive_errors >= 3:
            difficulty = DifficultyLevel.EASY
            reason = "连续错3题，降低难度"
        elif consecutive_correct >= 3:
            difficulty = DifficultyLevel.HARD
            reason = "连续对3题，提高难度"
        else:
            difficulty = DifficultyLevel.MEDIUM
            reason = "正常出题"

        # 检查是否需要复习
        if time_info["progress_percent"] > 80:
            # 快结束了，插入复习题
            review_skills = mastery_info.get("review_skills", [])
            if review_skills:
                target_skills = review_skills[:2]
                reason = "Session 快结束，复习旧知识点"

        return {
            "target_skills": target_skills,
            "difficulty": difficulty,
            "reason": reason,
        }

    def _get_recent_answers(self, session_id: int, limit: int = 5) -> list[dict[str, Any]]:
        """获取最近的答题记录"""
        answers = (
            self.db.query(StudentAnswer)
            .filter(StudentAnswer.session_id == session_id)
            .order_by(StudentAnswer.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "is_correct": a.is_correct,
                "time_spent": a.time_spent,
            }
            for a in reversed(answers)  # 按时间正序
        ]

    def _judge_answer(self, question, answer: str) -> bool:
        """判题（简化实现）"""
        # 实际应该用更复杂的逻辑，比如调用数学工具验证
        return answer.strip().lower() == question.correct_answer.strip().lower()

    def _decide_next_action(
        self,
        session_id: int,
        is_correct: bool,
        recent_answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """决定下一步动作"""
        # 检查疲劳
        fatigue_info = self.pomodoro.check_fatigue_signals(session_id, recent_answers)

        if fatigue_info["is_fatigued"]:
            return {
                "action": "suggest_break",
                "message": "检测到疲劳信号，建议休息",
            }

        if is_correct:
            return {
                "action": "continue",
                "message": "继续下一题",
            }
        else:
            return {
                "action": "continue",
                "message": "继续练习，建议巩固类似题目",
            }

    def complete_session(self, session_id: int) -> TrainingSession:
        """完成 Session"""
        session = self.db.query(TrainingSession).filter(TrainingSession.id == session_id).first()

        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.status = SessionStatus.COMPLETED
        session.completed_at = datetime.now().isoformat()
        session.updated_at = datetime.now().isoformat()

        # 更新学生统计
        student = self.db.query(Student).filter(Student.id == session.student_id).first()
        if student:
            student.total_sessions += 1
            student.total_questions += session.total_questions
            student.total_correct += session.correct_count

        self.db.commit()
        self.db.refresh(session)

        return session
