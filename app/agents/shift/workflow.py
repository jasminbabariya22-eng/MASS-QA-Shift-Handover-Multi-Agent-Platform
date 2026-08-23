from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import uuid
import logfire

from app.agents.shift.contracts import (
    ShiftHandover,
    ShiftHandoverData,
    ShiftHandoverState,
    ShiftHandoverRole,
    ShiftHandoverAction,
    ShiftHandoverAuditEntry,
    ShiftHandoverTransitionResult,
    SafetyCriticalItem,
)
from app.agents.shift.transitions import (
    WORKFLOW_DEFINITION,
    TRANSITION_RULES,
    TransitionRule,
    find_transition_rule,
    get_allowed_actions,
)


class ShiftHandoverWorkflowEngine:
    """
    Production Shift Handover Business Workflow Engine.
    
    Provides deterministic, auditable, role-aware state machine execution
    governing the Oil & Gas operational handover lifecycle without direct database coupling.
    """

    def __init__(self, workflow_definition: Optional[Dict[str, Any]] = None):
        self.workflow_def = workflow_definition or WORKFLOW_DEFINITION
        self.version = self.workflow_def.get("version", "1.0.0")

    def create_handover(
        self,
        data: ShiftHandoverData,
        actor_id: str,
        actor_role: ShiftHandoverRole,
        handover_id: Optional[str] = None
    ) -> Tuple[ShiftHandover, ShiftHandoverTransitionResult]:
        """
        Initialize a new ShiftHandover package in the DRAFT state.
        """
        now = datetime.now(timezone.utc)
        hid = handover_id or str(uuid.uuid4())

        handover = ShiftHandover(
            handover_id=hid,
            workflow_version=self.version,
            state=ShiftHandoverState.DRAFT,
            data=data,
            version=1,
            created_at=now,
            updated_at=now,
            audit_trail=[]
        )

        audit = ShiftHandoverAuditEntry(
            handover_id=hid,
            from_state=ShiftHandoverState.DRAFT,
            to_state=ShiftHandoverState.DRAFT,
            action=ShiftHandoverAction.CREATE,
            actor_id=actor_id,
            actor_role=actor_role,
            timestamp=now,
            reason="Initial handover draft creation",
            metadata={"unit_id": data.unit_id, "shift_type": data.shift_type.value}
        )
        handover.audit_trail.append(audit)

        logfire.info(f"[ShiftWorkflow] Handover {hid} created by {actor_id} ({actor_role.value}) [unit={data.unit_id}]")

        result = ShiftHandoverTransitionResult(
            success=True,
            handover_id=hid,
            previous_state=ShiftHandoverState.DRAFT,
            current_state=ShiftHandoverState.DRAFT,
            action=ShiftHandoverAction.CREATE,
            actor_id=actor_id,
            actor_role=actor_role,
            timestamp=now,
            audit_entry=audit,
            validation_errors=[],
            message="Handover draft created successfully."
        )
        return handover, result

    def can_perform_action(
        self,
        handover: ShiftHandover,
        action: ShiftHandoverAction,
        actor_role: ShiftHandoverRole
    ) -> Tuple[bool, str]:
        """
        Evaluate whether an actor with a given role can perform the action on the handover.
        """
        if handover.is_terminal:
            return False, f"Handover {handover.handover_id} is in terminal state '{handover.state.value}' and cannot be modified."

        rule = find_transition_rule(handover.state, action)
        if not rule:
            return False, f"Action '{action.value}' is not valid from state '{handover.state.value}'."

        if actor_role != ShiftHandoverRole.SYSTEM_ADMIN and actor_role not in rule.allowed_roles:
            return False, f"Role '{actor_role.value}' is not authorized to execute '{action.value}' from '{handover.state.value}'."

        return True, "Action allowed."

    def get_available_actions(
        self,
        handover: ShiftHandover,
        actor_role: Optional[ShiftHandoverRole] = None
    ) -> List[ShiftHandoverAction]:
        """
        List all permitted actions for the current state and role.
        """
        if handover.is_terminal:
            return []
        return get_allowed_actions(handover.state, actor_role)

    def execute_transition(
        self,
        handover: ShiftHandover,
        action: ShiftHandoverAction,
        actor_id: str,
        actor_role: ShiftHandoverRole,
        reason: Optional[str] = None,
        expected_version: Optional[int] = None,
        payload_updates: Optional[Dict[str, Any]] = None
    ) -> ShiftHandoverTransitionResult:
        """
        Execute an atomic state transition with validation, version check, and audit logging.
        """
        now = datetime.now(timezone.utc)
        prev_state = handover.state

        # 1. Terminal State Check
        if handover.is_terminal:
            msg = f"Cannot execute action '{action.value}': Handover is in terminal state '{prev_state.value}'."
            logfire.warning(f"[ShiftWorkflow] {msg} [id={handover.handover_id}]")
            return ShiftHandoverTransitionResult(
                success=False,
                handover_id=handover.handover_id,
                previous_state=prev_state,
                current_state=prev_state,
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                timestamp=now,
                validation_errors=["TERMINAL_STATE_LOCKED"],
                message=msg
            )

        # 2. Concurrency / Version Check (Optimistic Locking Guard)
        if expected_version is not None and expected_version != handover.version:
            msg = f"Version conflict: Expected version {expected_version}, but handover is at version {handover.version}."
            logfire.warning(f"[ShiftWorkflow] {msg} [id={handover.handover_id}]")
            return ShiftHandoverTransitionResult(
                success=False,
                handover_id=handover.handover_id,
                previous_state=prev_state,
                current_state=prev_state,
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                timestamp=now,
                validation_errors=["CONCURRENCY_VERSION_MISMATCH"],
                message=msg
            )

        # 3. Transition Rule & Role Authorization Check
        rule = find_transition_rule(prev_state, action)
        if not rule:
            msg = f"Invalid transition: Action '{action.value}' is not permitted from state '{prev_state.value}'."
            return ShiftHandoverTransitionResult(
                success=False,
                handover_id=handover.handover_id,
                previous_state=prev_state,
                current_state=prev_state,
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                timestamp=now,
                validation_errors=["INVALID_STATE_ACTION"],
                message=msg
            )

        if actor_role != ShiftHandoverRole.SYSTEM_ADMIN and actor_role not in rule.allowed_roles:
            msg = f"Unauthorized: Role '{actor_role.value}' is not permitted to execute '{action.value}' from '{prev_state.value}'."
            return ShiftHandoverTransitionResult(
                success=False,
                handover_id=handover.handover_id,
                previous_state=prev_state,
                current_state=prev_state,
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                timestamp=now,
                validation_errors=["ROLE_UNAUTHORIZED"],
                message=msg
            )

        # 4. Mandatory Reason Check
        if rule.requires_reason and (not reason or not reason.strip()):
            msg = f"Action '{action.value}' requires a mandatory reason/justification."
            return ShiftHandoverTransitionResult(
                success=False,
                handover_id=handover.handover_id,
                previous_state=prev_state,
                current_state=prev_state,
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                timestamp=now,
                validation_errors=["MISSING_MANDATORY_REASON"],
                message=msg
            )

        # 5. Apply Payload Updates if provided
        if payload_updates:
            for k, v in payload_updates.items():
                if hasattr(handover.data, k):
                    setattr(handover.data, k, v)

        # 6. Required Fields Validation
        validation_errors = []
        for field in rule.required_fields:
            val = getattr(handover.data, field, None)
            if val is None or (isinstance(val, str) and not val.strip()):
                validation_errors.append(f"Missing required field: '{field}'")

        # 7. Safety-Critical Item Acknowledgement Check on ACKNOWLEDGE -> COMPLETED
        if action == ShiftHandoverAction.ACKNOWLEDGE and rule.to_state == ShiftHandoverState.COMPLETED:
            if not handover.data.incoming_operator_id:
                validation_errors.append("Incoming operator ID must be recorded prior to completion.")
            
            # Check all safety items are acknowledged
            unack_safety = [
                item.equipment_tag for item in handover.data.safety_items
                if item.active and not item.acknowledged_by_incoming
            ]
            if unack_safety and not handover.data.all_safety_items_acknowledged:
                validation_errors.append(
                    f"Cannot complete handover: Unacknowledged safety items on tags: {', '.join(unack_safety)}"
                )

        if validation_errors:
            msg = f"Validation failed for transition '{action.value}': {'; '.join(validation_errors)}"
            logfire.warning(f"[ShiftWorkflow] {msg} [id={handover.handover_id}]")
            return ShiftHandoverTransitionResult(
                success=False,
                handover_id=handover.handover_id,
                previous_state=prev_state,
                current_state=prev_state,
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                timestamp=now,
                validation_errors=validation_errors,
                message=msg
            )

        # 8. Apply State Transition
        next_state = rule.to_state
        handover.state = next_state
        handover.version += 1
        handover.updated_at = now

        if next_state == ShiftHandoverState.SUBMITTED and not handover.submitted_at:
            handover.submitted_at = now
        elif next_state == ShiftHandoverState.COMPLETED:
            handover.completed_at = now

        # 9. Create Immutable Audit Entry
        audit = ShiftHandoverAuditEntry(
            handover_id=handover.handover_id,
            from_state=prev_state,
            to_state=next_state,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            timestamp=now,
            reason=reason,
            metadata={
                "version": handover.version,
                "unit_id": handover.data.unit_id,
                "shift_type": handover.data.shift_type.value
            }
        )
        handover.audit_trail.append(audit)

        logfire.info(
            f"[ShiftWorkflow] Transition succeeded [id={handover.handover_id}, v={handover.version}]: "
            f"{prev_state.value} -> {action.value} -> {next_state.value} (Actor: {actor_id}, Role: {actor_role.value})"
        )

        return ShiftHandoverTransitionResult(
            success=True,
            handover_id=handover.handover_id,
            previous_state=prev_state,
            current_state=next_state,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            timestamp=now,
            audit_entry=audit,
            validation_errors=[],
            message=f"Transition to '{next_state.value}' completed successfully."
        )


# Singleton workflow engine instance
shift_workflow_engine = ShiftHandoverWorkflowEngine()
