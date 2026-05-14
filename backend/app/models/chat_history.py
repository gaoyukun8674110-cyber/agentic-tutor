"""Tutor chat conversation history models."""
from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.database import Base


class TutorConversation(Base):
    """A persisted Tutor chat conversation."""

    __tablename__ = "tutor_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), ForeignKey("users.username", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(120), nullable=False)
    training_mode = Column(String(50), nullable=True)
    prompt_profile = Column(String(50), nullable=True)
    provider = Column(String(50), nullable=True)
    model = Column(String(120), nullable=True)
    message_count = Column(Integer, default=0, nullable=False)
    created_at = Column(String(50), nullable=False, index=True)
    updated_at = Column(String(50), nullable=False, index=True)

    messages = relationship(
        "TutorConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="TutorConversationMessage.sequence",
    )


class TutorConversationMessage(Base):
    """One message in a Tutor chat conversation."""

    __tablename__ = "tutor_conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("tutor_conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    label = Column(String(80), nullable=True)
    sequence = Column(Integer, nullable=False)
    created_at = Column(String(50), nullable=False)

    conversation = relationship("TutorConversation", back_populates="messages")


class TutorConversationDigest(Base):
    """Compact summary for long Tutor conversations."""

    __tablename__ = "tutor_conversation_digests"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("tutor_conversations.id"), unique=True, nullable=False, index=True)
    content = Column(Text, nullable=False)
    source_message_count = Column(Integer, default=0, nullable=False)
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)
