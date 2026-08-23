from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field

from app.agents.shift.contracts import (
    ShiftHandoverState,
    ShiftHandoverRole,
    ShiftHandoverAction,
)


class TransitionRule(BaseModel):
    """
    Data-driven transition rule specifying the valid execution matrix.
    """
    from_state: ShiftHandoverState
    action: ShiftHandoverAction
    allowed_roles: List[ShiftHandoverRole]
    to_state: ShiftHandoverState
    requires_reason: bool = False
    required_fields: List[str] = Field(default_factory=list)
    description: str = ""


# Master Declarative Workflow Definition (Version 1.0.0)
WORKFLOW_DEFINITION: Dict[str, Any] = {
    "workflow_code": "SHIFT_HANDOVER",
    "version": "1.0.0",
    "description": "Standardized Oil & Gas Operating Shift Handover Workflow",
    "states": [
        {
            "code": ShiftHandoverState.DRAFT.value,
            "display_name": "Draft",
            "is_terminal": False,
            "description": "Handover created by outgoing operator; undergoing preparation."
        },
        {
            "code": ShiftHandoverState.SUBMITTED.value,
            "display_name": "Submitted",
            "is_terminal": False,
            "description": "Handover submitted by outgoing shift; awaiting supervisor review or incoming operator."
        },
        {
            "code": ShiftHandoverState.PENDING_REVIEW.value,
            "display_name": "Pending Review",
            "is_terminal": False,
            "description": "Under formal review by Shift Supervisor or escalated authority."
        },
        {
            "code": ShiftHandoverState.PENDING_ACKNOWLEDGEMENT.value,
            "display_name": "Pending Acknowledgement",
            "is_terminal": False,
            "description": "Reviewed and cleared for incoming shift acceptance and safety checklist acknowledgement."
        },
        {
            "code": ShiftHandoverState.RETURNED.value,
            "display_name": "Returned for Correction",
            "is_terminal": False,
            "description": "Returned to outgoing operator due to missing information or unverified plant status."
        },
        {
            "code": ShiftHandoverState.REJECTED.value,
            "display_name": "Rejected",
            "is_terminal": True,
            "description": "Handover rejected by supervisor due to critical non-compliance."
        },
        {
            "code": ShiftHandoverState.COMPLETED.value,
            "display_name": "Completed",
            "is_terminal": True,
            "description": "Formally acknowledged and accepted by incoming operator. Handover legally closed."
        },
        {
            "code": ShiftHandoverState.CANCELLED.value,
            "display_name": "Cancelled",
            "is_terminal": True,
            "description": "Cancelled prior to completion."
        },
        {
            "code": ShiftHandoverState.EXPIRED.value,
            "display_name": "Expired",
            "is_terminal": True,
            "description": "Shift elapsed without completion; required supervisor administrative handling."
        }
    ],
    "roles": [
        ShiftHandoverRole.CONSOLE_OPERATOR.value,
        ShiftHandoverRole.FIELD_OPERATOR.value,
        ShiftHandoverRole.OUTGOING_OPERATOR.value,
        ShiftHandoverRole.INCOMING_OPERATOR.value,
        ShiftHandoverRole.SHIFT_SUPERVISOR.value,
        ShiftHandoverRole.OPERATIONS_ENGINEER.value,
        ShiftHandoverRole.MAINTENANCE_LEAD.value,
        ShiftHandoverRole.HSE_REPRESENTATIVE.value,
        ShiftHandoverRole.SYSTEM_ADMIN.value,
    ]
}


# Concrete Transition Rules Matrix
TRANSITION_RULES: List[TransitionRule] = [
    # --- DRAFT State Transitions ---
    TransitionRule(
        from_state=ShiftHandoverState.DRAFT,
        action=ShiftHandoverAction.SAVE,
        allowed_roles=[
            ShiftHandoverRole.CONSOLE_OPERATOR,
            ShiftHandoverRole.FIELD_OPERATOR,
            ShiftHandoverRole.OUTGOING_OPERATOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.DRAFT,
        requires_reason=False,
        description="Save in-progress draft changes"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.DRAFT,
        action=ShiftHandoverAction.SUBMIT,
        allowed_roles=[
            ShiftHandoverRole.CONSOLE_OPERATOR,
            ShiftHandoverRole.FIELD_OPERATOR,
            ShiftHandoverRole.OUTGOING_OPERATOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.SUBMITTED,
        requires_reason=False,
        required_fields=["unit_id", "shift_type", "shift_date", "outgoing_operator_id", "operational_summary"],
        description="Submit completed draft for review/acknowledgement"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.DRAFT,
        action=ShiftHandoverAction.CANCEL,
        allowed_roles=[
            ShiftHandoverRole.CONSOLE_OPERATOR,
            ShiftHandoverRole.FIELD_OPERATOR,
            ShiftHandoverRole.OUTGOING_OPERATOR,
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.CANCELLED,
        requires_reason=True,
        description="Cancel draft handover with mandatory reason"
    ),

    # --- SUBMITTED State Transitions ---
    TransitionRule(
        from_state=ShiftHandoverState.SUBMITTED,
        action=ShiftHandoverAction.REVIEW,
        allowed_roles=[
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.PENDING_REVIEW,
        requires_reason=False,
        description="Supervisor begins active review"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.SUBMITTED,
        action=ShiftHandoverAction.APPROVE,
        allowed_roles=[
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.PENDING_ACKNOWLEDGEMENT,
        requires_reason=False,
        description="Supervisor fast-tracks approval to incoming operator acknowledgement"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.SUBMITTED,
        action=ShiftHandoverAction.RETURN,
        allowed_roles=[
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.INCOMING_OPERATOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.RETURNED,
        requires_reason=True,
        description="Return handover to outgoing shift for correction"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.SUBMITTED,
        action=ShiftHandoverAction.REJECT,
        allowed_roles=[
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.REJECTED,
        requires_reason=True,
        description="Supervisor rejects invalid handover package"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.SUBMITTED,
        action=ShiftHandoverAction.ACKNOWLEDGE,
        allowed_roles=[
            ShiftHandoverRole.INCOMING_OPERATOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.COMPLETED,
        requires_reason=False,
        required_fields=["incoming_operator_id"],
        description="Incoming operator directly accepts submitted handover"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.SUBMITTED,
        action=ShiftHandoverAction.ESCALATE,
        allowed_roles=[
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.HSE_REPRESENTATIVE,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.PENDING_REVIEW,
        requires_reason=True,
        description="Escalate handover for special management/safety review"
    ),

    # --- PENDING_REVIEW State Transitions ---
    TransitionRule(
        from_state=ShiftHandoverState.PENDING_REVIEW,
        action=ShiftHandoverAction.APPROVE,
        allowed_roles=[
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.PENDING_ACKNOWLEDGEMENT,
        requires_reason=False,
        description="Supervisor approves and forwards to incoming operator"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.PENDING_REVIEW,
        action=ShiftHandoverAction.RETURN,
        allowed_roles=[
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.HSE_REPRESENTATIVE,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.RETURNED,
        requires_reason=True,
        description="Supervisor returns handover with comments"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.PENDING_REVIEW,
        action=ShiftHandoverAction.REJECT,
        allowed_roles=[
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.REJECTED,
        requires_reason=True,
        description="Supervisor rejects handover"
    ),

    # --- RETURNED State Transitions ---
    TransitionRule(
        from_state=ShiftHandoverState.RETURNED,
        action=ShiftHandoverAction.SAVE,
        allowed_roles=[
            ShiftHandoverRole.CONSOLE_OPERATOR,
            ShiftHandoverRole.FIELD_OPERATOR,
            ShiftHandoverRole.OUTGOING_OPERATOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.RETURNED,
        requires_reason=False,
        description="Save corrections on returned handover"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.RETURNED,
        action=ShiftHandoverAction.SUBMIT,
        allowed_roles=[
            ShiftHandoverRole.CONSOLE_OPERATOR,
            ShiftHandoverRole.FIELD_OPERATOR,
            ShiftHandoverRole.OUTGOING_OPERATOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.SUBMITTED,
        requires_reason=False,
        required_fields=["unit_id", "shift_type", "shift_date", "outgoing_operator_id", "operational_summary"],
        description="Resubmit corrected handover"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.RETURNED,
        action=ShiftHandoverAction.CANCEL,
        allowed_roles=[
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.CONSOLE_OPERATOR,
            ShiftHandoverRole.OUTGOING_OPERATOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.CANCELLED,
        requires_reason=True,
        description="Cancel returned handover"
    ),

    # --- PENDING_ACKNOWLEDGEMENT State Transitions ---
    TransitionRule(
        from_state=ShiftHandoverState.PENDING_ACKNOWLEDGEMENT,
        action=ShiftHandoverAction.ACKNOWLEDGE,
        allowed_roles=[
            ShiftHandoverRole.INCOMING_OPERATOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.COMPLETED,
        requires_reason=False,
        required_fields=["incoming_operator_id"],
        description="Incoming operator acknowledges all safety items and accepts handover"
    ),
    TransitionRule(
        from_state=ShiftHandoverState.PENDING_ACKNOWLEDGEMENT,
        action=ShiftHandoverAction.RETURN,
        allowed_roles=[
            ShiftHandoverRole.INCOMING_OPERATOR,
            ShiftHandoverRole.SHIFT_SUPERVISOR,
            ShiftHandoverRole.SYSTEM_ADMIN
        ],
        to_state=ShiftHandoverState.RETURNED,
        requires_reason=True,
        description="Incoming operator requests clarification / returns handover"
    ),
]


def find_transition_rule(from_state: ShiftHandoverState, action: ShiftHandoverAction) -> Optional[TransitionRule]:
    """Find the transition rule for a given from_state and action."""
    for rule in TRANSITION_RULES:
        if rule.from_state == from_state and rule.action == action:
            return rule
    return None


def get_allowed_actions(from_state: ShiftHandoverState, role: Optional[ShiftHandoverRole] = None) -> List[ShiftHandoverAction]:
    """Get all actions permitted from from_state, optionally filtered by role."""
    actions = []
    for rule in TRANSITION_RULES:
        if rule.from_state == from_state:
            if role is None or role in rule.allowed_roles or ShiftHandoverRole.SYSTEM_ADMIN == role:
                if rule.action not in actions:
                    actions.append(rule.action)
    return actions
