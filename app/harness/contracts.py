from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid

from app.agents.contracts import (
    AgentRequest,
    RequestContext,
    AgentResult,
    AgentResponse,
    AgentIntent,
    RiskLevel,
    TaskStatus,
    AgentErrorCode
)


class HarnessPolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRES_HUMAN_APPROVAL = "REQUIRES_HUMAN_APPROVAL"
    MODIFY = "MODIFY"
    RETRY = "RETRY"


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    DENIED = "DENIED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class HarnessErrorClassification(str, Enum):
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    SAFETY = "SAFETY"
    AUTHORIZATION = "AUTHORIZATION"
    VALIDATION = "VALIDATION"
    NOT_FOUND = "NOT_FOUND"
    CONCURRENCY = "CONCURRENCY"
    TIMEOUT = "TIMEOUT"
    DEPENDENCY = "DEPENDENCY"


class ToolPermission(str, Enum):
    # QA Tools
    RETRIEVE_DOCUMENT = "RETRIEVE_DOCUMENT"
    SEARCH_KNOWLEDGE_BASE = "SEARCH_KNOWLEDGE_BASE"
    GENERATE_GROUNDED_ANSWER = "GENERATE_GROUNDED_ANSWER"
    
    # Shift Tools
    CREATE_HANDOVER = "CREATE_HANDOVER"
    READ_HANDOVER = "READ_HANDOVER"
    UPDATE_HANDOVER = "UPDATE_HANDOVER"
    TRANSITION_HANDOVER = "TRANSITION_HANDOVER"
    READ_AUDIT = "READ_AUDIT"
    MANAGE_SAFETY_ITEMS = "MANAGE_SAFETY_ITEMS"
    
    # Loop Engineering Tools
    READ_LOOP = "READ_LOOP"
    READ_INSTRUMENT = "READ_INSTRUMENT"
    READ_IO_MAPPING = "READ_IO_MAPPING"
    READ_ENGINEERING_DOCUMENT = "READ_ENGINEERING_DOCUMENT"
    VALIDATE_LOOP = "VALIDATE_LOOP"
    
    # Prohibited Autonomous Operations
    REMOTE_EQUIPMENT_CONTROL = "REMOTE_EQUIPMENT_CONTROL"


class ExecutionBudget(BaseModel):
    max_execution_time_seconds: float = Field(default=30.0, description="Max allowed execution duration.")
    max_agent_calls: int = Field(default=2, description="Max specialized agent dispatches per request.")
    max_tool_calls: int = Field(default=10, description="Max tool executions.")
    max_depth: int = Field(default=3, description="Max nested invocation depth.")
    max_retries: int = Field(default=2, description="Max retries for transient errors.")
    max_response_bytes: int = Field(default=100_000, description="Max output character length.")


class HarnessRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(..., description="Authenticated user ID.")
    user_role: str = Field(default="CONSOLE_OPERATOR", description="Authenticated role.")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: Optional[str] = None
    message: str = Field(..., description="User prompt or operational query.")
    target_agent: Optional[str] = None
    required_permissions: List[ToolPermission] = Field(default_factory=list)
    budget: ExecutionBudget = Field(default_factory=ExecutionBudget)
    use_cache: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_agent_request(self) -> AgentRequest:
        return AgentRequest(
            request_id=self.request_id,
            user_id=self.user_id,
            user_role=self.user_role,
            session_id=self.session_id,
            conversation_id=self.conversation_id,
            message=self.message,
            use_cache=self.use_cache,
            metadata=self.metadata
        )


class HarnessValidationResult(BaseModel):
    is_valid: bool = True
    grounding_valid: bool = True
    citations_valid: bool = True
    conflicts_detected: bool = False
    secrets_sanitized: bool = True
    errors: List[str] = Field(default_factory=list)
    sanitized_response: Optional[str] = None


class HarnessResponse(BaseModel):
    request_id: str
    session_id: str
    conversation_id: Optional[str] = None
    status: ExecutionStatus = ExecutionStatus.COMPLETED
    decision: HarnessPolicyDecision = HarnessPolicyDecision.ALLOW
    response: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: str = "high"
    query_type: str = "general"
    grounded: bool = True
    execution_time_ms: float = 0.0
    retry_count: int = 0
    version_info: Dict[str, str] = Field(default_factory=lambda: {
        "harness_version": "1.0.0",
        "orchestrator_version": "1.0.0",
        "architecture": "PRODUCTION_AI_HARNESS"
    })
    validation: Optional[HarnessValidationResult] = None
    error: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
