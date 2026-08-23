import uuid
from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from sqlalchemy.orm import relationship

from app.db.base import Base

# Fallback to JSON if dialect doesn't support JSONB
JSONType = JSONB().with_variant(JSON(), "sqlite")


class MessageCitation(Base):
    __tablename__ = "message_citations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id = Column(String(100), index=True, nullable=True)
    document_name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=True)  # PDF, PPTX, DOCX, etc.
    page_number = Column(Integer, nullable=True)
    slide_number = Column(Integer, nullable=True)
    chunk_id = Column(String(100), nullable=True)
    score = Column(Float, nullable=True)
    citation_text = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONType, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    message = relationship("Message", back_populates="citations")
