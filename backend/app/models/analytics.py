"""分析服务相关数据模型"""

from sqlalchemy import JSON, Column, Float, ForeignKey, Integer, String

from app.database import Base


class BehaviorLog(Base):
    """行为日志表"""

    __tablename__ = "behavior_logs"

    id = Column(Integer, primary_key=True, index=True)

    # 日志类型
    log_type = Column(String(50), nullable=False, index=True)  # api_call, answer, llm_call, etc.

    # 关联信息
    user_id = Column(String(100), nullable=True, index=True)
    session_id = Column(Integer, ForeignKey("training_sessions.id"), nullable=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)

    # 日志内容
    action = Column(String(100), nullable=False)  # 具体动作
    details = Column(JSON, nullable=True)  # 详细信息
    metadata_ = Column("metadata_json", JSON, nullable=True)  # 元数据（耗时、结果等）

    # 时间戳
    created_at = Column(String(50), nullable=False, index=True)


class QuestionStat(Base):
    """题目统计表"""

    __tablename__ = "question_stats"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), unique=True, nullable=False)

    # 统计指标
    exposure_count = Column(Integer, default=0)  # 曝光次数
    answer_count = Column(Integer, default=0)  # 作答次数
    correct_count = Column(Integer, default=0)  # 正确次数
    correct_rate = Column(Float, default=0.0)  # 正确率
    average_time = Column(Float, default=0.0)  # 平均用时
    hint_usage_rate = Column(Float, default=0.0)  # hint 使用率

    # 质量指标
    complaint_count = Column(Integer, default=0)  # 投诉次数
    quality_score = Column(Float, default=1.0)  # 质量分数

    updated_at = Column(String(50), nullable=False)


class SkillStat(Base):
    """知识点统计表"""

    __tablename__ = "skill_stats"

    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(String(100), unique=True, nullable=False, index=True)
    skill_name = Column(String(200), nullable=False)

    # 统计指标
    total_attempts = Column(Integer, default=0)  # 总尝试次数
    total_correct = Column(Integer, default=0)  # 总正确次数
    overall_correct_rate = Column(Float, default=0.0)  # 总体正确率
    average_time = Column(Float, default=0.0)  # 平均用时

    # 错因分析
    common_errors = Column(JSON, nullable=True)  # 常见错因排名

    updated_at = Column(String(50), nullable=False)
