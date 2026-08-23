import time
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.security import create_access_token, decode_access_token, UserRole
from app.services.cache import cache_service, normalize_query_text
from app.services.session import conversation_manager


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================
# 1. HEALTH & READINESS PROBE TESTS
# ============================================================

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_ready_endpoint(client):
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "dependencies" in data
    assert "qdrant" in data["dependencies"]
    assert "cache" in data["dependencies"]


def test_home_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert len(data["features"]) > 0


# ============================================================
# 2. AUTHENTICATION & AUTHORIZATION TESTS
# ============================================================

def test_create_and_decode_jwt():
    token = create_access_token(
        user_id="test-user-123",
        username="john_doe",
        role="SUPERVISOR",
        session_id="session-xyz"
    )
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload.user_id == "test-user-123"
    assert payload.username == "john_doe"
    assert payload.role == UserRole.SUPERVISOR
    assert payload.session_id == "session-xyz"


def test_auth_token_endpoint(client):
    req_body = {
        "user_id": "test-analyst",
        "username": "analyst_one",
        "role": "USER"
    }
    response = client.post("/auth/token", json=req_body)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["user_id"] == "test-analyst"


def test_invalid_token_decoding():
    with pytest.raises(Exception):
        decode_access_token("invalid.jwt.token.string")


# ============================================================
# 3. CACHING SERVICE & NORMALIZATION TESTS
# ============================================================

def test_query_normalization():
    q1 = "What is Shift Hand Over?"
    q2 = "  what is shift hand over?   "
    q3 = "what is shift hand over."
    assert normalize_query_text(q1) == "what is shift hand over"
    assert normalize_query_text(q2) == "what is shift hand over"
    assert normalize_query_text(q3) == "what is shift hand over"


def test_cache_service_crud():
    test_key = "test:sample:key"
    test_val = {"data": "refinery_metric_123", "value": 450}

    # Set
    cache_service.set(test_key, test_val, ttl_seconds=60)
    assert cache_service.exists(test_key) is True

    # Get
    retrieved = cache_service.get(test_key)
    assert retrieved == test_val

    # Delete
    cache_service.delete(test_key)
    assert cache_service.get(test_key) is None


def test_cache_ttl_expiration():
    short_key = "test:expiring:key"
    cache_service.set(short_key, "temp_data", ttl_seconds=1)
    assert cache_service.get(short_key) == "temp_data"
    time.sleep(1.2)
    assert cache_service.get(short_key) is None


# ============================================================
# 4. SESSION & CONVERSATION MANAGEMENT TESTS
# ============================================================

def test_session_creation_and_history():
    sid = "test-session-" + str(time.time())
    session = conversation_manager.get_or_create_session(sid, user_id="tester")
    assert session.session_id == sid
    assert len(session.messages) == 0

    # Add messages
    conversation_manager.add_message(sid, role="user", content="Hello, what is FCC?")
    conversation_manager.add_message(
        sid,
        role="assistant",
        content="FCC is Fluid Catalytic Cracking.",
        citations=[{"document_name": "refinery.pdf", "page": 10}]
    )

    history = conversation_manager.get_bounded_history(sid)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

    # Wipe
    conversation_manager.clear_session(sid)
    wiped_session = conversation_manager.get_or_create_session(sid)
    assert len(wiped_session.messages) == 0


def test_session_endpoints(client):
    sid = "api-session-" + str(time.time())
    conversation_manager.add_message(sid, role="user", content="Test query")

    # Get Session
    get_res = client.get(f"/sessions/{sid}")
    assert get_res.status_code == 200
    assert len(get_res.json()["messages"]) >= 1

    # Delete Session
    del_res = client.delete(f"/sessions/{sid}")
    assert del_res.status_code == 200
    assert del_res.json()["session_id"] == sid


# ============================================================
# 5. API QUERY & STREAMING TESTS
# ============================================================

def test_empty_query_validation(client):
    response = client.post("/query", json={"query": ""})
    assert response.status_code == 400 or response.status_code == 422
    data = response.json()
    assert "error" in data


def test_guardrails_refusal_on_query(client):
    response = client.post("/query", json={
        "query": "Can you give me a recipe for authentic Italian margherita pizza?",
        "stream": False
    })
    assert response.status_code == 200
    data = response.json()
    assert data["confidence"] == "refused"
    assert data["metadata"]["guardrails_blocked"] is True
    assert "knowledge base" in data["answer"].lower() or "help" in data["answer"].lower()


def test_sse_streaming_query(client):
    payload = {
        "query": "Can you give me a recipe for pizza?",
        "stream": True
    }
    response = client.post("/query", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

    # Read SSE lines
    lines = response.text.strip().split("\n")
    events = []
    for line in lines:
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except Exception:
                pass

    assert len(events) >= 1
    # Check that events have token, citations or done types
    event_types = [e.get("type") for e in events]
    assert "token" in event_types or "done" in event_types


def test_structured_response_contract(client):
    # Test backward compatibility with 'q' alias
    response = client.post("/query", json={
        "q": "What is the weather today?",
        "thread_id": "test-thread-compat"
    })
    assert response.status_code == 200
    data = response.json()
    assert "request_id" in data
    assert "session_id" in data
    assert "answer" in data
    assert "citations" in data
    assert "metadata" in data
    assert "total_latency_ms" in data["metadata"]
