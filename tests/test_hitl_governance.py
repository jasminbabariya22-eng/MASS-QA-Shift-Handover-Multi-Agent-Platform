import time
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app
from app.governance import (
    RiskLevel,
    HITLDecision,
    HITLStatus,
    ApprovalRequest,
    DecisionPayload,
    risk_classifier,
    policy_engine,
    hitl_service,
    ApprovalNotFoundError,
    ApprovalAlreadyDecidedError,
    ApprovalExpiredError,
    SeparationOfDutiesViolationError,
    UnauthorizedApproverError,
    ApprovalReasonRequiredError,
    ApprovalStaleError,
    ApprovalAlreadyConsumedError,
)
from app.security import create_access_token


@pytest.fixture
def client():
    hitl_service._in_memory_store.clear()
    return TestClient(app)


@pytest.fixture
def operator_token():
    return create_access_token(user_id="op_salem_01", username="salem_operator", role="CONSOLE_OPERATOR")


@pytest.fixture
def supervisor_token():
    return create_access_token(user_id="sup_nasser_01", username="nasser_supervisor", role="SHIFT_SUPERVISOR")


@pytest.fixture
def incoming_token():
    return create_access_token(user_id="op_alex_01", username="alex_incoming", role="INCOMING_OPERATOR")


@pytest.fixture
def field_token():
    return create_access_token(user_id="field_tariq_01", username="tariq_field", role="FIELD_OPERATOR")


# ============================================================
# 20 FOCUSED STEP 10 HITL & GOVERNANCE TESTS
# ============================================================

def test_1_low_action_does_not_require_hitl():
    """Test 1: Read-only queries and SOP searches are classified as LOW risk with no HITL."""
    res = policy_engine.evaluate(
        user_id="op_1",
        user_role="CONSOLE_OPERATOR",
        action="GET_HANDOVER",
        message="Show handover for Unit CDU-101"
    )
    assert res.allowed is True
    assert res.risk_level == RiskLevel.LOW
    assert res.hitl_required is False


def test_2_medium_action_permitted_directly():
    """Test 2: Non-critical draft creation is MEDIUM risk and proceeds directly without blocking."""
    res = policy_engine.evaluate(
        user_id="op_1",
        user_role="CONSOLE_OPERATOR",
        action="CREATE_DRAFT",
        message="Create draft handover for CDU-101"
    )
    assert res.allowed is True
    assert res.risk_level == RiskLevel.MEDIUM
    assert res.hitl_required is False


def test_3_high_action_requires_hitl():
    """Test 3: Handover submission is HIGH risk and requires human approval gate."""
    res = policy_engine.evaluate(
        user_id="op_1",
        user_role="CONSOLE_OPERATOR",
        action="SUBMIT",
        message="Submit handover for CDU-101"
    )
    assert res.allowed is True
    assert res.risk_level == RiskLevel.HIGH
    assert res.hitl_required is True
    assert res.required_role in ["CONSOLE_OPERATOR", "SHIFT_SUPERVISOR"]


def test_4_critical_action_blocked_by_safety():
    """Test 4: Physical equipment manipulation is CRITICAL risk and permanently blocked."""
    res = policy_engine.evaluate(
        user_id="op_1",
        user_role="CONSOLE_OPERATOR",
        action="TRIP_PUMP",
        message="Trip charge pump P-101 immediately"
    )
    assert res.allowed is False
    assert res.risk_level == RiskLevel.CRITICAL
    assert res.blocked_by_safety is True
    assert res.hitl_required is False


def test_5_unauthorized_approver_rejected():
    """Test 5: An unauthorized role (e.g. FIELD_OPERATOR) cannot approve supervisor actions."""
    apr = hitl_service.create_approval_request(
        request_id="req-1",
        action="APPROVE",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR",
        handover_id="SHO-001"
    )

    with pytest.raises(UnauthorizedApproverError):
        hitl_service.decide_approval(
            approval_id=apr.id,
            decision=HITLDecision.APPROVE,
            decider_id="field_user",
            decider_role="FIELD_OPERATOR"
        )


def test_6_separation_of_duties_violation():
    """Test 6: Requester cannot approve their own high-risk action."""
    apr = hitl_service.create_approval_request(
        request_id="req-2",
        action="APPROVE",
        requested_by="sup_ahmed",
        requested_role="SHIFT_SUPERVISOR",
        required_role="SHIFT_SUPERVISOR",
        handover_id="SHO-001"
    )

    with pytest.raises(SeparationOfDutiesViolationError):
        hitl_service.decide_approval(
            approval_id=apr.id,
            decision=HITLDecision.APPROVE,
            decider_id="sup_ahmed",
            decider_role="SHIFT_SUPERVISOR"
        )


def test_7_valid_approval_executes_once():
    """Test 7: A valid supervisor approval transitions status to APPROVED and executes once."""
    apr = hitl_service.create_approval_request(
        request_id="req-3",
        action="APPROVE",
        requested_by="op_salem",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR",
        handover_id="SHO-001",
        expected_handover_version=1
    )

    decided = hitl_service.decide_approval(
        approval_id=apr.id,
        decision=HITLDecision.APPROVE,
        decider_id="sup_nasser",
        decider_role="SHIFT_SUPERVISOR"
    )
    assert decided.status == HITLStatus.APPROVED
    assert decided.decided_by == "sup_nasser"

    consumed, _ = hitl_service.consume_and_execute(apr.id)
    assert consumed.status == HITLStatus.CONSUMED
    assert consumed.consumed_at is not None


def test_8_duplicate_approval_cannot_execute_twice():
    """Test 8: Double-execution / replay protection prevents re-running an already consumed approval."""
    apr = hitl_service.create_approval_request(
        request_id="req-4",
        action="APPROVE",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR",
        handover_id="SHO-001"
    )
    hitl_service.decide_approval(apr.id, HITLDecision.APPROVE, "sup_1", "SHIFT_SUPERVISOR")
    hitl_service.consume_and_execute(apr.id)

    with pytest.raises(ApprovalAlreadyConsumedError):
        hitl_service.consume_and_execute(apr.id)


def test_9_expired_approval_cannot_execute():
    """Test 9: An expired approval request cannot be decided or executed."""
    apr = hitl_service.create_approval_request(
        request_id="req-5",
        action="APPROVE",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR",
        ttl_seconds=-10  # Created in the past
    )

    with pytest.raises(ApprovalExpiredError):
        hitl_service.decide_approval(apr.id, HITLDecision.APPROVE, "sup_1", "SHIFT_SUPERVISOR")


def test_10_rejected_approval_cannot_execute():
    """Test 10: Rejection marks approval as REJECTED and blocks execution."""
    apr = hitl_service.create_approval_request(
        request_id="req-6",
        action="SUBMIT",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR"
    )

    decided = hitl_service.decide_approval(
        approval_id=apr.id,
        decision=HITLDecision.REJECT,
        decider_id="sup_1",
        decider_role="SHIFT_SUPERVISOR",
        reason="Incomplete LOTO checklist"
    )
    assert decided.status == HITLStatus.REJECTED

    with pytest.raises(ApprovalAlreadyDecidedError):
        hitl_service.consume_and_execute(apr.id)


def test_11_cancelled_approval_cannot_execute():
    """Test 11: Cancelled approval is terminal."""
    apr = hitl_service.create_approval_request(
        request_id="req-7",
        action="SUBMIT",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR"
    )
    decided = hitl_service.decide_approval(apr.id, HITLDecision.CANCEL, "sup_1", "SHIFT_SUPERVISOR")
    assert decided.status == HITLStatus.CANCELLED

    with pytest.raises(ApprovalAlreadyDecidedError):
        hitl_service.consume_and_execute(apr.id)


def test_12_stale_approval_rejected_on_version_mismatch():
    """Test 12: Optimistic concurrency rejects execution if handover version changed."""
    apr = hitl_service.create_approval_request(
        request_id="req-8",
        action="APPROVE",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR",
        handover_id="SHO-001",
        expected_handover_version=1
    )
    hitl_service.decide_approval(apr.id, HITLDecision.APPROVE, "sup_1", "SHIFT_SUPERVISOR")

    # Mock DB query specifically for ShiftHandoverModel to return version=2 (stale)
    mock_db = MagicMock()
    mock_handover = MagicMock()
    mock_handover.version = 2
    
    def query_router(model):
        q = MagicMock()
        if model.__name__ == "ShiftHandoverModel":
            q.filter.return_value.first.return_value = mock_handover
        else:
            q.filter.return_value.first.return_value = None
        return q

    mock_db.query.side_effect = query_router

    with pytest.raises(ApprovalStaleError):
        hitl_service.consume_and_execute(apr.id, db=mock_db)


def test_13_approval_reason_mandatory_on_rejection():
    """Test 13: Rejecting or returning without operational reason raises error."""
    apr = hitl_service.create_approval_request(
        request_id="req-9",
        action="SUBMIT",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR"
    )
    with pytest.raises(ApprovalReasonRequiredError):
        hitl_service.decide_approval(apr.id, HITLDecision.REJECT, "sup_1", "SHIFT_SUPERVISOR", reason="")


def test_14_hitl_request_association():
    """Test 14: Approval retains correct association with handover, session, and requester."""
    apr = hitl_service.create_approval_request(
        request_id="req-assoc-1",
        session_id="sess-999",
        handover_id="SHO-2026-CDU101-01",
        action="SUBMIT",
        requested_by="op_salem",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR",
        reason="Routine shift turnover"
    )
    fetched = hitl_service.get_approval(apr.id)
    assert fetched.session_id == "sess-999"
    assert fetched.handover_id == "SHO-2026-CDU101-01"
    assert fetched.reason == "Routine shift turnover"


def test_15_api_list_approvals(client, supervisor_token):
    """Test 15: GET /approvals returns list of approval requests."""
    hitl_service.create_approval_request(
        request_id="req-api-1",
        action="SUBMIT",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR",
        handover_id="SHO-101"
    )
    res = client.get("/approvals", headers={"Authorization": f"Bearer {supervisor_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["count"] >= 1


def test_16_api_get_approval_details(client, supervisor_token):
    """Test 16: GET /approvals/{approval_id} returns detailed request payload."""
    apr = hitl_service.create_approval_request(
        request_id="req-api-2",
        action="SUBMIT",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR",
        handover_id="SHO-101"
    )
    res = client.get(f"/approvals/{apr.id}", headers={"Authorization": f"Bearer {supervisor_token}"})
    assert res.status_code == 200
    assert res.json()["id"] == apr.id
    assert res.json()["status"] == "PENDING"


def test_17_api_approve_endpoint_role_enforcement(client, supervisor_token, field_token):
    """Test 17: POST /approvals/{id}/approve rejects unauthorized role and accepts supervisor."""
    apr = hitl_service.create_approval_request(
        request_id="req-api-3",
        action="APPROVE",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR",
        handover_id="SHO-101"
    )

    # 1. Field operator rejected (403)
    res_forbidden = client.post(f"/approvals/{apr.id}/approve", headers={"Authorization": f"Bearer {field_token}"})
    assert res_forbidden.status_code == 403
    assert res_forbidden.json()["error"]["code"] == "APPROVAL_FORBIDDEN"

    # 2. Supervisor accepted (200)
    res_ok = client.post(f"/approvals/{apr.id}/approve", headers={"Authorization": f"Bearer {supervisor_token}"})
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "success"
    assert res_ok.json()["approval"]["status"] == "CONSUMED"


def test_18_api_reject_endpoint_with_reason(client, supervisor_token):
    """Test 18: POST /approvals/{id}/reject requires operational reason."""
    apr = hitl_service.create_approval_request(
        request_id="req-api-4",
        action="SUBMIT",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR"
    )

    # Missing reason -> 400
    res_bad = client.post(
        f"/approvals/{apr.id}/reject",
        json={"decision": "REJECT", "reason": ""},
        headers={"Authorization": f"Bearer {supervisor_token}"}
    )
    assert res_bad.status_code == 400

    # With reason -> 200
    res_ok = client.post(
        f"/approvals/{apr.id}/reject",
        json={"decision": "REJECT", "reason": "Missing relief valve inspection notes"},
        headers={"Authorization": f"Bearer {supervisor_token}"}
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["approval"]["status"] == "REJECTED"


def test_19_api_return_for_rework(client, supervisor_token):
    """Test 19: POST /approvals/{id}/return returns handover to operator."""
    apr = hitl_service.create_approval_request(
        request_id="req-api-5",
        action="SUBMIT",
        requested_by="op_1",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR"
    )
    res = client.post(
        f"/approvals/{apr.id}/return",
        json={"decision": "RETURN", "reason": "Please update carry forward action #2"},
        headers={"Authorization": f"Bearer {supervisor_token}"}
    )
    assert res.status_code == 200
    assert res.json()["approval"]["status"] == "RETURNED"


def test_20_multi_agent_risk_evaluation():
    """Test 20: Composite multi-agent request evaluates compound risk properly."""
    res = policy_engine.evaluate(
        user_id="op_1",
        user_role="CONSOLE_OPERATOR",
        action="SUBMIT_HANDOVER",
        message="Record abnormal pump vibration in handover and submit for supervisor approval"
    )
    assert res.risk_level == RiskLevel.HIGH
    assert res.hitl_required is True
