import pytest
import uuid
from typing import Dict, Any, Generator

from app.agents import (
    QAAgentAdapter,
    QAAgent,
    qa_agent,
    agent_registry,
    intent_router,
    orchestrator,
    AgentRequest,
    RequestContext,
    AgentResult,
    AgentErrorCode,
    TaskStatus,
    AgentIntent,
)
from app.services.generation import RAGResponse, SourceCitation


# --- Mock fixtures and helpers ---

def mock_success_rag_response(question: str = "What is crude stabilization?", **kwargs) -> RAGResponse:
    return RAGResponse(
        question=question,
        answer="Crude stabilization is the process of removing light hydrocarbons (H2S, methane, ethane, propane, butane) from crude oil.",
        sources=[
            SourceCitation(
                source_number=1,
                document_name="5.1_petroleum_refining.pdf",
                document_id="doc_refining_101",
                chunk_id="chunk_42",
                page_number=12,
                slide_number=None,
                section="Stabilization & Sweetening",
                content_type="text",
                score=0.95,
                snippet="Crude stabilization removes volatile components to lower RVP."
            ),
            SourceCitation(
                source_number=2,
                document_name="Operations_Manual.pptx",
                document_id="doc_ops_202",
                chunk_id="chunk_88",
                page_number=None,
                slide_number=5,
                section="Light Ends Recovery",
                content_type="slide",
                score=0.88,
                snippet="Stabilizer column overhead vapor is sent to gas processing."
            )
        ],
        query_type="normal",
        retrieval_count=8,
        grounded=True,
        confidence="high",
        thought_process=["Analysis completed", "Retrieved 8 chunks", "Synthesized grounded answer"],
        latency_breakdown={"retrieval": 0.05, "llm_generation": 0.45, "total": 0.52},
        status="success"
    )


def mock_insufficient_rag_response(question: str = "Unrelated question", **kwargs) -> RAGResponse:
    return RAGResponse(
        question=question,
        answer="I don't have enough information in the available knowledge base to answer this confidently.",
        sources=[],
        query_type="out_of_domain",
        retrieval_count=0,
        grounded=True,
        confidence="insufficient",
        thought_process=["Evidence insufficient"],
        latency_breakdown={"retrieval": 0.02, "total": 0.03},
        status="insufficient_evidence"
    )


def mock_llm_error_rag_response(question: str = "Error query", **kwargs) -> RAGResponse:
    return RAGResponse(
        question=question,
        answer="An error occurred while generating the answer from retrieved context. Please try again.",
        sources=[],
        query_type="normal",
        retrieval_count=5,
        grounded=False,
        confidence="low",
        thought_process=["Error in LLM call: Rate limit exceeded"],
        latency_breakdown={"retrieval": 0.04, "total": 0.05},
        status="llm_error"
    )


def mock_streaming_generator(question: str = "Test", **kwargs) -> Generator[Dict[str, Any], None, None]:
    yield {"type": "token", "content": "Crude "}
    yield {"type": "token", "content": "stabilization "}
    yield {"type": "token", "content": "process."}
    yield {
        "type": "citations",
        "citations": [
            {"source_number": 1, "document_name": "refining.pdf", "page_number": 3}
        ]
    }
    yield {
        "type": "done",
        "metadata": {"query_type": "normal", "confidence": "high"}
    }


# --- Test Cases ---

def test_1_qa_adapter_construction():
    """Verify QA adapter can be constructed with custom injected service functions."""
    adapter = QAAgentAdapter(
        qa_service_fn=mock_success_rag_response,
        stream_service_fn=mock_streaming_generator,
        timeout_seconds=15.0
    )
    assert adapter.agent_id == "qa_technical_agent"
    assert adapter.name == "MASS QA Technical Agent"
    assert "answer_question" in adapter.capabilities
    assert "return_citations" in adapter.capabilities
    assert "technical_qa" in adapter.capabilities
    assert adapter.supports_streaming is True
    assert adapter.timeout_seconds == 15.0


def test_2_qa_execution():
    """Verify synchronous execution wraps the injected QA service and returns an AgentResult."""
    adapter = QAAgentAdapter(qa_service_fn=mock_success_rag_response)
    req = AgentRequest(
        request_id="req-test-123",
        session_id="session-test-456",
        message="What is crude stabilization?",
        top_k=5
    )
    result = adapter.execute(req)
    
    assert isinstance(result, AgentResult)
    assert result.success is True
    assert result.status == TaskStatus.COMPLETED.value
    assert result.agent_id == "qa_technical_agent"
    assert result.request_id == "req-test-123"
    assert "Crude stabilization is the process" in result.response
    assert result.answer == result.response
    assert result.grounded is True
    assert result.confidence == "high"


def test_3_response_normalization():
    """Verify all RAG response fields correctly normalize into the AgentResult contract."""
    adapter = QAAgentAdapter(qa_service_fn=mock_success_rag_response)
    req = AgentRequest(message="What is crude stabilization?")
    result = adapter.execute(req)

    assert result.query_type == "normal"
    assert result.retrieval_count == 8
    assert result.execution_time_ms >= 0
    assert "retrieval" in result.latency_breakdown
    assert "llm_generation" in result.latency_breakdown
    assert result.metadata.get("status") == "success"
    assert "thought_process" in result.metadata


def test_4_citation_preservation():
    """Verify full source provenance (doc, page, slide, chunk, score, snippet) survives normalization."""
    adapter = QAAgentAdapter(qa_service_fn=mock_success_rag_response)
    req = AgentRequest(message="What is crude stabilization?")
    result = adapter.execute(req)

    assert len(result.citations) == 2
    
    # Check PDF source
    c1 = result.citations[0]
    assert c1["source_number"] == 1
    assert c1["document_name"] == "5.1_petroleum_refining.pdf"
    assert c1["page_number"] == 12
    assert c1["slide_number"] is None
    assert c1["content_type"] == "text"
    assert c1["score"] == 0.95
    assert "RVP" in c1["snippet"]

    # Check PPTX source
    c2 = result.citations[1]
    assert c2["source_number"] == 2
    assert c2["document_name"] == "Operations_Manual.pptx"
    assert c2["page_number"] is None
    assert c2["slide_number"] == 5
    assert c2["content_type"] == "slide"


def test_5_retrieval_error_handling():
    """Verify retrieval exceptions are safely caught and normalized into standard error contract."""
    def faulty_retrieval_service(*args, **kwargs):
        raise ConnectionError("Qdrant cluster connection refused on port 6333")

    adapter = QAAgentAdapter(qa_service_fn=faulty_retrieval_service)
    req = AgentRequest(message="What is the operating pressure of separator V-101?")
    result = adapter.execute(req)

    assert result.success is False
    assert result.status == TaskStatus.FAILED.value
    assert result.error is not None
    assert result.error["code"] == AgentErrorCode.AGENT_EXECUTION_ERROR.value
    assert "Qdrant cluster connection refused" in result.error["message"]
    assert "internal error" in result.response.lower() or "error occurred" in result.response.lower()


def test_6_generation_error_handling():
    """Verify LLM generation failures (e.g. status='llm_error') are normalized safely."""
    adapter = QAAgentAdapter(qa_service_fn=mock_llm_error_rag_response)
    req = AgentRequest(message="Explain distillation.")
    result = adapter.execute(req)

    assert result.success is False
    assert result.status == TaskStatus.FAILED.value
    assert result.error is not None
    assert result.error["code"] == AgentErrorCode.AGENT_EXECUTION_ERROR.value
    assert "LLM synthesis error" in result.error["message"]


def test_7_timeout_normalization():
    """Verify timeout conditions map cleanly to TaskStatus.TIMEOUT and AGENT_TIMEOUT."""
    def timeout_service(*args, **kwargs):
        raise TimeoutError("Execution exceeded 30s limit")

    adapter = QAAgentAdapter(qa_service_fn=timeout_service, timeout_seconds=10.0)
    req = AgentRequest(message="Complex multi-document comparison query.")
    result = adapter.execute(req)

    assert result.success is False
    assert result.status == TaskStatus.TIMEOUT.value
    assert result.error is not None
    assert result.error["code"] == AgentErrorCode.AGENT_TIMEOUT.value
    assert "timed out" in result.error["message"].lower()


def test_8_streaming_support():
    """Verify adapter stream() yields SSE tokens, citations, and completion events."""
    adapter = QAAgentAdapter(stream_service_fn=mock_streaming_generator)
    req = AgentRequest(message="What is crude stabilization?")
    
    events = list(adapter.stream(req))
    assert len(events) == 5
    
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 3
    full_text = "".join(e["content"] for e in token_events)
    assert full_text == "Crude stabilization process."

    citation_events = [e for e in events if e["type"] == "citations"]
    assert len(citation_events) == 1
    assert citation_events[0]["citations"][0]["document_name"] == "refining.pdf"

    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1


def test_9_registry_integration():
    """Verify QA Agent is discoverable in the registry as qa_technical_agent."""
    registered = agent_registry.get("qa_technical_agent")
    assert registered is not None
    assert registered.agent_id == "qa_technical_agent"
    assert registered.supports_streaming is True
    
    health = registered.health_check()
    assert health["status"] == "HEALTHY"
    assert "capabilities" in health


def test_10_orchestrator_integration_with_adapter(monkeypatch):
    """Verify full flow: Request -> Router -> Registry -> QA Adapter -> Result using mocked QA service."""
    # Temporarily mock the underlying service on qa_agent to avoid external network calls during unit test
    monkeypatch.setattr(qa_agent, "qa_service_fn", mock_success_rag_response)

    req = AgentRequest(
        request_id=str(uuid.uuid4()),
        message="What is crude stabilization in oil refining?",
        top_k=3,
        use_cache=True
    )
    
    # Route should identify QA intent
    route_res = intent_router.route(req.message)
    assert route_res.intent == AgentIntent.QA
    assert "qa_technical_agent" in route_res.target_agents

    # Orchestrator should resolve to qa_technical_agent and execute
    res = orchestrator.execute(req)
    assert res.agent_id == "qa_technical_agent"
    assert res.request_id == req.request_id
    assert res.success is True
    assert "Crude stabilization is the process" in res.response
    assert len(res.citations) == 2
