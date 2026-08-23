import uuid
from sqlalchemy import Column, String, Text, Integer, Float, Boolean, DateTime, func

from app.db.base import Base


class QueryLog(Base):
    __tablename__ = "query_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), index=True, nullable=True)
    conversation_id = Column(String(100), index=True, nullable=True)
    message_id = Column(String(100), nullable=True)
    query_text = Column(Text, nullable=False)
    retrieval_time_ms = Column(Float, nullable=True)
    reranking_time_ms = Column(Float, nullable=True)
    llm_time_ms = Column(Float, nullable=True)
    total_time_ms = Column(Float, nullable=True)
    retrieved_count = Column(Integer, nullable=True)
    reranked_count = Column(Integer, nullable=True)
    cache_hit = Column(Boolean, default=False, nullable=False)
    model_name = Column(String(100), nullable=True)
    status = Column(String(50), default="SUCCESS", index=True, nullable=False)
    error_type = Column(String(100), nullable=True)
    request_id = Column(String(100), index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
