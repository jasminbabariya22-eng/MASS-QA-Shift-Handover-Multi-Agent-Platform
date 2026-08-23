import uuid
from sqlalchemy import Column, String, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON

from app.db.base import Base

JSONType = JSONB().with_variant(JSON(), "sqlite")


class DocumentMetadata(Base):
    __tablename__ = "document_metadata"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(100), unique=True, index=True, nullable=False)
    document_name = Column(String(255), index=True, nullable=False)
    file_name = Column(String(255), nullable=True)
    file_type = Column(String(50), nullable=True)  # PDF, PPTX, DOCX
    version = Column(String(50), default="v1", nullable=False)
    source = Column(String(255), nullable=True)
    status = Column(String(50), default="ACTIVE", index=True, nullable=False)
    ingestion_version = Column(String(50), nullable=True)
    chunk_count = Column(Integer, default=0, nullable=False)
    page_count = Column(Integer, nullable=True)
    slide_count = Column(Integer, nullable=True)
    metadata_ = Column("metadata", JSONType, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
