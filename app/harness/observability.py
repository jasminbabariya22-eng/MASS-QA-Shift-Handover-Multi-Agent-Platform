from typing import Dict, Any, Optional
import time
import logfire


class HarnessTelemetry:
    """
    Observability and latency tracing for the AI Harness layer.
    Emits structured OpenTelemetry metrics and Logfire spans.
    """

    def trace_execution(
        self,
        request_id: str,
        user_id: str,
        user_role: str,
        intent: str,
        agent_id: str,
        total_latency_ms: float,
        validation_status: str,
        cache_hit: bool = False,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Record structured telemetry event.
        """
        metric = {
            "request_id": request_id,
            "user_id": user_id,
            "user_role": user_role,
            "intent": intent,
            "agent_id": agent_id,
            "total_latency_ms": total_latency_ms,
            "validation_status": validation_status,
            "cache_hit": cache_hit,
            "retry_count": retry_count
        }

        logfire.info(
            f"[Telemetry] req_id={request_id} agent={agent_id} "
            f"latency={total_latency_ms:.2f}ms validation={validation_status} cached={cache_hit}"
        )
        return metric


# Global Telemetry Singleton
harness_telemetry = HarnessTelemetry()
