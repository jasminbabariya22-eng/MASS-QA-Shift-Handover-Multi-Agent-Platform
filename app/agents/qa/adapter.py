from typing import Dict, Any, Generator, Optional, Callable, List
import time
import logfire

from app.config import settings
from app.agents.base import BaseAgent
from app.agents.contracts import (
    AgentRequest,
    RequestContext,
    AgentContext,
    AgentResult,
    AgentResponse,
    AgentErrorCode,
    TaskStatus,
)
from app.services.generation import answer_query, stream_answer_query, RAGResponse, SourceCitation


class QAAgentAdapter(BaseAgent):
    """
    MASS QA Technical Agent Adapter.
    
    Acts as the production boundary wrapping the validated MASS QA Hybrid Retrieval V2 +
    FlashRank Reranking + Grounded Generation pipeline into the Step 3 Agent Architecture.
    
    Standardized capabilities:
    - answer_question
    - search_knowledge_base
    - return_citations
    - technical_qa
    """

    def __init__(
        self,
        qa_service_fn: Optional[Callable[..., RAGResponse]] = None,
        stream_service_fn: Optional[Callable[..., Generator[Dict[str, Any], None, None]]] = None,
        timeout_seconds: Optional[float] = None,
    ):
        super().__init__(
            agent_id="qa_technical_agent",
            name="MASS QA Technical Agent",
            description="Answers petroleum refining, process engineering, equipment, and policy questions with grounded citations.",
            capabilities=[
                "answer_question",
                "search_knowledge_base",
                "return_citations",
                "technical_qa"
            ]
        )
        self.qa_service_fn = qa_service_fn or answer_query
        self.stream_service_fn = stream_service_fn or stream_answer_query
        self.timeout_seconds = timeout_seconds or float(getattr(settings, "GATEWAY_TIMEOUT", 30.0))

    def execute(self, request: AgentRequest, context: Optional[AgentContext] = None) -> AgentResult:
        """
        Execute synchronous QA pipeline over the frozen RAG engine and normalize
        the output into the standardized Step 3 AgentResult.
        """
        t_start = time.time()
        req_id = request.request_id
        session_id = request.session_id if request else (context.session_id if context else "unknown")

        logfire.info(
            f"[{self.agent_id}] Processing QA request [req_id={req_id}, session_id={session_id}]: "
            f"{request.message[:80] if request.message else '<empty>'}"
        )

        # 1. Validate Input
        if not request.message or not request.message.strip():
            return AgentResult(
                request_id=req_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED.value,
                success=False,
                response="Invalid query: message cannot be empty.",
                citations=[],
                confidence="insufficient",
                query_type="invalid_request",
                grounded=False,
                execution_time_ms=0.0,
                error={
                    "code": AgentErrorCode.INVALID_REQUEST.value,
                    "message": "Query message cannot be empty or whitespace only.",
                    "details": {"request_id": req_id}
                }
            )

        try:
            # 2. Invoke QA Pipeline via Injected Service
            rag_resp: RAGResponse = self.qa_service_fn(
                question=request.message,
                top_k=request.top_k,
                conversation_history=request.conversation_history,
                use_cache=request.use_cache
            )

            t_total_ms = round((time.time() - t_start) * 1000, 2)

            # 3. Check for timeout or error status in RAG response
            if rag_resp.status == "llm_error":
                return AgentResult(
                    request_id=req_id,
                    agent_id=self.agent_id,
                    status=TaskStatus.FAILED.value,
                    success=False,
                    response=rag_resp.answer,
                    citations=self._normalize_citations(rag_resp.sources),
                    confidence=rag_resp.confidence,
                    query_type=rag_resp.query_type,
                    grounded=rag_resp.grounded,
                    retrieval_count=rag_resp.retrieval_count,
                    execution_time_ms=t_total_ms,
                    latency_breakdown=rag_resp.latency_breakdown or {},
                    metadata={"status": rag_resp.status},
                    error={
                        "code": AgentErrorCode.AGENT_EXECUTION_ERROR.value,
                        "message": "LLM synthesis error occurred during answer generation.",
                        "details": {"status": rag_resp.status}
                    }
                )

            # 4. Normalize Success / Insufficient Evidence Response
            citations_data = self._normalize_citations(rag_resp.sources)
            is_cached = bool(rag_resp.latency_breakdown and "cache_lookup" in rag_resp.latency_breakdown)

            return AgentResult(
                request_id=req_id,
                agent_id=self.agent_id,
                status=TaskStatus.COMPLETED.value if rag_resp.status == "success" else rag_resp.status,
                success=(rag_resp.status in ("success", "insufficient_evidence")),
                response=rag_resp.answer,
                citations=citations_data,
                confidence=rag_resp.confidence,
                query_type=rag_resp.query_type,
                grounded=rag_resp.grounded,
                retrieval_count=rag_resp.retrieval_count,
                execution_time_ms=t_total_ms,
                latency_breakdown=rag_resp.latency_breakdown or {},
                metadata={
                    "cached": is_cached,
                    "status": rag_resp.status,
                    "thought_process": rag_resp.thought_process or []
                }
            )

        except TimeoutError as te:
            t_total_ms = round((time.time() - t_start) * 1000, 2)
            logfire.error(f"[{self.agent_id}] QA timeout: {te} [req_id={req_id}]")
            return AgentResult(
                request_id=req_id,
                agent_id=self.agent_id,
                status=TaskStatus.TIMEOUT.value,
                success=False,
                response="The request to the QA service timed out. Please try again.",
                citations=[],
                confidence="low",
                query_type="timeout",
                grounded=False,
                execution_time_ms=t_total_ms,
                error={
                    "code": AgentErrorCode.AGENT_TIMEOUT.value,
                    "message": f"QA pipeline execution timed out after {self.timeout_seconds}s.",
                    "details": {"timeout_seconds": self.timeout_seconds}
                }
            )

        except Exception as exc:
            t_total_ms = round((time.time() - t_start) * 1000, 2)
            logfire.error(f"[{self.agent_id}] QA execution failure: {exc} [req_id={req_id}]")
            return AgentResult(
                request_id=req_id,
                agent_id=self.agent_id,
                status=TaskStatus.FAILED.value,
                success=False,
                response="An internal error occurred while processing the technical question. Please try again.",
                citations=[],
                confidence="low",
                query_type="error",
                grounded=False,
                execution_time_ms=t_total_ms,
                error={
                    "code": AgentErrorCode.AGENT_EXECUTION_ERROR.value,
                    "message": str(exc) if not any(k in str(exc).lower() for k in ["key", "secret", "token", "password"]) else "Internal service error",
                    "details": {"exception_type": type(exc).__name__}
                }
            )

    def stream(self, request: AgentRequest, context: Optional[AgentContext] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Execute streaming QA pipeline yielding real-time SSE tokens, citations, and completion events.
        """
        req_id = request.request_id
        logfire.info(f"[{self.agent_id}] Streaming QA query [req_id={req_id}]: {request.message[:80] if request.message else '<empty>'}")

        if not request.message or not request.message.strip():
            yield {
                "type": "error",
                "error": {
                    "code": AgentErrorCode.INVALID_REQUEST.value,
                    "message": "Query message cannot be empty."
                }
            }
            return

        try:
            for event in self.stream_service_fn(
                question=request.message,
                top_k=request.top_k,
                conversation_history=request.conversation_history,
                use_cache=request.use_cache
            ):
                yield event
        except Exception as exc:
            logfire.error(f"[{self.agent_id}] Streaming QA failure: {exc} [req_id={req_id}]")
            yield {
                "type": "error",
                "error": {
                    "code": AgentErrorCode.AGENT_EXECUTION_ERROR.value,
                    "message": "Error streaming response from QA service."
                }
            }

    def _normalize_citations(self, sources: List[Any]) -> List[Dict[str, Any]]:
        """
        Normalize sources into structured citation dictionaries, preserving all
        document, page, slide, chunk, score, and snippet metadata.
        """
        normalized = []
        for s in sources:
            if isinstance(s, dict):
                normalized.append(s)
            elif hasattr(s, "model_dump"):
                normalized.append(s.model_dump())
            elif hasattr(s, "__dict__"):
                normalized.append(vars(s))
            else:
                normalized.append({"source": str(s)})
        return normalized


# Backwards compatibility alias
QAAgent = QAAgentAdapter
