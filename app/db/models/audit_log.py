import uuid
from sqlalchemy import Column, String, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON

from app.db.base import Base

JSONType = JSONB().with_variant(JSON(), "sqlite")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), index=True, nullable=True)
    action = Column(String(100), index=True, nullable=False)  # LOGIN, QUERY, etc.
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(100), nullable=True)
    endpoint = Column(String(255), nullable=True)
    http_method = Column(String(20), nullable=True)
    status_code = Column(Integer, nullable=True)
    request_id = Column(String(100), index=True, nullable=True)
    session_id = Column(String(100), nullable=True)
    ip_address = Column(String(100), nullable=True)
    user_agent = Column(String(255), nullable=True)
    metadata_ = Column("metadata", JSONType, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
