import json
import uuid
import time
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app
from app.config import settings
from app.security import create_access_token
from app.security.rate_limiter import rate_limiter
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
from app.services.cache import cache_service


@pytest.fixture
def client():
    rate_limiter.reset()
    return TestClient(app)


@pytest.fixture
def auth_headers():
    token = create_access_token(
        user_id="op_john_console",
        username="john_operator",
        role="CONSOLE_OPERATOR"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def supervisor_headers():
    token = create_access_token(
        user_id="sup_salem",
        username="salem_supervisor",
        role="SHIFT_SUPERVISOR"
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def incoming_headers():
    token = create_access_token(
        user_id="op_alex_incoming",
        username="alex_operator",
        role="INCOMING_OPERATOR"
    )
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 24 STEP 9 PRODUCTION API MESH & GATEWAY E2E SCENARIOS
# ============================================================

def test_1_login_authentication(client):
    """Scenario 1: Login/authentication generates valid JWT token and sets security context."""
    res = client.post("/auth/token", json={
        "user_id": "op_console_01",
        "username": "op_console_01",
        "role": "CONSOLE_OPERATOR"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["user_id"] == "op_console_01"
    assert data["user"]["role"] == "CONSOLE_OPERATOR"


def test_2_authenticated_qa_query(client, auth_headers, monkeypatch):
    """Scenario 2: Authenticated QA query routes via Gateway to QA agent."""
    mock_res = AgentResult(
        request_id="req-qa-step9-1",
        agent_id="qa_technical_agent",
        status="success",
        success=True,
        response="Pump P-101 requires minimum 2.5 bar lube oil pressure before starting.",
        citations=[{
            "source_type": "PDF",
            "document_name": "SOP_P101.pdf",
            "page_number": 8,
            "snippet": "Lube oil pressure >= 2.5 bar"
        }],
        query_type="technical_qa",
        confidence="high"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/api/v1/query", json={"query": "What is the startup requirement for P-101?"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "2.5 bar" in data["answer"]
    assert len(data["citations"]) == 1
    assert res.headers.get("X-Request-ID") is not None


def test_3_qa_streaming_query(client, auth_headers, monkeypatch):
    """Scenario 3: QA streaming query yields token events and heartbeat with security headers."""
    def fake_stream(agent_req):
        yield {"type": "token", "content": "Check pump "}
        yield {"type": "token", "content": "suction alignment."}
        yield {"type": "citations", "citations": [{"source_type": "PDF", "document_name": "SOP_Pump.pdf"}]}
        yield {"type": "done", "request_id": agent_req.request_id, "metadata": {}}

    monkeypatch.setattr(orchestrator, "stream", fake_stream)

    res = client.post("/api/v1/query/stream", json={"query": "How to align pump P-101?"}, headers=auth_headers)
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    body = res.text
    assert "suction alignment" in body
    assert res.headers.get("X-Request-ID") is not None


def test_4_qa_citation_preservation(client, auth_headers, monkeypatch):
    """Scenario 4: Technical document citations are preserved with source details."""
    mock_res = AgentResult(
        request_id="req-cite-step9",
        agent_id="qa_technical_agent",
        status="success",
        success=True,
        response="Inspect seal barrier fluid reservoir level.",
        citations=[{
            "source_type": "PDF",
            "document_name": "Mechanical_Seal_Standard.pdf",
            "page_number": 14,
            "snippet": "Inspect barrier fluid reservoir level"
        }]
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Check barrier fluid"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["citations"][0]["document_name"] == "Mechanical_Seal_Standard.pdf"
    assert data["citations"][0]["page_number"] == 14


def test_5_shift_handover_creation(client, auth_headers, monkeypatch):
    """Scenario 5: Shift handover draft creation via conversational Gateway."""
    mock_res = AgentResult(
        request_id="req-sho-create",
        agent_id="shift_handover_agent",
        status="success",
        success=True,
        response="✅ Created Shift Handover Draft: SHO-20260822-CDU101-0001 (DRAFT v1).",
        query_type="create_handover",
        citations=[{"source_type": "SHIFT_DATABASE", "document_name": "PostgreSQL: shift_handovers", "record_id": "SHO-001"}],
        metadata={"handover_id": "hid-1", "state": "DRAFT"}
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Create day shift handover for Unit CDU-101"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "SHO-20260822-CDU101-0001" in data["answer"]


def test_6_shift_handover_retrieval(client, auth_headers, monkeypatch):
    """Scenario 6: Shift handover retrieval returns live database record."""
    mock_res = AgentResult(
        request_id="req-sho-get",
        agent_id="shift_handover_agent",
        status="success",
        success=True,
        response="📋 Shift Handover: Unit CDU-101 is in state DRAFT (v1).",
        query_type="get_handover",
        citations=[{"source_type": "SHIFT_DATABASE", "document_name": "PostgreSQL: shift_handovers", "record_id": "SHO-001"}]
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Show handover for Unit CDU-101"}, headers=auth_headers)
    assert res.status_code == 200
    assert "CDU-101" in res.json()["answer"]


def test_7_shift_handover_submission(client, auth_headers, monkeypatch):
    """Scenario 7: Shift handover submission transitions state to SUBMITTED."""
    mock_res = AgentResult(
        request_id="req-sho-sub",
        agent_id="shift_handover_agent",
        status="success",
        success=True,
        response="✅ Handover SHO-20260822-CDU101-0001 transitioned to SUBMITTED (v2).",
        query_type="transition_success"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Submit handover for Unit CDU-101"}, headers=auth_headers)
    assert res.status_code == 200
    assert "SUBMITTED" in res.json()["answer"]


def test_8_supervisor_approval(client, supervisor_headers, monkeypatch):
    """Scenario 8: Supervisor approves handover to PENDING_ACKNOWLEDGEMENT."""
    mock_res = AgentResult(
        request_id="req-sho-app",
        agent_id="shift_handover_agent",
        status="success",
        success=True,
        response="✅ Handover SHO-20260822-CDU101-0001 transitioned to PENDING_ACKNOWLEDGEMENT (v3).",
        query_type="transition_success"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Approve handover for Unit CDU-101"}, headers=supervisor_headers)
    assert res.status_code == 200
    assert "PENDING_ACKNOWLEDGEMENT" in res.json()["answer"]


def test_9_incoming_operator_acknowledgement(client, incoming_headers, monkeypatch):
    """Scenario 9: Incoming operator acknowledges and completes handover."""
    mock_res = AgentResult(
        request_id="req-sho-ack",
        agent_id="shift_handover_agent",
        status="success",
        success=True,
        response="✅ Handover SHO-20260822-CDU101-0001 transitioned to COMPLETED (v4).",
        query_type="transition_success"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Acknowledge and accept handover for Unit CDU-101"}, headers=incoming_headers)
    assert res.status_code == 200
    assert "COMPLETED" in res.json()["answer"]


def test_10_completed_handover_retrieval(client, auth_headers, monkeypatch):
    """Scenario 10: Completed handover retrieval demonstrates final state persistence."""
    mock_res = AgentResult(
        request_id="req-sho-done",
        agent_id="shift_handover_agent",
        status="success",
        success=True,
        response="📋 Shift Handover Status: Unit CDU-101 is COMPLETED (v4).",
        query_type="get_handover"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Show handover status for Unit CDU-101"}, headers=auth_headers)
    assert res.status_code == 200
    assert "COMPLETED" in res.json()["answer"]


def test_11_shift_state_is_not_cached():
    """Scenario 11: Caching policy strictly enforces that Shift state is NEVER cached."""
    assert cache_service.is_cacheable(query_type="get_handover", intent="shift") is False
    assert cache_service.is_cacheable(query_type="transition_success", intent="shift") is False
    assert cache_service.is_cacheable(query_type="multi_agent_composite", intent="multi_agent") is False
    assert cache_service.is_cacheable(query_type="general_qa", intent="qa") is True


def test_12_concurrent_update_produces_409(client, auth_headers, monkeypatch):
    """Scenario 12: Optimistic concurrency conflict returns standardized 409 error."""
    def throw_concurrency(req):
        raise ConcurrencyConflictError("Version conflict on handover SHO-001.")

    monkeypatch.setattr(orchestrator, "execute", throw_concurrency)

    error_client = TestClient(app, raise_server_exceptions=False)
    res = error_client.post("/query", json={"query": "Update handover notes"}, headers=auth_headers)
    assert res.status_code == 409
    data = res.json()
    assert data["error"]["code"] == "CONCURRENCY_CONFLICT"
    assert "request_id" in data["error"]


def test_13_unauthorized_action_produces_error(client, auth_headers, monkeypatch):
    """Scenario 13: Role unauthorized action returns clear rejection."""
    mock_res = AgentResult(
        request_id="req-unauth",
        agent_id="shift_handover_agent",
        status="error",
        success=False,
        response="❌ Transition Blocked: Role CONSOLE_OPERATOR is not authorized to APPROVE.",
        query_type="transition_failed"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Approve handover"}, headers=auth_headers)
    assert res.status_code == 200
    assert "not authorized" in res.json()["answer"]


def test_14_unknown_handover_produces_404(auth_headers, monkeypatch):
    """Scenario 14: Unknown handover query raises 404 with standardized error."""
    def throw_notfound(req):
        raise ShiftHandoverNotFoundError("Handover not found: SHO-999")

    monkeypatch.setattr(orchestrator, "execute", throw_notfound)

    error_client = TestClient(app, raise_server_exceptions=False)
    res = error_client.post("/query", json={"query": "Show handover SHO-999"}, headers=auth_headers)
    assert res.status_code == 404
    data = res.json()
    assert data["error"]["code"] == "SHIFT_HANDOVER_NOT_FOUND"


def test_15_terminal_handover_mutation_rejected(auth_headers, monkeypatch):
    """Scenario 15: Terminal state mutation raises 400 Bad Request."""
    def throw_terminal(req):
        raise TerminalStateError("Handover is COMPLETED and locked.")

    monkeypatch.setattr(orchestrator, "execute", throw_terminal)

    error_client = TestClient(app, raise_server_exceptions=False)
    res = error_client.post("/query", json={"query": "Edit completed handover"}, headers=auth_headers)
    assert res.status_code == 400
    data = res.json()
    assert data["error"]["code"] == "TERMINAL_STATE_LOCKED"


def test_16_rate_limiting_produces_429(client):
    """Scenario 16: Rate limit exhaustion produces HTTP 429 with Retry-After header."""
    rate_limiter.reset()
    key = "auth:ip:testclient"
    # Fill up limit
    for _ in range(settings.RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE):
        rate_limiter.is_allowed(key, settings.RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE)

    res = client.post("/auth/token", json={"user_id": "test", "username": "test", "role": "ADMIN"})
    assert res.status_code == 429
    assert "Retry-After" in res.headers
    data = res.json()
    assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    rate_limiter.reset()


def test_17_correlation_id_propagation(client, auth_headers, monkeypatch):
    """Scenario 17: Incoming X-Request-ID is preserved and returned in headers."""
    monkeypatch.setattr(
        orchestrator,
        "execute",
        lambda req: AgentResult(request_id=req.request_id, agent_id="qa", status="success", success=True, response="OK")
    )

    custom_id = "test-correlation-uuid-999"
    res = client.post("/query", json={"query": "Status check"}, headers={**auth_headers, "X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id
    assert res.headers.get("X-Correlation-ID") == custom_id


def test_18_health_endpoint(client):
    """Scenario 18: Liveness probe /health returns 200 with service information."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert data["service"] == "mass-qa-rag"


def test_19_readiness_endpoint(client):
    """Scenario 19: Readiness probe /ready returns dependency health without expensive queries."""
    res = client.get("/ready")
    assert res.status_code == 200
    data = res.json()
    assert "dependencies" in data
    assert "postgresql" in data["dependencies"]
    assert "qdrant" in data["dependencies"]


def test_20_sanitized_500_error(auth_headers, monkeypatch):
    """Scenario 20: Unhandled 500 error sanitizes credentials and internal paths."""
    def crash_exec(req):
        raise RuntimeError("Internal DB error: postgresql://admin:secret_pass_123@10.0.0.5/MASS")

    monkeypatch.setattr(orchestrator, "execute", crash_exec)

    error_client = TestClient(app, raise_server_exceptions=False)
    res = error_client.post("/query", json={"query": "Perform maintenance check on Unit U-101"}, headers=auth_headers)
    assert res.status_code == 500
    data = res.json()
    assert "secret_pass_123" not in json.dumps(data)
    assert "10.0.0.5" not in json.dumps(data)
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"


def test_21_sse_disconnect_handling(client, auth_headers, monkeypatch):
    """Scenario 21: SSE streaming handles client events and yields heartbeat."""
    def fake_stream(req):
        yield {"type": "token", "content": "Live stream active."}
        yield {"type": "done", "request_id": req.request_id}

    monkeypatch.setattr(orchestrator, "stream", fake_stream)

    res = client.post("/api/v1/query/stream", json={"query": "Show unit live status"}, headers=auth_headers)
    assert res.status_code == 200
    assert "event: heartbeat" in res.text
    assert "Live stream active." in res.text


def test_22_api_timeout_handling(client, auth_headers, monkeypatch):
    """Scenario 22: Timeout returns standardized timeout error without hanging."""
    mock_res = AgentResult(
        request_id="req-timeout-step9",
        agent_id="orchestrator",
        status="timeout",
        success=False,
        response="The operation timed out. Please try again.",
        error={"code": AgentErrorCode.AGENT_TIMEOUT.value, "message": "Timeout exceeded"}
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Run heavy analysis"}, headers=auth_headers)
    assert res.status_code == 200
    assert "timed out" in res.json()["answer"]


def test_23_qa_shift_multi_agent_request(client, auth_headers, monkeypatch):
    """Scenario 23: Multi-agent request coordinates shift logging and SOP retrieval."""
    mock_res = AgentResult(
        request_id="req-multi-step9",
        agent_id="orchestrator_multi_agent",
        status="success",
        success=True,
        response="📝 Note logged to handover for Unit CDU-101.\n\nSOP Procedure:\nCheck bearing temperature before startup.",
        citations=[
            {"source_type": "SHIFT_DATABASE", "document_name": "PostgreSQL: shift_handovers", "record_id": "SHO-001"},
            {"source_type": "PDF", "document_name": "SOP_CDU101.pdf", "page_number": 3}
        ],
        query_type="multi_agent_composite",
        metadata={"coordinated_agents": ["shift_handover_agent", "qa_technical_agent"]}
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Add note on CDU-101 and check SOP"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "Note logged" in data["answer"]
    assert "SOP Procedure" in data["answer"]
    assert len(data["citations"]) == 2


def test_24_physical_equipment_command_blocked(client, auth_headers, monkeypatch):
    """Scenario 24: Direct physical plant commands are refused by safety interlock."""
    mock_res = AgentResult(
        request_id="req-safety-step9",
        agent_id="orchestrator_safety_guard",
        status="refused",
        success=True,
        response="⚠️ Safety Interlock: Physical plant operations cannot be executed by the AI assistant.",
        query_type="safety_interlock"
    )
    monkeypatch.setattr(orchestrator, "execute", lambda req: mock_res)

    res = client.post("/query", json={"query": "Shut down turbine KT-101"}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "Safety Interlock" in data["answer"]
    assert data["status"] == "refused"
