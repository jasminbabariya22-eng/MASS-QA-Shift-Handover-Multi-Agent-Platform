import time
import json
from typing import Optional, Dict, Any, Generator, List
import logfire

from app.agents.contracts import (
    AgentRequest,
    RequestContext,
    AgentResult,
    AgentIntent,
    AgentErrorCode
)
from app.agents.orchestrator import orchestrator, AgentOrchestrator
from app.agents.registry import agent_registry
from app.harness.contracts import (
    HarnessRequest,
    HarnessResponse,
    HarnessPolicyDecision,
    ExecutionStatus,
    HarnessErrorClassification,
    ToolPermission,
    HarnessValidationResult
)
from app.harness.permissions import permission_manager
from app.harness.safety import safety_policy
from app.harness.budget import ExecutionBudgetTracker, BudgetExceededError, AgentLoopDetectedError, AgentDepthExceededError
from app.harness.validator import output_validator
from app.harness.audit import audit_recorder
from app.harness.observability import harness_telemetry


class AIHarness:
    """
    Production AI Harness.
    Deterministic execution, authorization, safety, budget, and validation layer wrapping the Agent Orchestrator.
    """

    VERSION = "1.0.0"

    def __init__(self, orchestrator_instance: Optional[AgentOrchestrator] = None):
        self.orchestrator = orchestrator_instance or orchestrator
        self.permission_manager = permission_manager
        self.safety_policy = safety_policy
        self.validator = output_validator
        self.audit = audit_recorder
        self.telemetry = harness_telemetry

    def execute(self, request: HarnessRequest) -> HarnessResponse:
        """
        Execute request through the deterministic Harness governance pipeline:
        Auth -> RBAC -> Safety Gate -> Budget -> Orchestrator -> Output Validation -> Audit -> Response
        """
        t_start = time.time()
        budget_tracker = ExecutionBudgetTracker(request.budget)

        # 1. Safety Policy Gate (Pre-Execution Interlock)
        safety_decision, safety_code, safety_msg = self.safety_policy.evaluate(request.message)
        if safety_decision == HarnessPolicyDecision.DENY:
            t_ms = round((time.time() - t_start) * 1000, 2)
            self.audit.record_decision(
                request=request,
                decision=HarnessPolicyDecision.DENY,
                reason=safety_code,
                duration_ms=t_ms,
                error_code="PHYSICAL_CONTROL_PROHIBITED"
            )
            return HarnessResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                conversation_id=request.conversation_id,
                status=ExecutionStatus.DENIED,
                decision=HarnessPolicyDecision.DENY,
                response=safety_msg,
                citations=[],
                confidence="refused",
                query_type="safety_interlock",
                grounded=False,
                execution_time_ms=t_ms,
                error={"code": "PHYSICAL_CONTROL_PROHIBITED", "message": "Prohibited physical equipment operation."}
            )

        # 2. RBAC & Required Tool Permission Check
        for perm in request.required_permissions:
            if not self.permission_manager.verify_role_authorization(request.user_role, perm):
                t_ms = round((time.time() - t_start) * 1000, 2)
                deny_msg = f"⛔ **Access Denied**: Role `{request.user_role}` is not authorized to execute permission `{perm.value}`."
                self.audit.record_decision(
                    request=request,
                    decision=HarnessPolicyDecision.DENY,
                    reason=f"ROLE_NOT_AUTHORIZED:{perm.value}",
                    duration_ms=t_ms,
                    error_code="AUTHORIZATION_ERROR"
                )
                return HarnessResponse(
                    request_id=request.request_id,
                    session_id=request.session_id,
                    conversation_id=request.conversation_id,
                    status=ExecutionStatus.DENIED,
                    decision=HarnessPolicyDecision.DENY,
                    response=deny_msg,
                    citations=[],
                    confidence="refused",
                    query_type="authorization_denied",
                    grounded=False,
                    execution_time_ms=t_ms,
                    error={"code": "AUTHORIZATION_ERROR", "message": f"Role not authorized for {perm.value}"}
                )

        # 3. Human Approval Gate Check (if tagged)
        if request.metadata.get("requires_human_approval"):
            t_ms = round((time.time() - t_start) * 1000, 2)
            approval_msg = "⏳ **Action Pending**: This high-impact operation requires human supervisor approval before execution."
            self.audit.record_decision(
                request=request,
                decision=HarnessPolicyDecision.REQUIRES_HUMAN_APPROVAL,
                reason="HIGH_IMPACT_OPERATION",
                duration_ms=t_ms
            )
            return HarnessResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                conversation_id=request.conversation_id,
                status=ExecutionStatus.COMPLETED,
                decision=HarnessPolicyDecision.REQUIRES_HUMAN_APPROVAL,
                response=approval_msg,
                citations=[],
                confidence="pending",
                query_type="human_approval_gate",
                grounded=False,
                execution_time_ms=t_ms,
                metadata={"requires_human_approval": True}
            )

        # 4. Convert to AgentRequest and Dispatch to Orchestrator (with bounded retry)
        agent_req = request.to_agent_request()
        agent_res: Optional[AgentResult] = None
        retries = 0
        last_error = None

        while retries <= request.budget.max_retries:
            try:
                # Record agent call in budget tracker (detects recursion & loop cycles)
                budget_tracker.record_agent_invocation(request.target_agent or "orchestrator")
                agent_res = self.orchestrator.execute(agent_req)
                break
            except (AgentLoopDetectedError, AgentDepthExceededError, BudgetExceededError) as bex:
                # Permanent budget violations - do NOT retry
                logfire.error(f"[HarnessBudget] Execution stopped: {bex}")
                t_ms = round((time.time() - t_start) * 1000, 2)
                return HarnessResponse(
                    request_id=request.request_id,
                    session_id=request.session_id,
                    conversation_id=request.conversation_id,
                    status=ExecutionStatus.ERROR,
                    decision=HarnessPolicyDecision.DENY,
                    response=f"⚠️ Execution halted by AI Harness: {str(bex)}",
                    citations=[],
                    query_type="budget_exceeded",
                    grounded=False,
                    execution_time_ms=t_ms,
                    error={"code": getattr(bex, "code", "BUDGET_EXCEEDED"), "message": str(bex)}
                )
            except Exception as ex:
                last_error = ex
                retries += 1
                # Check error classification: only retry TRANSIENT errors
                err_class = self._classify_error(ex)
                if err_class != HarnessErrorClassification.TRANSIENT or retries > request.budget.max_retries:
                    logfire.error(f"[Harness] Permanent execution error ({err_class.value}): {ex}")
                    t_ms = round((time.time() - t_start) * 1000, 2)
                    return HarnessResponse(
                        request_id=request.request_id,
                        session_id=request.session_id,
                        conversation_id=request.conversation_id,
                        status=ExecutionStatus.ERROR,
                        decision=HarnessPolicyDecision.DENY,
                        response=f"An error occurred during agent execution: {str(ex)}",
                        citations=[],
                        query_type="execution_error",
                        grounded=False,
                        execution_time_ms=t_ms,
                        retry_count=retries - 1,
                        error={"code": "AGENT_EXECUTION_ERROR", "message": str(ex)}
                    )
                logfire.warning(f"[Harness] Transient error encountered, retrying ({retries}/{request.budget.max_retries})...")
                time.sleep(0.1 * retries)

        if not agent_res:
            t_ms = round((time.time() - t_start) * 1000, 2)
            return HarnessResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                status=ExecutionStatus.ERROR,
                decision=HarnessPolicyDecision.DENY,
                response="Failed to obtain response from Agent Orchestrator.",
                execution_time_ms=t_ms,
                error={"code": "NO_RESPONSE", "message": "No response returned"}
            )

        t_ms = round((time.time() - t_start) * 1000, 2)

        # 5. Output Validation Gate (Grounding, Citations, Conflicts, Secrets)
        val_result: HarnessValidationResult = self.validator.validate(
            response_text=agent_res.response,
            citations=agent_res.citations,
            query_type=agent_res.query_type or "general",
            metadata=agent_res.metadata,
            is_error=not agent_res.success
        )

        final_response_text = val_result.sanitized_response or agent_res.response

        # 6. Record Audit & Telemetry
        self.audit.record_decision(
            request=request,
            decision=HarnessPolicyDecision.ALLOW,
            agent_id=agent_res.agent_id,
            duration_ms=t_ms,
            metadata={"citations_count": len(agent_res.citations), "grounded": agent_res.grounded}
        )
        self.telemetry.trace_execution(
            request_id=request.request_id,
            user_id=request.user_id,
            user_role=request.user_role,
            intent=agent_res.query_type or "general",
            agent_id=agent_res.agent_id,
            total_latency_ms=t_ms,
            validation_status="PASSED" if val_result.is_valid else "WARNING",
            cache_hit=agent_res.metadata.get("cached", False),
            retry_count=retries
        )

        # 7. Assemble Validated Harness Response with Version Metadata
        return HarnessResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            conversation_id=request.conversation_id,
            status=ExecutionStatus.COMPLETED if agent_res.success else ExecutionStatus.ERROR,
            decision=HarnessPolicyDecision.ALLOW,
            response=final_response_text,
            citations=agent_res.citations,
            confidence=agent_res.confidence,
            query_type=agent_res.query_type or "general",
            grounded=agent_res.grounded,
            execution_time_ms=t_ms,
            retry_count=retries,
            version_info={
                "harness_version": self.VERSION,
                "orchestrator_version": "1.0.0",
                "agent_id": agent_res.agent_id,
                "agent_version": "1.0.0"
            },
            validation=val_result,
            error=agent_res.error,
            metadata=agent_res.metadata
        )

    def stream(self, request: HarnessRequest) -> Generator[Dict[str, Any], None, None]:
        """
        Streaming execution through Harness governance. Safety and RBAC checks run BEFORE stream opens.
        """
        # 1. Pre-stream Safety Gate
        safety_decision, safety_code, safety_msg = self.safety_policy.evaluate(request.message)
        if safety_decision == HarnessPolicyDecision.DENY:
            yield {"type": "error", "code": "PHYSICAL_CONTROL_PROHIBITED", "message": safety_msg}
            yield {"type": "done", "request_id": request.request_id, "status": "DENIED"}
            return

        # 2. Pre-stream RBAC Gate
        for perm in request.required_permissions:
            if not self.permission_manager.verify_role_authorization(request.user_role, perm):
                yield {"type": "error", "code": "AUTHORIZATION_ERROR", "message": f"Role '{request.user_role}' not authorized."}
                yield {"type": "done", "request_id": request.request_id, "status": "DENIED"}
                return

        # 3. Delegate to Orchestrator Stream
        agent_req = request.to_agent_request()
        for event in self.orchestrator.stream(agent_req):
            if event.get("type") == "token":
                # Secret sanitization on streamed tokens
                sanitized_token, _ = self.validator.sanitize_secrets(event.get("content", ""))
                event["content"] = sanitized_token
            yield event

    def health_check(self) -> Dict[str, Any]:
        """
        Check health and readiness across the agent foundation.
        """
        agents = agent_registry.list_agents()
        agent_statuses = {}
        for ag in agents:
            ag_id = ag["agent_id"]
            agent_instance = agent_registry.get(ag_id)
            if agent_instance:
                try:
                    check = agent_instance.health_check()
                    agent_statuses[ag_id] = check.get("status", "READY")
                except Exception:
                    agent_statuses[ag_id] = "DEGRADED"
            else:
                agent_statuses[ag_id] = "UNAVAILABLE"

        is_all_ready = all(s == "READY" for s in agent_statuses.values())

        return {
            "status": "READY" if is_all_ready else "DEGRADED",
            "harness_version": self.VERSION,
            "agent_count": len(agents),
            "agents": agent_statuses
        }

    def _classify_error(self, ex: Exception) -> HarnessErrorClassification:
        """Classify exceptions to determine retry eligibility."""
        msg = str(ex).lower()
        if "timeout" in msg or "timed out" in msg or "temporarily unavailable" in msg or "connection reset" in msg:
            return HarnessErrorClassification.TRANSIENT
        if "not authorized" in msg or "permission denied" in msg or "unauthorized" in msg:
            return HarnessErrorClassification.AUTHORIZATION
        if "safety" in msg or "prohibited" in msg or "trip" in msg:
            return HarnessErrorClassification.SAFETY
        if "not found" in msg:
            return HarnessErrorClassification.NOT_FOUND
        if "conflict" in msg or "concurrency" in msg:
            return HarnessErrorClassification.CONCURRENCY
        return HarnessErrorClassification.PERMANENT


# Global AI Harness Singleton
ai_harness = AIHarness()
