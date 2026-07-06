"""Authentication user models."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """A registered student account."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)
    last_login_at = Column(String(50), nullable=True)

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    llm_credentials = relationship("UserLLMCredential", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    """Server-side refresh token record storing only a SHA-256 hash."""

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    issued_at = Column(String(50), nullable=False)
    expires_at = Column(String(50), nullable=False, index=True)
    revoked_at = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    client_ip = Column(String(64), nullable=True)
    created_at = Column(String(50), nullable=False)

    user = relationship("User", back_populates="refresh_tokens")
