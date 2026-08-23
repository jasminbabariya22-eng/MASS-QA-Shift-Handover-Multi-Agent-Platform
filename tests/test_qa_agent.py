import pytest
from app.agents import qa_agent, AgentRequest, AgentResult
from qdrant_client import QdrantClient
from app.config import settings


def test_qa_agent_structure_and_contracts():
    """Verify QA Agent interface and baseline contracts."""
    assert qa_agent.agent_id == "qa_technical_agent"
    assert "technical" in qa_agent.description.lower() or "petroleum" in qa_agent.description.lower()
    assert "answer_question" in qa_agent.capabilities

    # Verify AgentRequest contract
    req = AgentRequest(message="What is crude stabilization?", top_k=3, use_cache=True)
    assert req.message == "What is crude stabilization?"
    assert req.top_k == 3
    assert req.request_id  # auto-generated


def test_qdrant_integrity_baseline():
    """
    CRITICAL BASELINE RULE:
    Verify Qdrant collection 'mass_qa_multimodal' is 100% UNTOUCHED:
    - Points: 2079
    - Dimension: 3072
    - Status: green
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
