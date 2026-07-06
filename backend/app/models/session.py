"""训练 Session 相关数据模型"""

import enum

from sqlalchemy import JSON, Boolean, Column, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import relationship

from app.database import Base


class SessionStatus(str, enum.Enum):
    """Session 状态"""

    PENDING = "pending"  # 待开始
    IN_PROGRESS = "in_progress"  # 进行中
    PAUSED = "paused"  # 暂停
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


class LearningGoal(str, enum.Enum):
    """学习目标"""

    BEGINNER = "beginner"  # 入门
    CONSOLIDATION = "consolidation"  # 巩固
    EXAM_PREP = "exam_prep"  # 考前冲刺


class TrainingSession(Base):
    """训练 Session 表"""

    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)

    # Session 配置
    target_skills = Column(JSON, nullable=True)  # 目标知识点列表
    target_chapter = Column(String(100), nullable=True)  # 目标章节
    learning_goal = Column(SQLEnum(LearningGoal), nullable=False)
    duration_minutes = Column(Integer, nullable=False)  # 预计时长（分钟）

    # 状态
    status = Column(SQLEnum(SessionStatus), default=SessionStatus.PENDING)
    started_at = Column(String(50), nullable=True)
    paused_at = Column(String(50), nullable=True)
    completed_at = Column(String(50), nullable=True)

    # 统计
    total_questions = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)
    hint_usage_count = Column(Integer, default=0)
    average_time = Column(Float, default=0.0)

    # Session 计划（训练引擎生成的粗框架）
    session_plan = Column(JSON, nullable=True)  # 例如：{"phases": [{"type": "warmup", "duration": 10}, ...]}

    # 关系
    questions = relationship("SessionQuestion", back_populates="session", cascade="all, delete-orphan")

    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)


class SessionQuestion(Base):
    """Session 中的题目记录"""

    __tablename__ = "session_questions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("training_sessions.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)

    # 题目在 Session 中的顺序
    sequence = Column(Integer, nullable=False)

    # 出题原因（训练引擎记录）
    reason = Column(String(200), nullable=True)  # 例如："连续做对3题，升难度"、"复习旧知识点"

    # 是否已回答
    is_answered = Column(Boolean, default=False)
    answered_at = Column(String(50), nullable=True)

    session = relationship("TrainingSession", back_populates="questions")
    created_at = Column(String(50), nullable=False)
