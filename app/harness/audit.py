from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logfire

from app.harness.contracts import HarnessRequest, HarnessResponse, HarnessPolicyDecision


class HarnessAuditRecorder:
    """
    Audit logging boundary capturing all AI Harness decisions, RBAC checks, and execution metrics.
    """

    def record_decision(
        self,
        request: HarnessRequest,
        decision: HarnessPolicyDecision,
        reason: Optional[str] = None,
        agent_id: Optional[str] = None,
        duration_ms: float = 0.0,
        error_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Record a structured audit log entry for a harness policy or execution decision.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request.request_id,
            "session_id": request.session_id,
            "user_id": request.user_id,
            "user_role": request.user_role,
            "decision": decision.value,
            "reason": reason,
            "agent_id": agent_id or request.target_agent,
            "duration_ms": duration_ms,
            "error_code": error_code,
            "metadata": metadata or {}
        }

        if decision == HarnessPolicyDecision.DENY:
            logfire.warning(f"[HarnessAudit:DENY] req_id={request.request_id} user={request.user_id} reason={reason}")
        else:
            logfire.info(f"[HarnessAudit:{decision.value}] req_id={request.request_id} agent={entry['agent_id']} ({duration_ms:.2f}ms)")

        return entry


# Global Audit Singleton
audit_recorder = HarnessAuditRecorder()
