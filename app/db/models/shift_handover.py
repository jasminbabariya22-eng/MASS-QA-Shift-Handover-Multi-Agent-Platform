import uuid
from typing import List
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, ForeignKey, func, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from sqlalchemy.orm import relationship

from app.db.base import Base

JSONType = JSONB().with_variant(JSON(), "sqlite")


class ShiftHandoverModel(Base):
    """
    SQLAlchemy ORM Model representing an operational Shift Handover in the MASS platform.
    Persists the aggregate root, state machine status, and optimistic concurrency version.
    """
    __tablename__ = "shift_handovers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    handover_number = Column(String(50), unique=True, index=True, nullable=False)
    workflow_code = Column(String(50), default="SHIFT_HANDOVER", nullable=False)
    workflow_version = Column(String(20), default="1.0.0", nullable=False)
    state = Column(String(50), default="DRAFT", index=True, nullable=False)
    unit_id = Column(String(50), index=True, nullable=False)
    unit_name = Column(String(150), nullable=True)
    shift_type = Column(String(20), default="DAY", nullable=False)
    shift_date = Column(String(20), index=True, nullable=False)  # YYYY-MM-DD
    
    outgoing_operator_id = Column(String(100), index=True, nullable=False)
    outgoing_operator_name = Column(String(150), nullable=True)
    incoming_operator_id = Column(String(100), index=True, nullable=True)
    incoming_operator_name = Column(String(150), nullable=True)
    supervisor_id = Column(String(100), index=True, nullable=True)
    
    operational_summary = Column(Text, default="", nullable=False)
    equipment_abnormalities = Column(JSONType, default=list, nullable=False)
    open_permits = Column(JSONType, default=list, nullable=False)
    loto_isolations = Column(JSONType, default=list, nullable=False)
    carry_forward_actions = Column(JSONType, default=list, nullable=False)
    all_safety_items_acknowledged = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)
    
    version = Column(Integer, default=1, nullable=False)  # Optimistic Concurrency Control
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    safety_items = relationship(
        "SafetyCriticalItemModel",
        back_populates="handover",
        cascade="all, delete-orphan",
        order_by="SafetyCriticalItemModel.created_at"
    )
    audit_trail = relationship(
        "ShiftHandoverAuditModel",
        back_populates="handover",
        cascade="all, delete-orphan",
        order_by="ShiftHandoverAuditModel.created_at"
    )

    @property
    def is_terminal(self) -> bool:
        return self.state in ("COMPLETED", "CANCELLED", "REJECTED", "EXPIRED")


class SafetyCriticalItemModel(Base):
    """
    SQLAlchemy ORM Model for individual safety critical items (LOTO, active permits, ESD bypass).
    """
    __tablename__ = "shift_safety_critical_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    handover_id = Column(String(36), ForeignKey("shift_handovers.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(50), nullable=False)  # LOTO, PERMIT_TO_WORK, ESD_BYPASS, ABNORMAL_ALARM, SOL_EXCURSION
    equipment_tag = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    acknowledged_by_incoming = Column(Boolean, default=False, nullable=False)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    handover = relationship("ShiftHandoverModel", back_populates="safety_items")


class ShiftHandoverAuditModel(Base):
    """
    SQLAlchemy ORM Model for immutable, append-only workflow state transition audit records.
    """
    __tablename__ = "shift_handover_audits"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    handover_id = Column(String(36), ForeignKey("shift_handovers.id", ondelete="CASCADE"), nullable=False, index=True)
    from_state = Column(String(50), nullable=False)
    to_state = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)
    actor_id = Column(String(100), nullable=False, index=True)
    actor_role = Column(String(50), nullable=False)
    reason = Column(Text, nullable=True)
    request_id = Column(String(100), index=True, nullable=True)
    session_id = Column(String(100), nullable=True)
    metadata_ = Column("metadata", JSONType, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    handover = relationship("ShiftHandoverModel", back_populates="audit_trail")
