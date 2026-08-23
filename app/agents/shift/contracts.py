from typing import Optional, List, Dict, Any, Set
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class ShiftHandoverState(str, Enum):
    """
    Standard operational lifecycle states for Oil & Gas Shift Handover.
    """
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PENDING_REVIEW = "PENDING_REVIEW"
    PENDING_ACKNOWLEDGEMENT = "PENDING_ACKNOWLEDGEMENT"
    RETURNED = "RETURNED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class ShiftHandoverRole(str, Enum):
    """
    Operational personas involved in plant shift handover.
    """
    CONSOLE_OPERATOR = "CONSOLE_OPERATOR"
    FIELD_OPERATOR = "FIELD_OPERATOR"
    OUTGOING_OPERATOR = "OUTGOING_OPERATOR"  # General alias for outgoing console/field operator
    INCOMING_OPERATOR = "INCOMING_OPERATOR"  # Incoming shift operator accepting unit
    INCOMING_SHIFT_OPERATOR = "INCOMING_OPERATOR"  # Backward-compatible alias
    SHIFT_SUPERVISOR = "SHIFT_SUPERVISOR"
    OPERATIONS_ENGINEER = "OPERATIONS_ENGINEER"
    MAINTENANCE_LEAD = "MAINTENANCE_LEAD"
    HSE_REPRESENTATIVE = "HSE_REPRESENTATIVE"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class ShiftHandoverAction(str, Enum):
    """
    Standardized operational workflow actions.
    """
    CREATE = "CREATE"
    SAVE = "SAVE"
    EDIT = "EDIT"
    SUBMIT = "SUBMIT"
    REVIEW = "REVIEW"
    RETURN = "RETURN"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ACKNOWLEDGE = "ACKNOWLEDGE"
    ESCALATE = "ESCALATE"
    CANCEL = "CANCEL"


class ShiftType(str, Enum):
    DAY = "DAY"
    NIGHT = "NIGHT"
    SWING = "SWING"


class SafetyCriticalItem(BaseModel):
    """
    High-visibility safety critical record (LOTO, active permits, ESD bypass, SOL/IOW deviations).
    Note: System records and surfaces safety items; it NEVER executes physical plant control.
    """
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str = Field(..., description="LOTO, PERMIT_TO_WORK, ESD_BYPASS, ABNORMAL_ALARM, SOL_EXCURSION")
    equipment_tag: str = Field(..., description="Target equipment tag e.g. P-101A, XV-202")
    description: str = Field(..., description="Safety critical details and operational precautions")
    active: bool = True
    acknowledged_by_incoming: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ShiftHandoverData(BaseModel):
    """
    Structured domain payload for a shift handover package.
    """
    unit_id: str = Field(..., description="Plant unit identifier e.g. CDU-101, HCU-202")
    unit_name: Optional[str] = None
    shift_type: ShiftType = ShiftType.DAY
    shift_date: str = Field(..., description="YYYY-MM-DD format")
    outgoing_operator_id: str
    outgoing_operator_name: Optional[str] = None
    incoming_operator_id: Optional[str] = None
    incoming_operator_name: Optional[str] = None
    supervisor_id: Optional[str] = None
    operational_summary: str = Field("", description="Summary of shift operations, throughput, mode changes")
    equipment_abnormalities: List[str] = Field(default_factory=list)
    open_permits: List[str] = Field(default_factory=list)
    loto_isolations: List[str] = Field(default_factory=list)
    carry_forward_actions: List[str] = Field(default_factory=list)
    safety_items: List[SafetyCriticalItem] = Field(default_factory=list)
    all_safety_items_acknowledged: bool = False
    notes: Optional[str] = None


class ShiftHandoverAuditEntry(BaseModel):
    """
    Immutable audit record for every workflow state transition.
    """
    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    handover_id: str
    from_state: ShiftHandoverState
    to_state: ShiftHandoverState
    action: ShiftHandoverAction
    actor_id: str
    actor_role: ShiftHandoverRole
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ShiftHandover(BaseModel):
    """
    Complete in-memory Shift Handover entity with versioning and audit trail.
    """
    handover_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_version: str = "1.0.0"
    state: ShiftHandoverState = ShiftHandoverState.DRAFT
    data: ShiftHandoverData
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    audit_trail: List[ShiftHandoverAuditEntry] = Field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.state in (
            ShiftHandoverState.COMPLETED,
            ShiftHandoverState.CANCELLED,
            ShiftHandoverState.REJECTED,
            ShiftHandoverState.EXPIRED
        )


class ShiftHandoverTransitionResult(BaseModel):
    """
    Normalized result contract returned after executing a workflow transition.
    """
    success: bool
    handover_id: str
    previous_state: ShiftHandoverState
    current_state: ShiftHandoverState
    action: ShiftHandoverAction
    actor_id: str
    actor_role: ShiftHandoverRole
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    audit_entry: Optional[ShiftHandoverAuditEntry] = None
    validation_errors: List[str] = Field(default_factory=list)
    message: str = ""
