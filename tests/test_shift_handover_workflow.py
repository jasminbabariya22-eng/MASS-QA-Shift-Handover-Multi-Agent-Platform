import pytest
from datetime import datetime, timezone
import uuid

from app.agents.shift import (
    ShiftHandoverState,
    ShiftHandoverRole,
    ShiftHandoverAction,
    ShiftType,
    SafetyCriticalItem,
    ShiftHandoverData,
    ShiftHandover,
    ShiftHandoverTransitionResult,
    WORKFLOW_DEFINITION,
    TRANSITION_RULES,
    ShiftHandoverWorkflowEngine,
    shift_workflow_engine,
)


# --- Test Fixtures ---

def sample_handover_data(
    unit_id: str = "CDU-101",
    operational_summary: str = "Operating at 110 kbpd nominal throughput. Desalter temperature stable at 125°C.",
    include_safety_item: bool = False,
    safety_acknowledged: bool = False
) -> ShiftHandoverData:
    safety_items = []
    if include_safety_item:
        safety_items.append(
            SafetyCriticalItem(
                category="LOTO",
                equipment_tag="P-101B",
                description="Pump decoupled for mechanical seal replacement under Permit #PTW-8821.",
                active=True,
                acknowledged_by_incoming=safety_acknowledged
            )
        )

    return ShiftHandoverData(
        unit_id=unit_id,
        unit_name="Crude Distillation Unit 101",
        shift_type=ShiftType.DAY,
        shift_date="2026-08-22",
        outgoing_operator_id="op_console_01",
        outgoing_operator_name="Ahmed Al-Mansoor",
        incoming_operator_id="op_incoming_02",
        incoming_operator_name="Sultan Al-Otaibi",
        supervisor_id="sup_khalid",
        operational_summary=operational_summary,
        equipment_abnormalities=["P-101B out of service for seal replacement"],
        open_permits=["PTW-8821 (Mechanical Work)"],
        loto_isolations=["LOTO-CDU-101-042 (P-101B suction & discharge valves tagged)"],
        carry_forward_actions=["Monitor P-101A vibration at 18:00"],
        safety_items=safety_items,
        all_safety_items_acknowledged=safety_acknowledged
    )


# --- Test Cases ---

def test_1_initial_state():
    """Test 1: Verify a newly created handover starts in DRAFT state with version=1 and audit record."""
    engine = ShiftHandoverWorkflowEngine()
    data = sample_handover_data()
    handover, res = engine.create_handover(
        data=data,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    assert handover.state == ShiftHandoverState.DRAFT
    assert handover.version == 1
    assert handover.workflow_version == "1.0.0"
    assert handover.is_terminal is False
    assert res.success is True
    assert len(handover.audit_trail) == 1
    assert handover.audit_trail[0].action == ShiftHandoverAction.CREATE


def test_2_valid_transition_submit():
    """Test 2: Verify DRAFT -> SUBMIT -> SUBMITTED by outgoing console operator."""
    engine = ShiftHandoverWorkflowEngine()
    handover, _ = engine.create_handover(
        data=sample_handover_data(),
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    res = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    assert res.success is True
    assert handover.state == ShiftHandoverState.SUBMITTED
    assert handover.version == 2
    assert handover.submitted_at is not None
    assert len(handover.audit_trail) == 2


def test_3_invalid_transition():
    """Test 3: Verify invalid action DRAFT -> ACKNOWLEDGE fails safely with rejection."""
    engine = ShiftHandoverWorkflowEngine()
    handover, _ = engine.create_handover(
        data=sample_handover_data(),
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    res = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.ACKNOWLEDGE,
        actor_id="op_incoming_02",
        actor_role=ShiftHandoverRole.INCOMING_OPERATOR
    )

    assert res.success is False
    assert handover.state == ShiftHandoverState.DRAFT
    assert "INVALID_STATE_ACTION" in res.validation_errors


def test_4_role_authorization():
    """Test 4: Verify unauthorized role (e.g. FIELD_OPERATOR attempting APPROVE) is blocked."""
    engine = ShiftHandoverWorkflowEngine()
    handover, _ = engine.create_handover(
        data=sample_handover_data(),
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    # Submit first
    engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    # Field operator attempts to approve
    res = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.APPROVE,
        actor_id="op_field_03",
        actor_role=ShiftHandoverRole.FIELD_OPERATOR
    )

    assert res.success is False
    assert "ROLE_UNAUTHORIZED" in res.validation_errors
    assert handover.state == ShiftHandoverState.SUBMITTED


def test_5_required_field_validation():
    """Test 5: Verify submission fails if mandatory operational summary is missing."""
    engine = ShiftHandoverWorkflowEngine()
    bad_data = sample_handover_data(operational_summary="")
    handover, _ = engine.create_handover(
        data=bad_data,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    res = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    assert res.success is False
    assert handover.state == ShiftHandoverState.DRAFT
    assert any("operational_summary" in err for err in res.validation_errors)


def test_6_return_flow():
    """Test 6: Verify SUBMITTED -> RETURN -> RETURNED -> SAVE -> SUBMIT flow."""
    engine = ShiftHandoverWorkflowEngine()
    handover, _ = engine.create_handover(
        data=sample_handover_data(),
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    # Supervisor returns with reason
    res_return = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.RETURN,
        actor_id="sup_khalid",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR,
        reason="Please include latest flare header pressure log."
    )
    assert res_return.success is True
    assert handover.state == ShiftHandoverState.RETURNED

    # Outgoing operator updates notes and resubmits
    res_save = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SAVE,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        payload_updates={"notes": "Flare header pressure logged at 0.15 barg."}
    )
    assert res_save.success is True
    assert handover.state == ShiftHandoverState.RETURNED
    assert handover.data.notes == "Flare header pressure logged at 0.15 barg."

    res_resubmit = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    assert res_resubmit.success is True
    assert handover.state == ShiftHandoverState.SUBMITTED


def test_7_acknowledgement_flow():
    """Test 7: Verify complete path: SUBMITTED -> REVIEW -> APPROVE -> ACKNOWLEDGE -> COMPLETED."""
    engine = ShiftHandoverWorkflowEngine()
    handover, _ = engine.create_handover(
        data=sample_handover_data(),
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    # Supervisor begins formal review
    res_review = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.REVIEW,
        actor_id="sup_khalid",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR
    )
    assert res_review.success is True
    assert handover.state == ShiftHandoverState.PENDING_REVIEW

    # Supervisor approves
    res_approve = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.APPROVE,
        actor_id="sup_khalid",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR
    )
    assert res_approve.success is True
    assert handover.state == ShiftHandoverState.PENDING_ACKNOWLEDGEMENT

    # Incoming operator acknowledges and accepts
    res_ack = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.ACKNOWLEDGE,
        actor_id="op_incoming_02",
        actor_role=ShiftHandoverRole.INCOMING_OPERATOR
    )
    assert res_ack.success is True
    assert handover.state == ShiftHandoverState.COMPLETED
    assert handover.is_terminal is True
    assert handover.completed_at is not None


def test_8_completion_safety_validation():
    """Test 8: Verify ACKNOWLEDGE -> COMPLETED fails if active safety items are unacknowledged."""
    engine = ShiftHandoverWorkflowEngine()
    data = sample_handover_data(include_safety_item=True, safety_acknowledged=False)
    handover, _ = engine.create_handover(
        data=data,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.APPROVE,
        actor_id="sup_khalid",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR
    )

    # Attempt to acknowledge without checking safety item
    res_ack_fail = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.ACKNOWLEDGE,
        actor_id="op_incoming_02",
        actor_role=ShiftHandoverRole.INCOMING_OPERATOR
    )
    assert res_ack_fail.success is False
    assert handover.state == ShiftHandoverState.PENDING_ACKNOWLEDGEMENT
    assert any("P-101B" in err for err in res_ack_fail.validation_errors)

    # Now acknowledge safety item
    handover.data.safety_items[0].acknowledged_by_incoming = True
    handover.data.all_safety_items_acknowledged = True

    res_ack_success = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.ACKNOWLEDGE,
        actor_id="op_incoming_02",
        actor_role=ShiftHandoverRole.INCOMING_OPERATOR
    )
    assert res_ack_success.success is True
    assert handover.state == ShiftHandoverState.COMPLETED


def test_9_terminal_state_protection():
    """Test 9: Verify completed handover cannot be modified through normal workflow actions."""
    engine = ShiftHandoverWorkflowEngine()
    handover, _ = engine.create_handover(
        data=sample_handover_data(),
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.ACKNOWLEDGE,
        actor_id="op_incoming_02",
        actor_role=ShiftHandoverRole.INCOMING_OPERATOR
    )
    assert handover.state == ShiftHandoverState.COMPLETED

    # Attempt to edit or save completed handover
    res = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SAVE,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    assert res.success is False
    assert "TERMINAL_STATE_LOCKED" in res.validation_errors


def test_10_audit_trail_and_result():
    """Test 10: Verify transition output contains complete audit record with timestamps and actors."""
    engine = ShiftHandoverWorkflowEngine()
    handover, _ = engine.create_handover(
        data=sample_handover_data(),
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    res = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    audit = res.audit_entry
    assert audit is not None
    assert audit.handover_id == handover.handover_id
    assert audit.from_state == ShiftHandoverState.DRAFT
    assert audit.to_state == ShiftHandoverState.SUBMITTED
    assert audit.action == ShiftHandoverAction.SUBMIT
    assert audit.actor_id == "op_console_01"
    assert audit.actor_role == ShiftHandoverRole.CONSOLE_OPERATOR
    assert audit.timestamp is not None


def test_11_reason_validation():
    """Test 11: Verify actions requiring reasons (RETURN, REJECT, CANCEL) reject missing reasons."""
    engine = ShiftHandoverWorkflowEngine()
    handover, _ = engine.create_handover(
        data=sample_handover_data(),
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    # Cancel without reason
    res_cancel_fail = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.CANCEL,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        reason=""
    )
    assert res_cancel_fail.success is False
    assert "MISSING_MANDATORY_REASON" in res_cancel_fail.validation_errors

    # Cancel with reason
    res_cancel_ok = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.CANCEL,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        reason="Unit shutdown postponed by plant superintendent."
    )
    assert res_cancel_ok.success is True
    assert handover.state == ShiftHandoverState.CANCELLED


def test_12_concurrency_version_protection():
    """Test 12: Verify version mismatch prevents race condition transitions."""
    engine = ShiftHandoverWorkflowEngine()
    handover, _ = engine.create_handover(
        data=sample_handover_data(),
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )
    assert handover.version == 1

    # Pass outdated expected_version 0
    res = engine.execute_transition(
        handover=handover,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=0
    )
    assert res.success is False
    assert "CONCURRENCY_VERSION_MISMATCH" in res.validation_errors
    assert handover.state == ShiftHandoverState.DRAFT


def test_13_unknown_action_or_state():
    """Test 13: Verify helper can_perform_action and get_available_actions operate deterministically."""
    engine = ShiftHandoverWorkflowEngine()
    handover, _ = engine.create_handover(
        data=sample_handover_data(),
        actor_id="op_console_01",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR
    )

    can_sub, _ = engine.can_perform_action(handover, ShiftHandoverAction.SUBMIT, ShiftHandoverRole.CONSOLE_OPERATOR)
    assert can_sub is True

    can_app, _ = engine.can_perform_action(handover, ShiftHandoverAction.APPROVE, ShiftHandoverRole.CONSOLE_OPERATOR)
    assert can_app is False

    actions = engine.get_available_actions(handover, ShiftHandoverRole.CONSOLE_OPERATOR)
    assert ShiftHandoverAction.SUBMIT in actions
    assert ShiftHandoverAction.SAVE in actions
    assert ShiftHandoverAction.CANCEL in actions


def test_14_workflow_version_and_metadata():
    """Test 14: Verify declarative workflow definition contains version, states, and roles."""
    assert WORKFLOW_DEFINITION["workflow_code"] == "SHIFT_HANDOVER"
    assert WORKFLOW_DEFINITION["version"] == "1.0.0"
    assert len(WORKFLOW_DEFINITION["states"]) >= 8
    assert len(WORKFLOW_DEFINITION["roles"]) >= 8
    assert len(TRANSITION_RULES) >= 12
