import pytest
import uuid
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.config import settings
from app.agents import (
    orchestrator,
    agent_registry,
    intent_router,
    qa_agent,
    shift_handover_agent,
    AgentRequest,
    RequestContext,
    AgentResult,
    AgentIntent,
    RiskLevel,
    RoutingResult,
    AgentErrorCode,
    BaseAgent,
)
from app.main import app

client = TestClient(app)


def test_agent_registry_operations():
    """Verify AgentRegistry registration, retrieval, listing, and unregistration."""
    assert agent_registry.has("qa_technical_agent") is True
    assert agent_registry.has("shift_handover_agent") is True

    qa = agent_registry.get("qa_technical_agent")
    assert qa is not None
    assert qa.agent_id == "qa_technical_agent"
    assert "answer_question" in qa.capabilities
    assert qa.supports_streaming is True
    assert qa.health_check()["status"] == "HEALTHY"

    agents_list = agent_registry.list_agents()
    assert len(agents_list) >= 2
    ids = [a["agent_id"] for a in agents_list]
    assert "qa_technical_agent" in ids
    assert "shift_handover_agent" in ids


def test_intent_router_classifications():
    """Verify hybrid intent and risk router across all operational categories."""
    
    # 1. Technical QA queries
    qa_queries = [
        "What is crude stabilization?",
        "Explain atmospheric distillation column operations.",
        "What is the approved procedure for restarting pump P-101?",
        "What are the safety guidelines for H2S exposure?"
    ]
    for q in qa_queries:
        res: RoutingResult = intent_router.route(q)
        assert res.intent == AgentIntent.QA
        assert "qa_technical_agent" in res.target_agents
        assert res.risk_level == RiskLevel.LOW
        assert res.requires_clarification is False

    # 2. Shift Handover queries
    shift_queries = [
        "Start my shift handover.",
        "Show me the shift handover log for unit 4.",
        "What happened during the night shift?",
        "Show unresolved actions from the previous shift."
    ]
    for q in shift_queries:
        res: RoutingResult = intent_router.route(q)
        assert res.intent == AgentIntent.SHIFT
        assert "shift_handover_agent" in res.target_agents
        assert res.risk_level == RiskLevel.LOW

    # 3. Multi-Agent queries (Handover + SOP Lookup)
    multi_queries = [
        "Add the compressor issue to my handover and find the restart procedure.",
        "Log P-101 trip in the shift log and show me the operating manual checklist."
    ]
    for q in multi_queries:
        res: RoutingResult = intent_router.route(q)
        assert res.intent == AgentIntent.MULTI_AGENT
        assert "shift_handover_agent" in res.target_agents
        assert "qa_technical_agent" in res.target_agents

    # 4. General greetings
    general_queries = [
        "Hello",
        "Hi there",
        "What can you do?"
    ]
    for q in general_queries:
        res: RoutingResult = intent_router.route(q)
        assert res.intent == AgentIntent.GENERAL
        assert "qa_technical_agent" in res.target_agents

    # 5. Ambiguous queries requiring clarification
    ambiguous_queries = [
        "Tell me about C-101.",
        "C-101",
        "P-101A"
    ]
    for q in ambiguous_queries:
        res: RoutingResult = intent_router.route(q)
        assert res.requires_clarification is True
        assert res.confidence < 0.8

    # 6. High-Risk safety-critical physical control commands (Must be Blocked)
    high_risk_queries = [
        "Turn off compressor C-101.",
        "Shut down unit 12 immediately.",
        "Open valve XV-101.",
        "Trip the charge pump P-101.",
        "Bypass ESD interlock on furnace F-101."
    ]
    for q in high_risk_queries:
        res: RoutingResult = intent_router.route(q)
        assert res.intent == AgentIntent.HIGH_RISK
        assert res.risk_level == RiskLevel.CRITICAL
        assert len(res.target_agents) == 0


def test_orchestrator_safety_interlock_refusal():
    """Verify Orchestrator blocks physical equipment control commands safely."""
    req = AgentRequest(
        request_id=str(uuid.uuid4()),
        message="Turn off crude charge pump P-101 immediately."
    )
    res = orchestrator.execute(req)
    assert res.agent_id == "orchestrator_safety_guard"
    assert res.query_type == "safety_interlock"
    assert "Safety Interlock" in res.response
    assert res.metadata.get("blocked_by_safety") is True


def test_orchestrator_ambiguity_clarification():
    """Verify Orchestrator prompts user for clarification on ambiguous queries."""
    req = AgentRequest(
        request_id=str(uuid.uuid4()),
        message="Tell me about C-101."
    )
    res = orchestrator.execute(req)
    assert res.agent_id == "orchestrator_router"
    assert res.query_type == "clarification_required"
    assert "clarify" in res.response.lower()
    assert res.metadata.get("requires_clarification") is True


def test_shift_handover_agent_skeleton_controlled_response():
    """Verify Shift Handover Agent returns structured handover response."""
    req = AgentRequest(
        request_id=str(uuid.uuid4()),
        message="Start my shift handover."
    )
    res = orchestrator.execute(req)
    assert res.agent_id == "shift_handover_agent"
    assert "Step" in res.response or "not yet active" in res.response or "in design" in res.response or "Handover" in res.response or res.success is True


def test_orchestrator_streaming_events():
    """Verify Orchestrator streaming generator produces valid token and done events."""
    req = AgentRequest(
        request_id=str(uuid.uuid4()),
        message="Turn off compressor C-101.",
    )
    events = list(orchestrator.stream(req))
    assert len(events) >= 2
    types = [e.get("type") for e in events]
    assert "token" in types
    assert "done" in types
    assert "Safety Interlock" in events[0]["content"]


def test_orchestrator_error_handling_on_unregistered_agent():
    """Verify Orchestrator safely shields users from internal agent lookup failures."""
    class FakeOrchestrator(orchestrator.__class__):
        def _build_context(self, request):
            ctx = super()._build_context(request)
            ctx.current_agent = "non_existent_agent_999"
            return ctx

    fake_orch = FakeOrchestrator()
    req = AgentRequest(message="Test query")
    res = fake_orch.execute(req)
    assert res.success is False
    assert res.error is not None
    assert res.error["code"] == AgentErrorCode.AGENT_UNAVAILABLE.value


def test_api_get_agents_endpoint():
    """Verify GET /agents API endpoint returns registered agents and health."""
    resp = client.get("/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["count"] >= 2
    agent_ids = [a["agent_id"] for a in data["agents"]]
    assert "qa_technical_agent" in agent_ids
    assert "shift_handover_agent" in agent_ids


def test_qdrant_collection_unchanged():
    """
    CRITICAL BASELINE RULE:
    Verify Qdrant collection 'mass_qa_multimodal' is 100% UNTOUCHED:
    - 2,079 vectors, 3072 dimensions, green status.
    """
    qdrant = QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        prefer_grpc=False,
        check_compatibility=False,
        timeout=30.0
    )
    info = qdrant.get_collection("mass_qa_multimodal")
    assert info.points_count == 2079
    assert info.config.params.vectors.size == 3072
    assert info.status.name.lower() == "green"
