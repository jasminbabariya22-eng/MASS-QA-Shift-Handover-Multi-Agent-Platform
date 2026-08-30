from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

from app.agents.shift.contracts import (
    ShiftHandoverAction,
    ShiftHandoverState,
    ShiftHandoverRole,
    ShiftType,
)


class ShiftCommandType(str, Enum):
    """
    High-level operational intent types for the Shift Handover Agent.
    """
    CREATE_HANDOVER = "CREATE_HANDOVER"
    GET_HANDOVER = "GET_HANDOVER"
    LIST_HANDOVERS = "LIST_HANDOVERS"
    UPDATE_HANDOVER = "UPDATE_HANDOVER"
    ADD_SAFETY_ITEM = "ADD_SAFETY_ITEM"
    ACKNOWLEDGE_SAFETY_ITEM = "ACKNOWLEDGE_SAFETY_ITEM"
    SUBMIT_HANDOVER = "SUBMIT_HANDOVER"
    REVIEW_HANDOVER = "REVIEW_HANDOVER"
    APPROVE_HANDOVER = "APPROVE_HANDOVER"
    RETURN_HANDOVER = "RETURN_HANDOVER"
    REJECT_HANDOVER = "REJECT_HANDOVER"
    ACKNOWLEDGE_HANDOVER = "ACKNOWLEDGE_HANDOVER"
    CANCEL_HANDOVER = "CANCEL_HANDOVER"
    ESCALATE_HANDOVER = "ESCALATE_HANDOVER"
    GET_AUDIT_HISTORY = "GET_AUDIT_HISTORY"
    GET_SAFETY_STATUS = "GET_SAFETY_STATUS"
    PROCESS_VOICE_NOTE = "PROCESS_VOICE_NOTE"
    CHECK_QUALITY = "CHECK_QUALITY"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"



class ShiftCommand(BaseModel):
    """
    Strongly typed command representation extracted from natural-language requests.
    """
    command_type: ShiftCommandType
    action: Optional[ShiftHandoverAction] = None
    handover_id: Optional[str] = None
    handover_number: Optional[str] = None
    unit_id: Optional[str] = None
    shift_type: Optional[ShiftType] = None
    shift_date: Optional[str] = None
    operational_summary: Optional[str] = None
    safety_category: Optional[str] = None
    equipment_tag: Optional[str] = None
    description: Optional[str] = None
    reason: Optional[str] = None
    updates: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    requires_clarification: bool = False
    clarification_prompt: Optional[str] = None
    requires_confirmation: bool = False
    confirmation_prompt: Optional[str] = None
    raw_query: str = ""
