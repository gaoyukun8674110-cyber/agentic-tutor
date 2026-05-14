"""Per-user LLM provider credentials."""
from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class UserLLMCredential(Base):
    """Encrypted LLM credential owned by one user and one provider."""

    __tablename__ = "user_llm_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "provider_id", name="uq_user_llm_credentials_user_provider"),
        Index("idx_user_llm_credentials_user", "user_id"),
        Index("idx_user_llm_credentials_fingerprint", "api_key_fingerprint"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider_id = Column(String(50), nullable=False)
    encrypted_api_key = Column(Text, nullable=True)
    api_key_fingerprint = Column(String(32), nullable=True, index=True)
    base_url = Column(String(500), nullable=True)
    default_model = Column(String(120), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    last_validated_at = Column(String(50), nullable=True)
    last_validation_error_code = Column(String(32), nullable=True)
    last_used_at = Column(String(50), nullable=True)
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)

    user = relationship("User", back_populates="llm_credentials")
