from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.db.base import Base


class HITLApprovalModel(Base):
    """
    Persistent record of Human-In-The-Loop approval requests, decisions, and execution status.
    """
    __tablename__ = "hitl_approval_requests"

    id = Column(String(64), primary_key=True, default=lambda: f"APR-{uuid.uuid4().hex[:12].upper()}")
    request_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    handover_id = Column(String(64), ForeignKey("shift_handovers.id", ondelete="SET NULL"), nullable=True, index=True)
    
    action = Column(String(64), nullable=False)
    risk_level = Column(String(32), nullable=False, default="HIGH")
    status = Column(String(32), nullable=False, default="PENDING", index=True)
    
    requested_by = Column(String(64), nullable=False)
    requested_role = Column(String(64), nullable=False)
    required_role = Column(String(64), nullable=False)
    reason = Column(Text, nullable=True)
    proposed_payload = Column(JSON, nullable=True)
    
    decision = Column(String(32), nullable=True)
    decision_reason = Column(Text, nullable=True)
    decided_by = Column(String(64), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    
    version = Column(Integer, default=1, nullable=False)
    expected_handover_version = Column(Integer, nullable=True)

    # Relationships
    handover = relationship("ShiftHandoverModel", backref="approval_requests")
