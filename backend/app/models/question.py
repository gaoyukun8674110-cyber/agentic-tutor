"""题目相关数据模型"""

import enum

from sqlalchemy import JSON, Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import relationship

from app.database import Base


class QuestionType(str, enum.Enum):
    """题型枚举"""

    CHOICE = "choice"  # 选择题
    FILL_BLANK = "fill_blank"  # 填空题
    DERIVATION = "derivation"  # 推导题
    PROOF = "proof"  # 证明题
    APPLICATION = "application"  # 应用题


class QuestionStatus(str, enum.Enum):
    """题目状态"""

    ACTIVE = "active"  # 启用
    INACTIVE = "inactive"  # 下线
    PENDING = "pending"  # 待审核


class DifficultyLevel(str, enum.Enum):
    """难度等级"""

    EASY = "easy"  # 简单
    MEDIUM = "medium"  # 中等
    HARD = "hard"  # 困难
    EXPERT = "expert"  # 专家级


class Question(Base):
    """题目表"""

    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)

    # 题目内容
    content = Column(Text, nullable=False)  # 题干
    options = Column(JSON, nullable=True)  # 选项（选择题用）
    correct_answer = Column(Text, nullable=False)  # 正确答案
    standard_solution = Column(Text, nullable=False)  # 标准解
    solution_steps = Column(JSON, nullable=True)  # 分步解题树

    # 元数据
    question_type = Column(SQLEnum(QuestionType), nullable=False)
    difficulty = Column(SQLEnum(DifficultyLevel), nullable=False)
    status = Column(SQLEnum(QuestionStatus), default=QuestionStatus.ACTIVE)

    # 来源信息
    source = Column(String(255), nullable=True)  # 题源（教材章节、真题等）
    chapter = Column(String(100), nullable=True)  # 所属章节

    # 关系
    tags = relationship("QuestionTag", back_populates="question", cascade="all, delete-orphan")
    skills = relationship("QuestionSkill", back_populates="question", cascade="all, delete-orphan")

    created_at = Column(String(50), nullable=False)  # 创建时间
    updated_at = Column(String(50), nullable=False)  # 更新时间


class QuestionTag(Base):
    """题目标签表"""

    __tablename__ = "question_tags"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    tag = Column(String(100), nullable=False)

    question = relationship("Question", back_populates="tags")


class QuestionSkill(Base):
    """题目-知识点关联表"""

    __tablename__ = "question_skills"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    skill_id = Column(String(100), nullable=False)  # 知识点ID
    skill_name = Column(String(200), nullable=False)  # 知识点名称
    weight = Column(Float, default=1.0)  # 权重（一个题可能命中多个知识点，权重不同）

    question = relationship("Question", back_populates="skills")


class PrerequisiteSkill(Base):
    """先修知识点表（做这题之前最好先掌握什么）"""

    __tablename__ = "prerequisite_skills"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    prerequisite_skill_id = Column(String(100), nullable=False)  # 先修知识点ID

    question = relationship("Question")
