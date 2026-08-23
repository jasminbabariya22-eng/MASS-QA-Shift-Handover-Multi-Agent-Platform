import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.shift_handover import (
    ShiftHandoverModel,
    SafetyCriticalItemModel,
    ShiftHandoverAuditModel,
)
from app.repositories.shift_handover_repository import (
    ShiftHandoverRepository,
    ShiftHandoverNotFoundError,
    ConcurrencyConflictError,
    TerminalStateError,
)
from app.services.shift_handover_service import (
    ShiftHandoverService,
    shift_handover_service,
)
from app.agents.shift.contracts import (
    ShiftHandoverData,
    ShiftHandoverState,
    ShiftHandoverRole,
    ShiftHandoverAction,
    SafetyCriticalItem,
    ShiftType,
)


@pytest.fixture(scope="function")
def db_session():
    """Create a transactional database session for each test that rolls back cleanly or cleans up test rows."""
    session = SessionLocal()
    created_handover_ids = []

    class TrackedSession:
        def __init__(self, s):
            self._s = s

        def track(self, hid):
            if hid not in created_handover_ids:
                created_handover_ids.append(hid)

        def __getattr__(self, name):
            return getattr(self._s, name)

    tracked = TrackedSession(session)
    try:
        yield tracked
    finally:
        # Cleanup any created test handovers and related cascaded tables
        try:
            if created_handover_ids:
                session.query(ShiftHandoverModel).filter(
                    ShiftHandoverModel.id.in_(created_handover_ids)
                ).delete(synchronize_session=False)
                session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()


def create_sample_data(unit_id: str = "CDU-101", summary: str = "Nominal operation 100 kbpd.") -> ShiftHandoverData:
    return ShiftHandoverData(
        unit_id=unit_id,
        unit_name="Crude Distillation Unit",
        shift_type=ShiftType.DAY,
        shift_date="2026-08-22",
        outgoing_operator_id="op_outgoing_101",
        outgoing_operator_name="Tariq Mansoor",
        incoming_operator_id="op_incoming_202",
        incoming_operator_name="Faisal Al-Dosari",
        supervisor_id="sup_salem",
        operational_summary=summary,
        equipment_abnormalities=["P-101A vibration normal, P-101B on standby"],
        open_permits=["PTW-4401"],
        loto_isolations=["LOTO-091"],
        carry_forward_actions=["Sample naphtha tank at 16:00"],
        safety_items=[],
        all_safety_items_acknowledged=False
    )


# --- Test Cases ---

def test_1_create_handover_persistence(db_session):
    """Test 1: Create a handover and verify DRAFT state, version=1, timestamps, and reference number."""
    data = create_sample_data()
    model = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(model.id)

    assert model.id is not None
    assert model.state == "DRAFT"
    assert model.version == 1
    assert model.workflow_code == "SHIFT_HANDOVER"
    assert model.workflow_version == "1.0.0"
    assert model.handover_number.startswith("SHO-20260822-CDU101-")
    assert model.created_at is not None


def test_2_read_handover_persistence(db_session):
    """Test 2: Retrieve the handover and verify persisted data and relationships."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    fetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.unit_id == "CDU-101"
    assert len(fetched.audit_trail) == 1
    assert fetched.audit_trail[0].action == "CREATE"


def test_3_update_handover_data(db_session):
    """Test 3: Update mutable handover information in DRAFT and verify persistence."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    updated = ShiftHandoverRepository.update_data(
        db=db_session,
        handover_id=created.id,
        expected_version=1,
        updates={"operational_summary": "Throughput increased to 115 kbpd.", "notes": "Feed quality light crude."},
        actor_id="op_outgoing_101"
    )
    db_session.commit()

    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert "115 kbpd" in refetched.operational_summary
    assert refetched.notes == "Feed quality light crude."


def test_4_submit_transaction(db_session):
    """Test 4: Verify DRAFT -> SUBMITTED and audit entry created atomically in single transaction."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    res = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    db_session.commit()

    assert res.success is True
    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.state == "SUBMITTED"
    assert refetched.version == 2
    assert refetched.submitted_at is not None
    assert len(refetched.audit_trail) == 2


def test_5_review_transaction(db_session):
    """Test 5: Verify SUBMITTED -> PENDING_REVIEW by shift supervisor."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    db_session.commit()

    res = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.REVIEW,
        actor_id="sup_salem",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR,
        expected_version=2
    )
    db_session.commit()

    assert res.success is True
    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.state == "PENDING_REVIEW"
    assert refetched.version == 3


def test_6_approval_transaction(db_session):
    """Test 6: Verify PENDING_REVIEW -> PENDING_ACKNOWLEDGEMENT by shift supervisor."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.REVIEW,
        actor_id="sup_salem",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR,
        expected_version=2
    )
    db_session.commit()

    res = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.APPROVE,
        actor_id="sup_salem",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR,
        expected_version=3
    )
    db_session.commit()

    assert res.success is True
    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.state == "PENDING_ACKNOWLEDGEMENT"
    assert refetched.version == 4


def test_7_return_transaction(db_session):
    """Test 7: Verify PENDING_REVIEW -> RETURNED and mandatory reason is persisted."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    db_session.commit()

    res = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.RETURN,
        actor_id="sup_salem",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR,
        expected_version=2,
        reason="Please verify stabilizer column reboiler steam flow rate."
    )
    db_session.commit()

    assert res.success is True
    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.state == "RETURNED"
    assert refetched.audit_trail[-1].reason == "Please verify stabilizer column reboiler steam flow rate."


def test_8_rejection_transaction(db_session):
    """Test 8: Verify PENDING_REVIEW -> REJECTED and reason is persisted."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    db_session.commit()

    res = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.REJECT,
        actor_id="sup_salem",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR,
        expected_version=2,
        reason="Severe safety interlock bypass violation detected."
    )
    db_session.commit()

    assert res.success is True
    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.state == "REJECTED"
    assert refetched.is_terminal is True
    assert refetched.rejected_at is not None


def test_9_resubmission(db_session):
    """Test 9: Verify RETURNED -> SUBMITTED resubmission cycle."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    # Submit -> Return
    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.RETURN,
        actor_id="sup_salem",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR,
        expected_version=2,
        reason="Add flare pressure details."
    )
    db_session.commit()

    # Resubmit
    res = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=3,
        payload_updates={"notes": "Flare pressure logged at 0.12 barg."}
    )
    db_session.commit()

    assert res.success is True
    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.state == "SUBMITTED"
    assert refetched.version == 4


def test_10_safety_item_persistence(db_session):
    """Test 10: Create and retrieve safety-critical items attached to a handover."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    item = ShiftHandoverRepository.add_safety_item(
        db=db_session,
        handover_id=created.id,
        category="LOTO",
        equipment_tag="E-101A",
        description="Heat exchanger bundle isolated for high-pressure washing."
    )
    db_session.commit()

    assert item.id is not None
    assert item.equipment_tag == "E-101A"
    assert item.active is True
    assert item.acknowledged_by_incoming is False

    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert len(refetched.safety_items) == 1
    assert refetched.safety_items[0].equipment_tag == "E-101A"


def test_11_safety_acknowledgement(db_session):
    """Test 11: Verify safety item acknowledgement data persists."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    item = ShiftHandoverRepository.add_safety_item(
        db=db_session,
        handover_id=created.id,
        category="PERMIT_TO_WORK",
        equipment_tag="V-102",
        description="Confined space entry permit #PTW-991 active."
    )
    db_session.commit()
    db_session.track(created.id)

    ack_item = ShiftHandoverRepository.acknowledge_safety_item(
        db=db_session,
        item_id=item.id,
        actor_id="op_incoming_202"
    )
    db_session.commit()

    assert ack_item.acknowledged_by_incoming is True
    assert ack_item.acknowledged_by == "op_incoming_202"
    assert ack_item.acknowledged_at is not None


def test_12_completion_with_safety_check(db_session):
    """Test 12: Verify PENDING_ACKNOWLEDGEMENT -> COMPLETED only when required safety conditions are met."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary,
        incoming_operator_id="op_incoming_202"
    )
    item = ShiftHandoverRepository.add_safety_item(
        db=db_session,
        handover_id=created.id,
        category="ESD_BYPASS",
        equipment_tag="XV-301",
        description="ESD valve bypass authorized by OIM under MOS-102."
    )
    db_session.commit()
    db_session.track(created.id)

    # Submit and fast-track approve
    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.APPROVE,
        actor_id="sup_salem",
        actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR,
        expected_version=2
    )
    db_session.commit()

    # Attempt to complete without acknowledging safety item -> Fails
    res_fail = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.ACKNOWLEDGE,
        actor_id="op_incoming_202",
        actor_role=ShiftHandoverRole.INCOMING_OPERATOR,
        expected_version=3
    )
    assert res_fail.success is False
    assert any("XV-301" in err for err in res_fail.validation_errors)

    # Acknowledge safety item
    ShiftHandoverRepository.acknowledge_safety_item(db=db_session, item_id=item.id, actor_id="op_incoming_202")
    db_session.commit()

    # Attempt completion again -> Succeeds
    res_ok = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.ACKNOWLEDGE,
        actor_id="op_incoming_202",
        actor_role=ShiftHandoverRole.INCOMING_OPERATOR,
        expected_version=3
    )
    db_session.commit()

    assert res_ok.success is True
    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.state == "COMPLETED"
    assert refetched.is_terminal is True
    assert refetched.completed_at is not None


def test_13_terminal_protection(db_session):
    """Test 13: Verify completed records cannot be transitioned or modified."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary,
        incoming_operator_id="op_incoming_202"
    )
    db_session.commit()
    db_session.track(created.id)

    # Submit -> Acknowledge -> Complete
    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.ACKNOWLEDGE,
        actor_id="op_incoming_202",
        actor_role=ShiftHandoverRole.INCOMING_OPERATOR,
        expected_version=2
    )
    db_session.commit()

    # Attempt to transition completed handover
    res = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SAVE,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=3
    )
    assert res.success is False
    assert "TERMINAL_STATE_LOCKED" in res.validation_errors


def test_14_audit_history_immutability(db_session):
    """Test 14: Verify every transition creates an immutable audit record with timestamps and actors."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    db_session.commit()

    audits = ShiftHandoverRepository.get_audit_trail(db_session, created.id)
    assert len(audits) == 2
    assert audits[0].action == "CREATE"
    assert audits[1].action == "SUBMIT"
    assert audits[1].from_state == "DRAFT"
    assert audits[1].to_state == "SUBMITTED"
    assert audits[1].actor_id == "op_outgoing_101"
    assert audits[1].created_at is not None


def test_15_atomic_rollback_on_failure(db_session):
    """Test 15: Verify forced database failure rolls back state change and audit insertion cleanly."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    # Force a version conflict
    with pytest.raises(ConcurrencyConflictError):
        ShiftHandoverRepository.execute_transition_atomic(
            db=db_session,
            handover_id=created.id,
            from_state="DRAFT",
            to_state="SUBMITTED",
            action="SUBMIT",
            actor_id="op_outgoing_101",
            actor_role="CONSOLE_OPERATOR",
            expected_version=999  # Wrong version
        )
    db_session.rollback()

    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.state == "DRAFT"
    assert refetched.version == 1
    assert len(refetched.audit_trail) == 1


def test_16_optimistic_locking_concurrency_conflict(db_session):
    """Test 16: Two concurrent actions with same expected version produce one success and one ConcurrencyConflictError."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    # First transition with expected_version=1 succeeds
    res1 = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    db_session.commit()
    assert res1.success is True

    # Second concurrent transition still using expected_version=1 must raise ConcurrencyConflictError
    with pytest.raises(ConcurrencyConflictError):
        shift_handover_service.transition_handover(
            db=db_session,
            handover_id=created.id,
            action=ShiftHandoverAction.REVIEW,
            actor_id="sup_salem",
            actor_role=ShiftHandoverRole.SHIFT_SUPERVISOR,
            expected_version=1  # Stale version!
        )


def test_17_version_increment(db_session):
    """Test 17: Verify every successful transition increments version by exactly 1."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)
    assert created.version == 1

    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    db_session.commit()

    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.version == 2


def test_18_invalid_role_blocked(db_session):
    """Test 18: Unauthorized transition blocked by service and leaves database untouched."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    # Submit first
    shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    db_session.commit()

    # Field operator attempts to approve
    res = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.APPROVE,
        actor_id="op_field_03",
        actor_role=ShiftHandoverRole.FIELD_OPERATOR,
        expected_version=2
    )

    assert res.success is False
    assert "ROLE_UNAUTHORIZED" in res.validation_errors

    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.state == "SUBMITTED"
    assert refetched.version == 2


def test_19_missing_reason_rejected(db_session):
    """Test 19: Actions requiring reason (CANCEL, RETURN, REJECT) reject empty reason."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    res = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.CANCEL,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1,
        reason=""  # Empty reason!
    )

    assert res.success is False
    assert "MISSING_MANDATORY_REASON" in res.validation_errors
    refetched = ShiftHandoverRepository.get_by_id(db_session, created.id)
    assert refetched.state == "DRAFT"


def test_20_duplicate_transition_safety(db_session):
    """Test 20: Repeated submission does not produce invalid state changes."""
    data = create_sample_data()
    created = ShiftHandoverRepository.create_handover(
        db=db_session,
        unit_id=data.unit_id,
        shift_type=data.shift_type.value,
        shift_date=data.shift_date,
        outgoing_operator_id=data.outgoing_operator_id,
        operational_summary=data.operational_summary
    )
    db_session.commit()
    db_session.track(created.id)

    # First SUBMIT succeeds
    res1 = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=1
    )
    db_session.commit()
    assert res1.success is True

    # Immediate second SUBMIT attempt
    res2 = shift_handover_service.transition_handover(
        db=db_session,
        handover_id=created.id,
        action=ShiftHandoverAction.SUBMIT,
        actor_id="op_outgoing_101",
        actor_role=ShiftHandoverRole.CONSOLE_OPERATOR,
        expected_version=2
    )

    assert res2.success is False
    assert "INVALID_STATE_ACTION" in res2.validation_errors
