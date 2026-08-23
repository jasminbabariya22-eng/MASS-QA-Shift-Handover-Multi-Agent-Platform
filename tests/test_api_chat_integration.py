import json
import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app
from app.config import settings
from app.security import create_access_token, UserRole
from app.agents.orchestrator import orchestrator
from app.agents.contracts import (
    AgentRequest,
    RequestContext,
    AgentResult,
    AgentIntent,
    AgentErrorCode,
)
from app.repositories.shift_handover_repository import (
    ConcurrencyConflictError,
    TerminalStateError,
    ShiftHandoverNotFoundError,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    token = create_access_token(
        user_id="op_console_99",
        username="john_operator",
        role="CONSOLE_OPERATOR"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def supervisor_headers():
    token = create_access_token(
        user_id="sup_salem_01",
        username="salem_supervisor",
        role="SHIFT_SUPERVISOR"
    )
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 25 FOCUSED STEP 8 API & CHAT INTEGRATION TESTS
# ============================================================

def test_1_query_request_validation(client, auth_headers):
    """Test 1: Empty query text fails with 400 Bad Request."""
    res = client.post("/query", json={"query": ""}, headers=auth_headers)
    assert res.status_code == 400
    assert "cannot be empty" in res.json()["error"]["message"]


def test_2_successful_qa_query(client, auth_headers, monkeypatch):
    """Test 2: Successful QA query returns grounded answer with citations."""
    mock_res = AgentResult(
        request_id="req-qa-1",
        agent_id="qa_technical_agent",
        status="success",
        success=True,
        response="To restart pump P-101, verify suction valve is open and seal oil pressure is above 2.5 bar.",
        citations=[{
            "source_type": "PDF",
            "document_name": "SOP_P101_Restart.pdf",
            "page_number": 12,
            "snippet": "Verify seal oil pressure is above 2.5 bar"
        }],
        query_type="technical_qa",
        confidence="high"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    payload = {"query": "What is the restart procedure for pump P-101?"}
    res = client.post("/query", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["answer"] == mock_res.response
    assert len(data["citations"]) == 1
    assert data["citations"][0]["document_name"] == "SOP_P101_Restart.pdf"
    assert data["status"] == "success"


def test_3_successful_shift_query(client, auth_headers, monkeypatch):
    """Test 3: Successful Shift query returns live database state."""
    mock_res = AgentResult(
        request_id="req-shift-1",
        agent_id="shift_handover_agent",
        status="success",
        success=True,
        response="📋 Shift Handover Status: Unit CDU-101 is in state DRAFT (v1).",
        citations=[{
            "source_type": "SHIFT_DATABASE",
            "document_name": "PostgreSQL: shift_handovers",
            "record_id": "SHO-20260822-CDU101-0001",
            "unit_id": "CDU-101",
            "state": "DRAFT"
        }],
        query_type="get_handover",
        confidence="high"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    payload = {"query": "Show current handover for Unit CDU-101"}
    res = client.post("/query", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "CDU-101" in data["answer"]
    assert data["citations"][0]["source_type"] == "SHIFT_DATABASE"


def test_4_multi_agent_query(client, auth_headers, monkeypatch):
    """Test 4: Multi-agent composite query combines shift data and SOP retrieval."""
    mock_res = AgentResult(
        request_id="req-multi-1",
        agent_id="orchestrator_multi_agent",
        status="success",
        success=True,
        response="📝 Note logged: abnormal vibration on C-101.\n\nStandard Operating Procedure (SOP) Reference:\nCheck lube oil pressure and vibration threshold.",
        citations=[{"source_type": "PDF", "document_name": "SOP_C101.pdf", "page_number": 4}],
        query_type="multi_agent_composite",
        confidence="high",
        metadata={"coordinated_agents": ["shift_handover_agent", "qa_technical_agent"]}
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    payload = {"query": "Add abnormal vibration on C-101 to shift handover and tell me what the SOP says"}
    res = client.post("/query", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "Standard Operating Procedure" in data["answer"]
    assert data["query_type"] == "multi_agent_composite"


def test_5_authentication_context_propagation(client, auth_headers, monkeypatch):
    """Test 5: Authenticated user_id from JWT is propagated to AgentRequest."""
    captured_req = {}

    def spy_execute(req):
        captured_req["user_id"] = req.user_id
        return AgentResult(
            request_id=req.request_id,
            agent_id="qa_technical_agent",
            status="success",
            success=True,
            response="OK"
        )

    monkeypatch.setattr(orchestrator, "execute", spy_execute)

    res = client.post("/query", json={"query": "Check status for Unit U-101"}, headers=auth_headers)
    assert res.status_code == 200
    assert captured_req["user_id"] == "op_console_99"


def test_6_role_propagation(client, supervisor_headers, monkeypatch):
    """Test 6: Authenticated user role from JWT is propagated to AgentRequest."""
    captured_req = {}

    def spy_execute(req):
        captured_req["user_role"] = req.user_role
        return AgentResult(
            request_id=req.request_id,
            agent_id="shift_handover_agent",
            status="success",
            success=True,
            response="Approved"
        )

    monkeypatch.setattr(orchestrator, "execute", spy_execute)

    res = client.post("/query", json={"query": "Approve handover SHO-101"}, headers=supervisor_headers)
    assert res.status_code == 200
    assert captured_req["user_role"] == "SHIFT_SUPERVISOR"


def test_7_session_propagation(client, auth_headers, monkeypatch):
    """Test 7: Custom session_id is preserved and returned in response."""
    monkeypatch.setattr(
        orchestrator,
        "execute",
        lambda req: AgentResult(request_id=req.request_id, agent_id="qa", status="success", success=True, response="OK")
    )

    custom_sess = "session-custom-abc-123"
    res = client.post("/query", json={"query": "Check status", "session_id": custom_sess}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["session_id"] == custom_sess


def test_8_request_id_propagation(client, auth_headers, monkeypatch):
    """Test 8: Request ID is generated and returned consistently."""
    monkeypatch.setattr(
        orchestrator,
        "execute",
        lambda req: AgentResult(request_id=req.request_id, agent_id="qa", status="success", success=True, response="OK")
    )

    res = client.post("/query", json={"query": "Check status"}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["request_id"] is not None
    assert len(res.json()["request_id"]) > 10


def test_9_clarification_response(client, auth_headers, monkeypatch):
    """Test 9: When agent requires clarification, response exposes requires_clarification=True."""
    mock_res = AgentResult(
        request_id="req-clarify",
        agent_id="shift_handover_agent",
        status="clarification_required",
        success=True,
        response="Which plant unit would you like to create the shift handover for?",
        query_type="clarification_required",
        metadata={"requires_clarification": True}
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Create a new handover"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["requires_clarification"] is True
    assert "Which plant unit" in data["answer"]


def test_10_safety_refusal(client, auth_headers, monkeypatch):
    """Test 10: Plant control command returns safety refusal response."""
    mock_res = AgentResult(
        request_id="req-safety",
        agent_id="orchestrator_safety_guard",
        status="refused",
        success=True,
        response="⚠️ Safety Interlock: Physical plant operation cannot be executed by the AI assistant.",
        query_type="safety_interlock"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Shut down pump P-101"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "Safety Interlock" in data["answer"]
    assert data["status"] == "refused"


def test_11_shift_workflow_success(client, supervisor_headers, monkeypatch):
    """Test 11: Valid workflow transition returns success."""
    mock_res = AgentResult(
        request_id="req-wf-1",
        agent_id="shift_handover_agent",
        status="success",
        success=True,
        response="✅ Handover SHO-20260822-CDU101-0001 transitioned to PENDING_ACKNOWLEDGEMENT (v3).",
        query_type="transition_success",
        metadata={"handover_id": "hid-1", "state": "PENDING_ACKNOWLEDGEMENT"}
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Approve handover SHO-20260822-CDU101-0001"}, headers=supervisor_headers)
    assert res.status_code == 200
    data = res.json()
    assert "PENDING_ACKNOWLEDGEMENT" in data["answer"]
    assert data["status"] == "success"


def test_12_invalid_workflow_response(client, auth_headers, monkeypatch):
    """Test 12: Invalid state transition returns clear rejection without crashing."""
    mock_res = AgentResult(
        request_id="req-wf-fail",
        agent_id="shift_handover_agent",
        status="error",
        success=False,
        response="❌ Transition Blocked: Cannot execute APPROVE on handover in DRAFT state.",
        query_type="transition_failed"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Approve draft handover"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "Transition Blocked" in data["answer"]
    assert data["status"] == "error"


def test_13_unauthorized_response(client, auth_headers, monkeypatch):
    """Test 13: Role unauthorized transition returns blocked notice."""
    mock_res = AgentResult(
        request_id="req-unauth",
        agent_id="shift_handover_agent",
        status="error",
        success=False,
        response="❌ Transition Blocked: Cannot execute APPROVE. Role CONSOLE_OPERATOR is not authorized.",
        query_type="transition_failed",
        metadata={"validation_errors": ["ROLE_UNAUTHORIZED"]}
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Approve handover SHO-001"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "not authorized" in data["answer"]


def test_14_concurrency_conflict_response(client, auth_headers, monkeypatch):
    """Test 14: Concurrency conflict returns clear notification."""
    mock_res = AgentResult(
        request_id="req-conflict",
        agent_id="shift_handover_agent",
        status="conflict",
        success=False,
        response="⚠️ Concurrency Conflict: This handover was modified by another user. Please refresh and try again.",
        query_type="concurrency_conflict"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Submit handover"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "Concurrency Conflict" in data["answer"]
    assert data["status"] == "conflict"


def test_15_database_failure_response(client, auth_headers, monkeypatch):
    """Test 15: Database error is shielded and does not leak connection credentials."""
    mock_res = AgentResult(
        request_id="req-dberr",
        agent_id="shift_handover_agent",
        status="error",
        success=False,
        response="An error occurred while accessing the shift handover system. Please verify the unit or handover details and try again.",
        query_type="error",
        error={"code": "AGENT_EXECUTION_ERROR", "message": "Database operational error."}
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "List all handovers"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "postgres://" not in data["answer"]
    assert "An error occurred" in data["answer"]


def test_16_agent_timeout(client, auth_headers, monkeypatch):
    """Test 16: Agent timeout returns standardized error."""
    mock_res = AgentResult(
        request_id="req-timeout",
        agent_id="orchestrator",
        status="timeout",
        success=False,
        response="The operation timed out before completing. Please try again.",
        query_type="timeout",
        error={"code": AgentErrorCode.AGENT_TIMEOUT.value, "message": "Execution exceeded timeout"}
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Perform complex analysis"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "timed out" in data["answer"]


def test_17_streaming_response(client, auth_headers, monkeypatch):
    """Test 17: Streaming request via stream=True yields structured SSE chunks."""
    def fake_stream(agent_req):
        yield {"type": "progress", "step": "interpreting_request", "message": "Processing..."}
        yield {"type": "token", "content": "SOP-101 recommends checking "}
        yield {"type": "token", "content": "bearing temperatures."}
        yield {"type": "citations", "citations": [{"source_type": "PDF", "document_name": "SOP_101.pdf"}]}
        yield {"type": "done", "request_id": agent_req.request_id, "metadata": {}}

    monkeypatch.setattr(orchestrator, "stream", fake_stream)

    res = client.post("/query", json={"query": "What does SOP-101 say?", "stream": True}, headers=auth_headers)
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    body = res.text
    assert "bearing temperatures" in body
    assert "SOP_101.pdf" in body


def test_18_streaming_error(client, auth_headers, monkeypatch):
    """Test 18: Streaming safety refusal emits refusal token in event stream."""
    def fake_stream(agent_req):
        yield {"type": "token", "content": "⚠️ Safety Interlock: Physical plant control refused."}
        yield {"type": "done", "request_id": agent_req.request_id}

    monkeypatch.setattr(orchestrator, "stream", fake_stream)

    res = client.post("/query/stream", json={"query": "Trip turbine KT-101"}, headers=auth_headers)
    assert res.status_code == 200
    assert "Safety Interlock" in res.text


def test_19_citation_serialization(client, auth_headers, monkeypatch):
    """Test 19: Citations are properly formatted with source_number and document_name."""
    mock_res = AgentResult(
        request_id="req-cite",
        agent_id="qa_technical_agent",
        status="success",
        success=True,
        response="Check vibration sensor.",
        citations=[
            {"source_number": 1, "document_name": "Turbine_Manual.pdf", "page_number": 45, "score": 0.92}
        ]
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Turbine check"}, headers=auth_headers)
    assert res.status_code == 200
    c = res.json()["citations"][0]
    assert c["document_name"] == "Turbine_Manual.pdf"
    assert c["page_number"] == 45


def test_20_shift_database_response_serialization(client, auth_headers, monkeypatch):
    """Test 20: Database citations identify source_type as SHIFT_DATABASE."""
    mock_res = AgentResult(
        request_id="req-shift-cite",
        agent_id="shift_handover_agent",
        status="success",
        success=True,
        response="Handover details.",
        citations=[
            {"source_type": "SHIFT_DATABASE", "document_name": "PostgreSQL: shift_handovers", "record_id": "SHO-001"}
        ]
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Show handover"}, headers=auth_headers)
    assert res.status_code == 200
    c = res.json()["citations"][0]
    assert c["source_type"] == "SHIFT_DATABASE"


def test_21_health_endpoint(client):
    """Test 21: Liveness /health endpoint returns 200 with service info."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert data["service"] == "mass-qa-rag"


def test_22_readiness_behavior(client):
    """Test 22: Readiness /ready endpoint reports dependency readiness."""
    res = client.get("/ready")
    assert res.status_code == 200
    data = res.json()
    assert "dependencies" in data
    assert "postgresql" in data["dependencies"]


def test_23_session_isolation(client):
    """Test 23: Separate JWT tokens have isolated user identity contexts."""
    token_a = create_access_token(user_id="user_alpha", username="alpha", role="CONSOLE_OPERATOR")
    token_b = create_access_token(user_id="user_beta", username="beta", role="CONSOLE_OPERATOR")

    captured_users = []

    def spy_exec(req):
        captured_users.append(req.user_id)
        return AgentResult(request_id=req.request_id, agent_id="qa", status="success", success=True, response="OK")

    with patch.object(orchestrator, "execute", side_effect=spy_exec):
        client.post("/query", json={"query": "Q1"}, headers={"Authorization": f"Bearer {token_a}"})
        client.post("/query", json={"query": "Q2"}, headers={"Authorization": f"Bearer {token_b}"})

    assert captured_users == ["user_alpha", "user_beta"]


def test_24_no_sensitive_information_in_errors(auth_headers, monkeypatch):
    """Test 24: Unhandled exceptions return generic sanitized error messages."""
    def crash_exec(req):
        raise RuntimeError("Internal DB error at postgresql://admin:secret_password@10.0.0.1:5432/MASS")

    monkeypatch.setattr(orchestrator, "execute", crash_exec)

    error_client = TestClient(app, raise_server_exceptions=False)
    res = error_client.post("/query", json={"query": "Check system health for Unit U-101"}, headers=auth_headers)
    assert res.status_code == 500
    data = res.json()
    assert "secret_password" not in json.dumps(data)
    assert "10.0.0.1" not in json.dumps(data)
    assert "INTERNAL_SERVER_ERROR" in data["error"]["code"]


def test_25_backward_compatibility_query_endpoint(client, auth_headers, monkeypatch):
    """Test 25: Backward compatibility: requests with 'q' and 'thread_id' operate cleanly."""
    monkeypatch.setattr(
        orchestrator,
        "execute",
        lambda req: AgentResult(request_id=req.request_id, agent_id="qa", status="success", success=True, response=f"Answer to: {req.message}")
    )

    payload = {"q": "What is the procedure?", "thread_id": "thread-legacy-001"}
    res = client.post("/query", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "What is the procedure?" in data["answer"]
    assert data["session_id"] == "thread-legacy-001"
