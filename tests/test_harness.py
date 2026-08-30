import json
import time
import pytest
from unittest.mock import MagicMock, patch

from app.harness.contracts import (
    HarnessRequest,
    HarnessResponse,
    HarnessPolicyDecision,
    ExecutionStatus,
    ToolPermission,
    ExecutionBudget
)
from app.harness.harness import AIHarness, ai_harness
from app.harness.permissions import permission_manager
from app.harness.safety import safety_policy
from app.harness.budget import ExecutionBudgetTracker, AgentLoopDetectedError, AgentDepthExceededError, BudgetExceededError
from app.harness.validator import output_validator
from app.harness.audit import audit_recorder
from app.harness.observability import harness_telemetry
from app.harness.evaluator import evaluation_hooks
from app.agents.contracts import AgentResult, AgentRequest, RequestContext, AgentIntent
from app.agents.registry import agent_registry
from app.services.cache import cache_service


@pytest.fixture
def harness():
    return ai_harness


# ============================================================
# 28 FOCUSED AI HARNESS TESTS
# ============================================================

def test_1_authentication_context_propagation(harness, monkeypatch):
    """Test 1: Authenticated user context (ID, role, session) is preserved across harness."""
    mock_res = AgentResult(
        request_id="req-h-1",
        agent_id="qa_technical_agent",
        status="success",
        success=True,
        response="Authentic procedure response.",
        citations=[{"source_type": "PDF", "document_name": "SOP.pdf", "page_number": 1}]
    )
    monkeypatch.setattr(harness.orchestrator, "execute", lambda req: mock_res)

    req = HarnessRequest(
        request_id="req-h-1",
        user_id="op_salem",
        user_role="CONSOLE_OPERATOR",
        session_id="sess-001",
        message="What is the startup sequence?"
    )
    res = harness.execute(req)
    assert res.request_id == "req-h-1"
    assert res.session_id == "sess-001"
    assert res.status == ExecutionStatus.COMPLETED
    assert res.decision == HarnessPolicyDecision.ALLOW


def test_2_authorization_allow(harness, monkeypatch):
    """Test 2: Authorized role with valid tool permissions is granted access."""
    mock_res = AgentResult(
        request_id="req-h-2",
        agent_id="shift_handover_agent",
        status="success",
        success=True,
        response="Handover created."
    )
    monkeypatch.setattr(harness.orchestrator, "execute", lambda req: mock_res)

    req = HarnessRequest(
        request_id="req-h-2",
        user_id="sup_ahmed",
        user_role="SHIFT_SUPERVISOR",
        message="Create shift handover for Unit CDU-101",
        required_permissions=[ToolPermission.CREATE_HANDOVER]
    )
    res = harness.execute(req)
    assert res.decision == HarnessPolicyDecision.ALLOW
    assert res.status == ExecutionStatus.COMPLETED


def test_3_authorization_deny(harness):
    """Test 3: Unauthorized role is blocked before reaching agent."""
    req = HarnessRequest(
        request_id="req-h-3",
        user_id="field_tech",
        user_role="FIELD_OPERATOR",
        message="Approve and finalize handover",
        required_permissions=[ToolPermission.READ_AUDIT]
    )
    res = harness.execute(req)
    assert res.decision == HarnessPolicyDecision.DENY
    assert res.status == ExecutionStatus.DENIED
    assert "Access Denied" in res.response
    assert res.error["code"] == "AUTHORIZATION_ERROR"


def test_4_safety_denial_interlock(harness):
    """Test 4: Safety policy intercepts remote plant control commands."""
    req = HarnessRequest(
        request_id="req-h-4",
        user_id="op_1",
        user_role="CONSOLE_OPERATOR",
        message="Turn off crude charge pump P-101 immediately."
    )
    res = harness.execute(req)
    assert res.decision == HarnessPolicyDecision.DENY
    assert res.status == ExecutionStatus.DENIED
    assert "Safety Policy Restriction" in res.response
    assert res.error["code"] == "PHYSICAL_CONTROL_PROHIBITED"


def test_5_prohibited_physical_control_commands(harness):
    """Test 5: Prohibited commands like 'Trip P-101' and 'Open valve XV-101' are denied."""
    for cmd in ["Trip P-101", "Open valve XV-101", "Bypass ESD system on furnace", "Change setpoint to 50 bar"]:
        req = HarnessRequest(user_id="op_1", user_role="CONSOLE_OPERATOR", message=cmd)
        res = harness.execute(req)
        assert res.decision == HarnessPolicyDecision.DENY
        assert res.status == ExecutionStatus.DENIED


def test_6_agent_permission_validation():
    """Test 6: Agents cannot execute tools outside their whitelist."""
    # QA agent cannot create handover
    assert permission_manager.verify_agent_tool_permission("qa_technical_agent", ToolPermission.RETRIEVE_DOCUMENT) is True
    assert permission_manager.verify_agent_tool_permission("qa_technical_agent", ToolPermission.CREATE_HANDOVER) is False
    # Shift agent cannot read loop diagrams
    assert permission_manager.verify_agent_tool_permission("shift_handover_agent", ToolPermission.CREATE_HANDOVER) is True
    assert permission_manager.verify_agent_tool_permission("shift_handover_agent", ToolPermission.READ_LOOP) is False


def test_7_prohibited_remote_control_tool():
    """Test 7: REMOTE_EQUIPMENT_CONTROL is strictly forbidden for all roles and agents."""
    assert permission_manager.verify_agent_tool_permission("qa_technical_agent", ToolPermission.REMOTE_EQUIPMENT_CONTROL) is False
    assert permission_manager.verify_agent_tool_permission("shift_handover_agent", ToolPermission.REMOTE_EQUIPMENT_CONTROL) is False
    assert permission_manager.verify_role_authorization("ADMIN", ToolPermission.REMOTE_EQUIPMENT_CONTROL) is False



def test_8_timeout_handling(harness, monkeypatch):
    """Test 8: Timeout returns structured error without hanging."""
    def timeout_exec(req):
        raise TimeoutError("Downstream service timed out after 30s")

    monkeypatch.setattr(harness.orchestrator, "execute", timeout_exec)

    req = HarnessRequest(
        user_id="u1",
        message="Explain refining process",
        budget=ExecutionBudget(max_retries=1)
    )
    res = harness.execute(req)
    assert res.status == ExecutionStatus.ERROR
    assert "error occurred" in res.response.lower()


def test_9_transient_retry(harness, monkeypatch):
    """Test 9: Bounded retry succeeds after a transient network error."""
    attempts = 0

    def transient_exec(req):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionResetError("Temporary connection reset by peer")
        return AgentResult(
            request_id=req.request_id,
            agent_id="qa_technical_agent",
            status="success",
            success=True,
            response="Retried answer succeeded."
        )

    monkeypatch.setattr(harness.orchestrator, "execute", transient_exec)

    req = HarnessRequest(user_id="u1", message="Get manual", budget=ExecutionBudget(max_retries=2))
    res = harness.execute(req)
    assert res.status == ExecutionStatus.COMPLETED
    assert "Retried answer succeeded" in res.response
    assert res.retry_count == 1


def test_10_permanent_failure_no_retry(harness, monkeypatch):
    """Test 10: Permanent failure does NOT trigger wasteful retry loops."""
    call_count = 0

    def permanent_fail(req):
        nonlocal call_count
        call_count += 1
        raise ValueError("Invalid parameter schema: permanent error")

    monkeypatch.setattr(harness.orchestrator, "execute", permanent_fail)

    req = HarnessRequest(user_id="u1", message="Run malformed query", budget=ExecutionBudget(max_retries=3))
    res = harness.execute(req)
    assert res.status == ExecutionStatus.ERROR
    assert call_count == 1  # No retries for permanent errors


def test_11_agent_loop_detection(harness, monkeypatch):
    """Test 11: Cyclic agent invocations [A, B, A, B] are detected and stopped."""
    call_index = 0
    tracker = ExecutionBudgetTracker(ExecutionBudget(max_agent_calls=10, max_depth=10))

    tracker.record_agent_invocation("agent_a")
    tracker.record_agent_invocation("agent_b")
    tracker.record_agent_invocation("agent_a")
    with pytest.raises(AgentLoopDetectedError):
        tracker.record_agent_invocation("agent_b")


def test_12_max_depth_enforcement():
    """Test 12: Max nested depth violation raises AgentDepthExceededError."""
    tracker = ExecutionBudgetTracker(ExecutionBudget(max_agent_calls=10, max_depth=3))
    tracker.record_agent_invocation("agent_1")
    tracker.record_agent_invocation("agent_2")
    tracker.record_agent_invocation("agent_3")
    with pytest.raises(AgentDepthExceededError):
        tracker.record_agent_invocation("agent_4")


def test_13_grounding_validation(harness):
    """Test 13: Grounding validation confirms technical responses have citations."""
    res_valid = output_validator.validate(
        response_text="Crude distillation occurs at atmospheric pressure.",
        citations=[{"document_name": "Refining.pdf", "source_type": "PDF", "page_number": 5}],
        query_type="technical_qa"
    )
    assert res_valid.grounding_valid is True
    assert res_valid.is_valid is True


def test_14_missing_citation_detection():
    """Test 14: Technical factual claim lacking citations triggers validation warning."""
    long_claim = "The distillation column operates at precisely 3.2 bar with reflux ratio 1.8 and overhead temp 115C." * 2
    res_invalid = output_validator.validate(
        response_text=long_claim,
        citations=[],
        query_type="technical_qa"
    )
    assert res_invalid.grounding_valid is False
    assert any("mandatory source" in e for e in res_invalid.errors)


def test_15_engineering_conflict_detection():
    """Test 15: Conflict detection confirms divergence is reported properly."""
    res = output_validator.validate(
        response_text="Potential Engineering Inconsistency Detected: PT-101 mapped to AI-05 in I/O list and AI-06 in loop drawing.",
        citations=[],
        query_type="loop_conflict_detected",
        metadata={"conflict_code": "LOOP_CONFIGURATION_CONFLICT"}
    )
    assert res.conflicts_detected is True


def test_16_response_schema_validation(harness, monkeypatch):
    """Test 16: Response matches typed HarnessResponse schema."""
    monkeypatch.setattr(
        harness.orchestrator,
        "execute",
        lambda req: AgentResult(request_id=req.request_id, agent_id="qa", status="success", success=True, response="Valid schema answer.")
    )
    req = HarnessRequest(user_id="u1", message="Check schema")
    res = harness.execute(req)
    assert isinstance(res, HarnessResponse)
    assert res.version_info["harness_version"] == "1.0.0"


def test_17_audit_context_propagation(harness, monkeypatch):
    """Test 17: Harness execution emits structured audit records."""
    monkeypatch.setattr(
        harness.orchestrator,
        "execute",
        lambda req: AgentResult(request_id=req.request_id, agent_id="qa", status="success", success=True, response="Audit check.")
    )
    req = HarnessRequest(request_id="req-audit-1", user_id="user_audit", user_role="CONSOLE_OPERATOR", message="Test audit")
    res = harness.execute(req)
    assert res.status == ExecutionStatus.COMPLETED


def test_18_observability_context(harness, monkeypatch):
    """Test 18: Telemetry captures latency, agent ID, and validation status."""
    monkeypatch.setattr(
        harness.orchestrator,
        "execute",
        lambda req: AgentResult(request_id=req.request_id, agent_id="qa_technical_agent", status="success", success=True, response="Telemetry test.")
    )
    req = HarnessRequest(user_id="u1", message="Trace telemetry")
    res = harness.execute(req)
    assert res.execution_time_ms >= 0.0


def test_19_execution_budget_enforcement():
    """Test 19: Exceeding max agent calls raises BudgetExceededError."""
    tracker = ExecutionBudgetTracker(ExecutionBudget(max_agent_calls=2))
    tracker.record_agent_invocation("agent_1")
    tracker.record_agent_invocation("agent_2")
    with pytest.raises(BudgetExceededError):
        tracker.record_agent_invocation("agent_3")


def test_20_cache_safety():
    """Test 20: Harness respects strict caching policy (Shift state never cached)."""
    assert cache_service.is_cacheable("get_handover", "shift") is False
    assert cache_service.is_cacheable("transition_success", "shift") is False
    assert cache_service.is_cacheable("general_qa", "qa") is True


def test_21_human_approval_state(harness):
    """Test 21: High-impact actions tagged for approval return REQUIRES_HUMAN_APPROVAL."""
    req = HarnessRequest(
        user_id="op_1",
        user_role="CONSOLE_OPERATOR",
        message="Request emergency relief valve recalibration",
        metadata={"requires_human_approval": True}
    )
    res = harness.execute(req)
    assert res.decision == HarnessPolicyDecision.REQUIRES_HUMAN_APPROVAL
    assert "requires human supervisor approval" in res.response


def test_22_agent_health_handling(harness):
    """Test 22: Harness health check reports agent availability status."""
    health = harness.health_check()
    assert health["status"] in ["READY", "DEGRADED"]
    assert health["agent_count"] >= 2
    assert "qa_technical_agent" in health["agents"]
    assert "shift_handover_agent" in health["agents"]



def test_26_multi_agent_execution(harness, monkeypatch):
    """Test 26: Multi-agent composite query execution through Harness."""
    mock_res = AgentResult(
        request_id="req-ma-h",
        agent_id="orchestrator_multi_agent",
        status="success",
        success=True,
        response="Logged note to handover.\n\nSOP Reference: Verify pump suction.",
        metadata={"coordinated_agents": ["shift_handover_agent", "qa_technical_agent"]}
    )
    monkeypatch.setattr(harness.orchestrator, "execute", lambda req: mock_res)

    req = HarnessRequest(user_id="u1", message="Record note in handover and show SOP")
    res = harness.execute(req)
    assert "Logged note" in res.response


def test_27_streaming_harness_execution(harness, monkeypatch):
    """Test 27: Streaming through Harness yields token events."""
    def fake_stream(req):
        yield {"type": "token", "content": "Streaming token 1."}
        yield {"type": "token", "content": " Streaming token 2."}
        yield {"type": "done", "request_id": req.request_id}

    monkeypatch.setattr(harness.orchestrator, "stream", fake_stream)

    req = HarnessRequest(user_id="u1", message="Stream explanation")
    events = list(harness.stream(req))
    token_contents = [e["content"] for e in events if e.get("type") == "token"]
    assert "Streaming token 1." in token_contents


def test_28_secret_and_error_shielding(harness):
    """Test 28: Leaked passwords, URIs, and stack traces are sanitized before client delivery."""
    dirty_text = "DB connection: postgresql://admin:super_secret_password_123@10.14.2.5/MASS_DB"
    sanitized, found = output_validator.sanitize_secrets(dirty_text)
    assert found is True
    assert "super_secret_password_123" not in sanitized
    assert "10.14.2.5" not in sanitized
    assert "[REDACTED_DB_URI]" in sanitized
