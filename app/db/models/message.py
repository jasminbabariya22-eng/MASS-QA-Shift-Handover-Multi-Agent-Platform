import uuid
from sqlalchemy import Column, String, Text, Boolean, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.db.base import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role = Column(String(50), nullable=False)  # USER, ASSISTANT, SYSTEM
    content = Column(Text, nullable=False)
    model_name = Column(String(100), nullable=True)
    response_time_ms = Column(Float, nullable=True)
    token_count = Column(Integer, nullable=True)
    cache_hit = Column(Boolean, default=False, nullable=False)
    status = Column(String(50), default="SUCCESS", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    citations = relationship("MessageCitation", back_populates="message", cascade="all, delete-orphan")
    feedback = relationship("MessageFeedback", back_populates="message", cascade="all, delete-orphan", uselist=False)
