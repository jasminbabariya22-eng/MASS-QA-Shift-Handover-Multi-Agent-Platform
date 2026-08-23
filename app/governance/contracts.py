from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid


class RiskLevel(str, Enum):
    """
    Centralized 4-tier risk classification for all platform actions.
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class HITLDecision(str, Enum):
    """
    Human-In-The-Loop decision outcomes.
    """
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    RETURN = "RETURN"
    ESCALATE = "ESCALATE"
    CANCEL = "CANCEL"


class HITLStatus(str, Enum):
    """
    State machine for Human-In-The-Loop approval requests.
    """
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    RETURNED = "RETURNED"
    ESCALATED = "ESCALATED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    CONSUMED = "CONSUMED"


class ApprovalRequest(BaseModel):
    """
    Strongly typed HITL approval request contract.
    """
    id: str = Field(default_factory=lambda: f"APR-{uuid.uuid4().hex[:12].upper()}")
    request_id: str
    session_id: Optional[str] = None
    handover_id: Optional[str] = None
    action: str = Field(..., description="Action requested (e.g. SUBMIT, APPROVE, REJECT, ACKNOWLEDGE, CREATE, EDIT).")
    risk_level: RiskLevel = RiskLevel.HIGH
    status: HITLStatus = HITLStatus.PENDING
    
    requested_by: str = Field(..., description="User ID of requester.")
    requested_role: str = Field(..., description="Operational role of requester.")
    required_role: str = Field(..., description="Operational role required to decide/approve.")
    reason: Optional[str] = Field(None, description="Operational justification for request.")
    proposed_payload: Dict[str, Any] = Field(default_factory=dict)
    
    decision: Optional[HITLDecision] = None
    decision_reason: Optional[str] = None
    decided_by: Optional[str] = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    decided_at: Optional[datetime] = None
    consumed_at: Optional[datetime] = None
    
    version: int = 1
    expected_handover_version: Optional[int] = None


class DecisionPayload(BaseModel):
    """
    Payload supplied by human reviewer when deciding an approval request.
    """
    decision: HITLDecision
    reason: Optional[str] = Field(None, description="Mandatory reason if decision is REJECT or RETURN.")
    decider_id: Optional[str] = None
    decider_role: Optional[str] = None


class HITLPolicyResult(BaseModel):
    """
    Policy evaluation outcome returned by PolicyEngine.
    """
    allowed: bool = True
    risk_level: RiskLevel = RiskLevel.LOW
    hitl_required: bool = False
    required_role: Optional[str] = None
    reason: str = "Standard policy evaluation"
    blocked_by_safety: bool = False
