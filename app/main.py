# ============================================================
# CRITICAL: logfire MUST be configured before ALL other imports
# so that spans from all modules are captured from the start.
# ============================================================
import logfire
import os
import time
import json
import uuid
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()
logfire.configure(token=os.getenv("LOGFIRE_TOKEN"))

# Now safe to import app modules - logfire is already active
from fastapi import FastAPI, Response, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.agents.graph import rag_agent
from app.agents import (
    orchestrator,
    agent_registry,
    AgentRequest,
    AgentResult,
    AgentIntent
)
from app.guardrails import initialize_rails, guard
from app.services.generation import answer_query, stream_answer_query, RAGResponse, SourceCitation
from app.services.cache import cache_service
from app.services.session import conversation_manager, SessionState, ChatMessage
from app.db import (
    get_db,
    check_db_health,
    User,
    Conversation,
    Message,
    MessageCitation,
    MessageFeedback,
    AuditLog,
    DocumentMetadata,
    QueryLog,
)
from app.services.db_services import db_service
from app.security import (
    UserRole,
    UserPayload,
    create_access_token,
    get_current_user,
    require_role
)


from app.repositories.shift_handover_repository import (
    ConcurrencyConflictError,
    TerminalStateError,
    ShiftHandoverNotFoundError,
)
from app.governance import (
    hitl_service,
    policy_engine,
    ApprovalRequest,
    DecisionPayload,
    HITLDecision,
    HITLStatus,
    RiskLevel,
    HITLError,
    ApprovalNotFoundError,
    ApprovalAlreadyDecidedError,
    ApprovalExpiredError,
    SeparationOfDutiesViolationError,
    UnauthorizedApproverError,
    ApprovalReasonRequiredError,
    ApprovalStaleError,
    ApprovalAlreadyConsumedError,
)


from app.security.middleware import (
    GatewayCorrelationMiddleware,
    SecurityHeadersMiddleware
)
from app.security.rate_limiter import enforce_rate_limit, rate_limiter

# Initialize FastAPI Production Application
app = FastAPI(
    title="MASS QA & Shift Handover Multi-Agent API Gateway",
    description="Enterprise-grade Multimodal RAG & Shift Handover Multi-Agent Platform for Oil & Gas Technical Intelligence with PostgreSQL Persistence.",
    version="3.2.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Gateway Middleware Stack (Order: Correlation -> Security Headers -> CORS)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GatewayCorrelationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    initialize_rails()
    logfire.info("🚀 MASS QA Production API Gateway & PostgreSQL initialized successfully.")


# ============================================================
# REQUEST / RESPONSE DATA CONTRACTS
# ============================================================

class ProductionQueryRequest(BaseModel):
    query: Optional[str] = Field(None, description="User question or prompt.")
    question: Optional[str] = Field(None, description="User question or prompt alias.")
    message: Optional[str] = Field(None, description="User prompt or message alias.")
    q: Optional[str] = Field(None, description="Backward-compatible query field.")
    session_id: Optional[str] = Field(None, description="Unique session/conversation identifier.")
    thread_id: Optional[str] = Field(None, description="Backward-compatible thread identifier.")
    conversation_id: Optional[str] = Field(None, description="Optional conversation identifier.")
    stream: bool = Field(False, description="Enable Server-Sent Events (SSE) token streaming.")
    top_k: Optional[int] = Field(5, description="Number of top context chunks to retrieve.")
    use_cache: Optional[bool] = Field(True, description="Enable query and retrieval cache lookup.")
    context_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Operational context metadata.")

    def get_query_text(self) -> str:
        text = self.query or self.question or self.message or self.q or ""
        return text.strip()

    def get_session_id(self) -> str:
        return self.session_id or self.thread_id or self.conversation_id or str(uuid.uuid4())


class TokenRequest(BaseModel):
    user_id: str = "user-001"
    username: str = "engineer"
    role: str = "CONSOLE_OPERATOR"


class FeedbackRequest(BaseModel):
    message_id: str = Field(..., description="Target assistant message UUID.")
    rating: str = Field(..., description="Rating: 'POSITIVE' or 'NEGATIVE'.")
    comment: Optional[str] = Field(None, description="Optional user comment.")


class ConversationStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="Status: 'ACTIVE', 'ARCHIVED', or 'DELETED'.")


class ProductionQueryResponse(BaseModel):
    request_id: str
    session_id: str
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    question: str
    answer: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    query_type: str = "general_qa"
    confidence: str = "high"
    status: str = "success"
    requires_clarification: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None


# ============================================================
# UNIFIED GATEWAY EXCEPTION HANDLERS
# ============================================================

@app.exception_handler(ConcurrencyConflictError)
async def concurrency_exception_handler(request: Request, exc: ConcurrencyConflictError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logfire.warning(f"Concurrency conflict on {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": {
                "code": "CONCURRENCY_CONFLICT",
                "message": "Another user modified this handover. Please refresh and try again.",
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id}
    )


@app.exception_handler(TerminalStateError)
async def terminal_state_exception_handler(request: Request, exc: TerminalStateError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logfire.warning(f"Terminal state rejection on {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": {
                "code": "TERMINAL_STATE_LOCKED",
                "message": str(exc),
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id}
    )


@app.exception_handler(ShiftHandoverNotFoundError)
async def not_found_exception_handler(request: Request, exc: ShiftHandoverNotFoundError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": {
                "code": "SHIFT_HANDOVER_NOT_FOUND",
                "message": str(exc),
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id}
    )


@app.exception_handler(ApprovalNotFoundError)
async def hitl_not_found_handler(request: Request, exc: ApprovalNotFoundError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": {
                "code": "APPROVAL_NOT_FOUND",
                "message": str(exc),
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id}
    )


@app.exception_handler(ApprovalAlreadyDecidedError)
@app.exception_handler(ApprovalAlreadyConsumedError)
async def hitl_conflict_handler(request: Request, exc: HITLError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": {
                "code": "APPROVAL_CONFLICT",
                "message": str(exc),
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id}
    )


@app.exception_handler(ApprovalStaleError)
async def hitl_stale_handler(request: Request, exc: ApprovalStaleError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": {
                "code": "APPROVAL_STALE",
                "message": str(exc),
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id}
    )


@app.exception_handler(SeparationOfDutiesViolationError)
@app.exception_handler(UnauthorizedApproverError)
async def hitl_forbidden_handler(request: Request, exc: HITLError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": {
                "code": "APPROVAL_FORBIDDEN",
                "message": str(exc),
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id}
    )


@app.exception_handler(ApprovalExpiredError)
@app.exception_handler(ApprovalReasonRequiredError)
async def hitl_bad_request_handler(request: Request, exc: HITLError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": {
                "code": "APPROVAL_INVALID",
                "message": str(exc),
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logfire.warning(f"Validation error on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request payload.",
                "request_id": req_id,
                "details": exc.errors()
            }
        },
        headers={"X-Request-ID": req_id}
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    if isinstance(exc.detail, dict):
        err_code = exc.detail.get("code", f"HTTP_{exc.status_code}")
        err_msg = exc.detail.get("message", "An error occurred.")
        err_details = {k: v for k, v in exc.detail.items() if k not in ("code", "message")}
    else:
        err_code = f"HTTP_{exc.status_code}"
        err_msg = str(exc.detail)
        err_details = None

    content = {
        "error": {
            "code": err_code,
            "message": err_msg,
            "request_id": req_id
        }
    }
    if err_details:
        content["error"]["details"] = err_details

    headers = {"X-Request-ID": req_id}
    if exc.headers:
        headers.update(exc.headers)

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=headers
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logfire.error(f"Unhandled server error [req_id={req_id}]: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal error occurred while processing the request.",
                "request_id": req_id
            }
        },
        headers={"X-Request-ID": req_id}
    )


# ============================================================
# CORE API ENDPOINTS
# ============================================================

@app.get("/")
def home():
    return {
        "message": "MASS QA Production Hybrid RAG API is live with PostgreSQL Persistence.",
        "version": "3.1.0",
        "database": "PostgreSQL 18 (MASS.public)",
        "features": [
            "Hybrid Retrieval V2",
            "FlashRank Reranking",
            "Grounded Citations",
            "Multi-Layer Caching (Redis + Memory)",
            "SSE Token Streaming",
            "PostgreSQL 18 Application Persistence",
            "Session & Conversation Management",
            "NeMo Guardrails Gate",
            "JWT Authentication"
        ]
    }


@app.get("/health")
def health():
    """
    Liveness & database availability probe.
    """
    db_ok = check_db_health()
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "mass-qa-rag",
        "version": "3.1.0",
        "database": "connected" if db_ok else "unreachable"
    }


@app.get("/ready")
def ready():
    """
    Readiness probe: validates dependencies and configurations without running expensive queries.
    """
    db_ok = check_db_health()
    deps = {
        "postgresql": "connected" if db_ok else "unreachable",
        "qdrant": "configured" if settings.QDRANT_URL else "unconfigured",
        "cache": "connected" if cache_service.is_connected else "in_memory_fallback",
        "llm_gateway": "configured" if settings.GEMINI_API_KEY or settings.GROQ_API_KEY else "unconfigured",
        "guardrails": "initialized"
    }
    is_ready = bool(db_ok and settings.QDRANT_URL and (settings.GEMINI_API_KEY or settings.GROQ_API_KEY))
    return {
        "status": "ready" if is_ready else "degraded",
        "dependencies": deps
    }


@app.get("/graph")
def get_graph_image():
    """
    Returns the Mermaid image of the agent's workflow.
    """
    try:
        png_bytes = rag_agent.get_graph().draw_mermaid_png()
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        return {"error": f"Could not generate graph image: {e}"}


@app.post("/auth/token")
def generate_token(req: TokenRequest, raw_request: Request = None, db: Session = Depends(get_db)):
    """
    Generate signed JWT Bearer token for API access.
    """
    if raw_request is not None:
        enforce_rate_limit(raw_request, endpoint_type="auth")

    token = create_access_token(
        user_id=req.user_id,
        username=req.username,
        role=req.role
    )
    db_service.log_audit_event(
        db,
        action="LOGIN",
        user_id=req.user_id,
        endpoint="/auth/token",
        http_method="POST",
        status_code=200
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": settings.JWT_EXPIRATION_MINUTES,
        "user": {
            "user_id": req.user_id,
            "username": req.username,
            "role": req.role
        }
    }


# ============================================================
# PERSISTENT CONVERSATION & FEEDBACK ENDPOINTS
# ============================================================

@app.get("/conversations")
def list_conversations(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    List historical conversations for the authenticated user.
    """
    convs = db_service.list_user_conversations(db, user_id=current_user.user_id, limit=limit)
    return [
        {
            "id": c.id,
            "session_id": c.session_id,
            "title": c.title,
            "status": c.status,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "last_message_at": c.last_message_at
        }
        for c in convs
    ]


@app.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Retrieve all messages and citations in a conversation.
    """
    conv = db_service.get_conversation_by_id(db, conversation_id=conversation_id, user_id=current_user.user_id)
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found or unauthorized.")

    result = []
    for msg in conv.messages:
        result.append({
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "model_name": msg.model_name,
            "response_time_ms": msg.response_time_ms,
            "cache_hit": msg.cache_hit,
            "created_at": msg.created_at,
            "citations": [
                {
                    "id": cit.id,
                    "document_name": cit.document_name,
                    "page_number": cit.page_number,
                    "slide_number": cit.slide_number,
                    "source_type": cit.source_type,
                    "score": cit.score,
                    "citation_text": cit.citation_text
                }
                for cit in msg.citations
            ]
        })
    return {"conversation_id": conversation_id, "title": conv.title, "messages": result}


@app.patch("/conversations/{conversation_id}/status")
def update_conversation_status(
    conversation_id: str,
    req: ConversationStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Update status of a conversation (e.g. 'ARCHIVED', 'DELETED').
    """
    success = db_service.update_conversation_status(
        db,
        conversation_id=conversation_id,
        status=req.status.upper(),
        user_id=current_user.user_id
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found or unauthorized.")
    return {"status": "success", "conversation_id": conversation_id, "new_status": req.status.upper()}


@app.post("/feedback")
def submit_feedback(
    req: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Submit positive/negative rating and comments on an assistant message.
    """
    fb = db_service.submit_feedback(
        db,
        message_id=req.message_id,
        rating=req.rating,
        user_id=current_user.user_id,
        comment=req.comment
    )
    db_service.log_audit_event(
        db,
        action="FEEDBACK_SUBMITTED",
        user_id=current_user.user_id,
        resource_type="message",
        resource_id=req.message_id,
        metadata={"rating": req.rating, "feedback_id": fb.id}
    )
    return {
        "status": "success",
        "feedback_id": fb.id,
        "message_id": fb.message_id,
        "rating": fb.rating
    }


@app.get("/sessions/{session_id}")
def get_session_history(
    session_id: str,
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Retrieve conversation history and messages for a specific session.
    """
    session = conversation_manager.get_or_create_session(session_id, user_id=current_user.user_id)
    return session


@app.delete("/sessions/{session_id}")
def clear_session_history(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Wipe conversation history for a given session in cache and mark database conversation as archived.
    """
    conversation_manager.clear_session(session_id)
    conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
    if conv:
        conv.status = "ARCHIVED"
        db.commit()
    return {"message": f"Session '{session_id}' memory cleared successfully.", "session_id": session_id}


@app.get("/agents")
def list_registered_agents():
    """
    List all agents currently registered in the Agent Foundation registry.
    """
    return {
        "status": "ok",
        "count": len(agent_registry.list_agents()),
        "agents": agent_registry.list_agents()
    }


# ============================================================
# UNIFIED PRODUCTION QUERY ENDPOINT (ORCHESTRATOR PERSISTED)
# ============================================================

@app.post("/query")
async def query_endpoint(
    request: ProductionQueryRequest,
    raw_request: Request = None,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Executes the Production Agentic Workflow:
    Auth -> Rate Limit -> Guardrails -> PostgreSQL Persistence -> Agent Orchestrator -> Target Agent (QA / Shift Handover) -> Grounded Generation -> Citations -> Metric Logging.
    """
    if raw_request is not None:
        enforce_rate_limit(raw_request, endpoint_type="stream" if request.stream else "query")

    q = request.get_query_text()
    if not q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query text cannot be empty."
        )

    session_id = request.get_session_id()
    top_k = request.top_k or 5
    use_cache = request.use_cache if request.use_cache is not None else True
    req_id = getattr(raw_request.state, "request_id", str(uuid.uuid4())) if raw_request and hasattr(raw_request, "state") else str(uuid.uuid4())
    t_start = time.time()

    # 1. PostgreSQL: Get/Create persistent conversation and save User message
    db_conv = db_service.get_or_create_conversation(db, session_id=session_id, user_id=current_user.user_id, title=q[:60])
    u_msg = db_service.create_message(
        db,
        conversation_id=db_conv.id,
        role="USER",
        content=q,
        user_id=current_user.user_id
    )

    # Log audit event
    db_service.log_audit_event(
        db,
        action="QUERY",
        user_id=current_user.user_id,
        request_id=req_id,
        session_id=session_id,
        endpoint="/query",
        http_method="POST"
    )

    # 2. NeMo Guardrails & Greetings Fast-Path Gate
    rail_fired, rail_response = guard(q)
    if rail_fired:
        refusal_msg = rail_response or "I can help with questions related to the MASS QA / ORS knowledge base, including product functionality, operational procedures, workflows, troubleshooting and technical documentation."
        t_refusal = round((time.time() - t_start) * 1000, 2)

        # Persist assistant message in DB & Session
        a_msg = db_service.create_message(
            db,
            conversation_id=db_conv.id,
            role="ASSISTANT",
            content=refusal_msg,
            user_id=current_user.user_id,
            response_time_ms=t_refusal,
            status="BLOCKED_BY_GUARDRAILS"
        )
        conversation_manager.add_message(session_id, role="user", content=q, user_id=current_user.user_id)
        conversation_manager.add_message(session_id, role="assistant", content=refusal_msg, user_id=current_user.user_id)

        # Query metrics logging
        db_service.log_query_metrics(
            db,
            query_text=q,
            user_id=current_user.user_id,
            conversation_id=db_conv.id,
            message_id=a_msg.id,
            total_time_ms=t_refusal,
            status="BLOCKED_BY_GUARDRAILS",
            request_id=req_id
        )

        if request.stream:
            async def sse_refusal():
                yield {"event": "heartbeat", "data": json.dumps({"type": "heartbeat", "timestamp": time.time()})}
                yield {"data": json.dumps({"type": "token", "content": refusal_msg})}
                yield {"data": json.dumps({"type": "citations", "citations": []})}
                yield {"data": json.dumps({
                    "type": "done",
                    "request_id": req_id,
                    "message_id": a_msg.id,
                    "conversation_id": db_conv.id,
                    "metadata": {
                        "cached": False,
                        "guardrails_blocked": True,
                        "confidence": "refused",
                        "total_latency_ms": t_refusal
                    }
                })}
            return EventSourceResponse(sse_refusal(), headers={"X-Request-ID": req_id})

        return ProductionQueryResponse(
            request_id=req_id,
            session_id=session_id,
            conversation_id=db_conv.id,
            message_id=a_msg.id,
            question=q,
            answer=refusal_msg,
            citations=[],
            query_type="out_of_domain",
            confidence="refused",
            metadata={
                "cached": False,
                "guardrails_blocked": True,
                "total_latency_ms": t_refusal
            }
        )

    # 3. Extract sliding conversation context
    conversation_manager.add_message(session_id, role="user", content=q, user_id=current_user.user_id)
    history = conversation_manager.get_bounded_history(session_id)

    # 4. Construct AgentRequest for Orchestration with authenticated user role
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    agent_req = AgentRequest(
        request_id=req_id,
        user_id=current_user.user_id,
        user_role=user_role_str,
        conversation_id=db_conv.id,
        session_id=session_id,
        message=q,
        top_k=top_k,
        use_cache=use_cache,
        conversation_history=history,
        metadata=request.context_metadata or {}
    )

    # 5. Handle Streaming Request via Orchestrator
    if request.stream:
        async def sse_generator():
            full_answer_chunks = []
            final_citations = []
            yield {"event": "heartbeat", "data": json.dumps({"type": "heartbeat", "timestamp": time.time()})}
            try:
                for event in orchestrator.stream(agent_req):
                    if event.get("type") == "token":
                        full_answer_chunks.append(event.get("content", ""))
                    elif event.get("type") == "citations":
                        final_citations = event.get("citations", [])

                    yield {"data": json.dumps(event)}
            except Exception as ex:
                logfire.error(f"SSE stream error: {ex}")
                yield {"event": "error", "data": json.dumps({"type": "error", "message": "An error occurred during streaming."})}

            complete_answer = "".join(full_answer_chunks)
            t_stream_total = round((time.time() - t_start) * 1000, 2)

            if complete_answer:
                # Save assistant message & citations in PostgreSQL
                a_msg = db_service.create_message(
                    db,
                    conversation_id=db_conv.id,
                    role="ASSISTANT",
                    content=complete_answer,
                    user_id=current_user.user_id,
                    response_time_ms=t_stream_total
                )
                if final_citations:
                    db_service.create_citations(db, message_id=a_msg.id, citations=final_citations)

                # Query metrics log
                db_service.log_query_metrics(
                    db,
                    query_text=q,
                    user_id=current_user.user_id,
                    conversation_id=db_conv.id,
                    message_id=a_msg.id,
                    total_time_ms=t_stream_total,
                    retrieved_count=len(final_citations),
                    request_id=req_id
                )

                # Persist to memory
                conversation_manager.add_message(
                    session_id,
                    role="assistant",
                    content=complete_answer,
                    citations=final_citations,
                    user_id=current_user.user_id
                )

        return EventSourceResponse(sse_generator(), headers={"X-Request-ID": req_id})

    # 6. Handle Synchronous Request via Orchestrator
    agent_res: AgentResult = orchestrator.execute(agent_req)

    t_total = time.time() - t_start
    t_total_ms = round(t_total * 1000, 2)
    is_cached = agent_res.metadata.get("cached", False)
    citations_data = agent_res.citations

    # Save Assistant message in PostgreSQL
    a_msg = db_service.create_message(
        db,
        conversation_id=db_conv.id,
        role="ASSISTANT",
        content=agent_res.response,
        user_id=current_user.user_id,
        response_time_ms=t_total_ms,
        cache_hit=is_cached,
        status="SUCCESS" if agent_res.success else "ERROR"
    )

    # Save Citations in PostgreSQL
    if citations_data:
        db_service.create_citations(db, message_id=a_msg.id, citations=citations_data)

    # Save Query Log in PostgreSQL
    db_service.log_query_metrics(
        db,
        query_text=q,
        user_id=current_user.user_id,
        conversation_id=db_conv.id,
        message_id=a_msg.id,
        retrieval_time_ms=round(agent_res.latency_breakdown.get("retrieval", 0) * 1000, 2),
        reranking_time_ms=0,
        llm_time_ms=round(agent_res.latency_breakdown.get("llm_generation", 0) * 1000, 2),
        total_time_ms=t_total_ms,
        retrieved_count=agent_res.retrieval_count,
        cache_hit=is_cached,
        status="SUCCESS" if agent_res.success else "ERROR",
        request_id=req_id
    )

    # Save to memory cache
    conversation_manager.add_message(
        session_id,
        role="assistant",
        content=agent_res.response,
        citations=citations_data,
        user_id=current_user.user_id
    )

    return ProductionQueryResponse(
        request_id=req_id,
        session_id=session_id,
        conversation_id=db_conv.id,
        message_id=a_msg.id,
        question=q,
        answer=agent_res.response,
        citations=citations_data,
        query_type=agent_res.query_type,
        confidence=agent_res.confidence,
        status=agent_res.status,
        requires_clarification=agent_res.metadata.get("requires_clarification", False),
        error=agent_res.error,
        metadata={
            **agent_res.metadata,
            "cached": is_cached,
            "agent_id": agent_res.agent_id,
            "retrieval_count": agent_res.retrieval_count,
            "grounded": agent_res.grounded,
            "latency_breakdown": agent_res.latency_breakdown,
            "total_latency_ms": t_total_ms
        }
    )


@app.post("/query/stream")
async def query_stream_endpoint(
    request: ProductionQueryRequest,
    raw_request: Request = None,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Dedicated endpoint for Server-Sent Events (SSE) streaming.
    """
    request.stream = True
    return await query_endpoint(request, raw_request=raw_request, db=db, current_user=current_user)


# ============================================================
# CANONICAL API V1 GATEWAY ROUTES (VERSIONED ALIASES)
# ============================================================

@app.post("/api/v1/query")
async def api_v1_query(
    request: ProductionQueryRequest,
    raw_request: Request = None,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    return await query_endpoint(request, raw_request=raw_request, db=db, current_user=current_user)


@app.post("/api/v1/query/stream")
async def api_v1_query_stream(
    request: ProductionQueryRequest,
    raw_request: Request = None,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    request.stream = True
    return await query_endpoint(request, raw_request=raw_request, db=db, current_user=current_user)


@app.get("/api/v1/health")
def api_v1_health():
    return health()


@app.get("/api/v1/ready")
def api_v1_ready():
    return ready()


@app.get("/api/v1/agents")
def api_v1_agents():
    return list_registered_agents()


@app.post("/api/v1/auth/token")
def api_v1_token(req: TokenRequest, raw_request: Request = None, db: Session = Depends(get_db)):
    return generate_token(req, raw_request=raw_request, db=db)


# ============================================================
# HUMAN-IN-THE-LOOP (HITL) APPROVAL GOVERNANCE ENDPOINTS
# ============================================================

@app.get("/approvals")
def list_approvals_endpoint(
    handover_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    List HITL approval requests with optional status and handover filtering.
    """
    status_enum = None
    if status:
        try:
            status_enum = HITLStatus(status.upper())
        except ValueError:
            pass

    approvals = hitl_service.list_approvals(handover_id=handover_id, status=status_enum, db=db)
    return {
        "status": "ok",
        "count": len(approvals),
        "approvals": [a.model_dump() for a in approvals]
    }


@app.get("/approvals/{approval_id}")
def get_approval_details_endpoint(
    approval_id: str,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Retrieve specific HITL approval request status, payload, and history.
    """
    approval = hitl_service.get_approval(approval_id, db=db)
    if not approval:
        raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")
    return approval.model_dump()


@app.post("/approvals/{approval_id}/approve")
def approve_request_endpoint(
    approval_id: str,
    payload: Optional[DecisionPayload] = None,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Authoritative Human Approval: decides request and consumes/executes deterministic workflow.
    """
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    approval = hitl_service.decide_approval(
        approval_id=approval_id,
        decision=HITLDecision.APPROVE,
        decider_id=current_user.user_id,
        decider_role=user_role_str,
        reason=payload.reason if payload else None,
        db=db
    )
    consumed_approval, wf_res = hitl_service.consume_and_execute(approval_id, db=db)
    return {
        "status": "success",
        "approval": consumed_approval.model_dump(),
        "workflow_result": wf_res
    }


@app.post("/approvals/{approval_id}/reject")
def reject_request_endpoint(
    approval_id: str,
    payload: DecisionPayload,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Authoritative Human Rejection: rejects action with mandatory operational reason.
    """
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    approval = hitl_service.decide_approval(
        approval_id=approval_id,
        decision=HITLDecision.REJECT,
        decider_id=current_user.user_id,
        decider_role=user_role_str,
        reason=payload.reason,
        db=db
    )
    return {
        "status": "success",
        "approval": approval.model_dump()
    }


@app.post("/approvals/{approval_id}/return")
def return_request_endpoint(
    approval_id: str,
    payload: DecisionPayload,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Authoritative Human Return: returns handover action for rework with explanation.
    """
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    approval = hitl_service.decide_approval(
        approval_id=approval_id,
        decision=HITLDecision.RETURN,
        decider_id=current_user.user_id,
        decider_role=user_role_str,
        reason=payload.reason,
        db=db
    )
    return {
        "status": "success",
        "approval": approval.model_dump()
    }


@app.post("/approvals/{approval_id}/escalate")
def escalate_request_endpoint(
    approval_id: str,
    payload: Optional[DecisionPayload] = None,
    db: Session = Depends(get_db),
    current_user: UserPayload = Depends(get_current_user)
):
    """
    Escalate approval request to higher management.
    """
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    approval = hitl_service.decide_approval(
        approval_id=approval_id,
        decision=HITLDecision.ESCALATE,
        decider_id=current_user.user_id,
        decider_role=user_role_str,
        reason=payload.reason if payload else None,
        db=db
    )
    return {
        "status": "success",
        "approval": approval.model_dump()
    }


# Canonical /api/v1/ Approvals Aliases
@app.get("/api/v1/approvals")
def api_v1_list_approvals(handover_id: Optional[str] = None, status: Optional[str] = None, db: Session = Depends(get_db), current_user: UserPayload = Depends(get_current_user)):
    return list_approvals_endpoint(handover_id=handover_id, status=status, db=db, current_user=current_user)


@app.get("/api/v1/approvals/{approval_id}")
def api_v1_get_approval(approval_id: str, db: Session = Depends(get_db), current_user: UserPayload = Depends(get_current_user)):
    return get_approval_details_endpoint(approval_id=approval_id, db=db, current_user=current_user)


@app.post("/api/v1/approvals/{approval_id}/approve")
def api_v1_approve(approval_id: str, payload: Optional[DecisionPayload] = None, db: Session = Depends(get_db), current_user: UserPayload = Depends(get_current_user)):
    return approve_request_endpoint(approval_id=approval_id, payload=payload, db=db, current_user=current_user)


@app.post("/api/v1/approvals/{approval_id}/reject")
def api_v1_reject(approval_id: str, payload: DecisionPayload, db: Session = Depends(get_db), current_user: UserPayload = Depends(get_current_user)):
    return reject_request_endpoint(approval_id=approval_id, payload=payload, db=db, current_user=current_user)


@app.post("/api/v1/approvals/{approval_id}/return")
def api_v1_return(approval_id: str, payload: DecisionPayload, db: Session = Depends(get_db), current_user: UserPayload = Depends(get_current_user)):
    return return_request_endpoint(approval_id=approval_id, payload=payload, db=db, current_user=current_user)

