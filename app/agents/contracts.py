from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class AgentIntent(str, Enum):
    QA = "QA"
    SHIFT = "SHIFT"
    SHIFT_HANDOVER = "SHIFT"  # Backwards compatibility alias
    LOOP_ENGINEERING = "LOOP_ENGINEERING"
    MULTI_AGENT = "MULTI_AGENT"
    GENERAL = "GENERAL"
    HIGH_RISK = "HIGH_RISK"
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class AgentErrorCode(str, Enum):
    ROUTING_ERROR = "ROUTING_ERROR"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    AGENT_UNAVAILABLE = "AGENT_UNAVAILABLE"
    INVALID_AGENT_RESPONSE = "INVALID_AGENT_RESPONSE"
    CONTEXT_ERROR = "CONTEXT_ERROR"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    HIGH_RISK_REJECTED = "HIGH_RISK_REJECTED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    AGENT_EXECUTION_ERROR = "AGENT_EXECUTION_ERROR"
    INVALID_AGENT = "INVALID_AGENT"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNKNOWN_INTENT = "UNKNOWN_INTENT"
    LOOP_NOT_FOUND = "LOOP_NOT_FOUND"
    LOOP_CONFIGURATION_CONFLICT = "LOOP_CONFIGURATION_CONFLICT"


class RoutingResult(BaseModel):
    """
    Strongly typed intent and risk routing result emitted by IntentRouter.
    """
    intent: AgentIntent
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = "Deterministic classification"
    target_agents: List[str] = Field(default_factory=list)
    requires_clarification: bool = False
    risk_level: RiskLevel = RiskLevel.LOW


class AgentRequest(BaseModel):
    """
    Structured request contract passed into the Agent Orchestration layer.
    """
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message_id: Optional[str] = None
    user_role: Optional[str] = None
    message: str = Field(..., description="User prompt or query.")
    intent: Optional[AgentIntent] = None
    top_k: int = Field(5, description="Number of context items.")
    use_cache: bool = Field(True, description="Whether to query cache.")
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RequestContext(BaseModel):
    """
    Shared execution context propagated across the orchestration lifecycle.
    """
    request_id: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    session_id: str
    message_id: Optional[str] = None
    user_role: Optional[str] = None
    intent: AgentIntent = AgentIntent.QA
    target_agents: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_info: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    parent_task_id: Optional[str] = None
    trace_info: Dict[str, Any] = Field(default_factory=dict)
    permissions: List[str] = Field(default_factory=lambda: ["qa.read"])
    current_agent: Optional[str] = None
    previous_agent: Optional[str] = None


# Alias for backward compatibility
AgentContext = RequestContext


class AgentResult(BaseModel):
    """
    Normalized response contract returned by individual Agents and the Orchestrator.
    """
    request_id: str
    agent_id: str
    status: str = "success"
    success: bool = True
    response: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: str = "high"
    query_type: str = "general_qa"
    grounded: bool = True
    retrieval_count: int = 0
    execution_time_ms: float = 0.0
    latency_breakdown: Dict[str, float] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None

    @property
    def answer(self) -> str:
        return self.response


# Alias for backward compatibility
AgentResponse = AgentResult


class AgentTask(BaseModel):
    """
    Generic task contract for agent-to-agent delegation and lifecycle tracking.
    """
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_task_id: Optional[str] = None
    request_id: str
    source: str
    target: str
    task_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    timeout: float = 20.0
    error: Optional[Dict[str, Any]] = None
