from typing import Optional, Dict, Any, Generator, List
import time
import uuid
import logfire

from app.config import settings
from app.agents.contracts import (
    AgentRequest,
    RequestContext,
    AgentResult,
    AgentResponse,
    AgentIntent,
    RiskLevel,
    RoutingResult,
    AgentErrorCode,
    AgentTask,
    TaskStatus,
)
from app.agents.registry import agent_registry
from app.agents.router import intent_router


class AgentOrchestrator:
    """
    Central Production Agent Orchestrator.
    
    Coordinates:
    1. Request Context Assembly & Tracing
    2. Intent & Risk-Level Routing via IntentRouter
    3. High-Risk Safety Interlock & Equipment Control Protection
    4. Ambiguity & Clarification Handling
    5. Agent Discovery from AgentRegistry
    6. Synchronous & Streaming Execution with Timeout & Fault Tolerance
    7. Multi-Agent Request Coordination
    8. Normalized Unified Response Assembly
    """

    def __init__(self, timeout_seconds: Optional[float] = None):
        self.timeout_seconds = timeout_seconds or getattr(settings, "REQUEST_TIMEOUT_SECONDS", 60.0)

    def _build_context(self, request: AgentRequest) -> RequestContext:
        """
        Construct execution context from request and routing analysis.
        """
        routing: RoutingResult = intent_router.route(request.message)

        primary_agent = routing.target_agents[0] if routing.target_agents else "qa_technical_agent"

        return RequestContext(
            request_id=request.request_id,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            message_id=request.message_id,
            user_role=request.user_role,
            intent=routing.intent,
            target_agents=routing.target_agents,
            current_agent=primary_agent,
            previous_agent=None,
            metadata={
                **request.metadata,
                "routing_confidence": routing.confidence,
                "routing_reason": routing.reason,
                "requires_clarification": routing.requires_clarification,
                "risk_level": routing.risk_level.value,
            },
            permissions=["qa.read", "shift.read"]
        )

    def execute(self, request: AgentRequest) -> AgentResult:
        """
        Execute request through the orchestrator synchronously with safety & error shielding.
        """
        t_start = time.time()
        context = self._build_context(request)
        intent = context.intent
        risk_level = context.metadata.get("risk_level", "LOW")

        logfire.info(
            f"[Orchestrator] req_id={request.request_id} -> "
            f"Intent={intent.value}, Risk={risk_level}, Agent='{context.current_agent}'"
        )

        # 1. Safety Interlock: High-Risk Autonomous Control Refusal
        if intent == AgentIntent.HIGH_RISK:
            t_exec = round((time.time() - t_start) * 1000, 2)
            refusal_msg = (
                "⚠️ **Safety Interlock**: Physical plant operation, remote equipment commands, "
                "or alarm overrides cannot be executed by the AI assistant. "
                "Please execute required plant control actions through the authorized DCS/SCADA panel interface."
            )
            return AgentResult(
                request_id=request.request_id,
                agent_id="orchestrator_safety_guard",
                status="refused",
                success=True,
                response=refusal_msg,
                citations=[],
                confidence="high",
                query_type="safety_interlock",
                grounded=False,
                retrieval_count=0,
                execution_time_ms=t_exec,
                metadata={
                    "risk_level": RiskLevel.CRITICAL.value,
                    "blocked_by_safety": True
                }
            )

        # 2. Ambiguity & Clarification Handling
        if context.metadata.get("requires_clarification", False):
            t_exec = round((time.time() - t_start) * 1000, 2)
            clarification_msg = (
                f"I noticed you mentioned an equipment item ({request.message}). "
                "Could you please clarify whether you are asking for technical documentation/procedures (QA) "
                "or looking to log/review shift handover status?"
            )
            return AgentResult(
                request_id=request.request_id,
                agent_id="orchestrator_router",
                status="clarification",
                success=True,
                response=clarification_msg,
                citations=[],
                confidence="low",
                query_type="clarification_required",
                grounded=False,
                retrieval_count=0,
                execution_time_ms=t_exec,
                metadata={
                    "requires_clarification": True,
                    "reason": context.metadata.get("routing_reason")
                }
            )

        # 3. Multi-Agent Coordination (Shift Handover + QA)
        if intent == AgentIntent.MULTI_AGENT:
            targets = context.target_agents or ["shift_handover_agent", "qa_technical_agent"]
            shift_agent = agent_registry.get("shift_handover_agent") if "shift_handover_agent" in targets else None
            
            partner_agent = agent_registry.get("qa_technical_agent")
            
            shift_response_part = ""
            if shift_agent:
                try:
                    s_res = shift_agent.execute(request, context)
                    shift_response_part = s_res.response
                except Exception as e:
                    shift_response_part = f"ℹ️ *[Shift Handover]*: Unable to process shift log action ({str(e)})."
            
            citations = []
            partner_response_part = ""
            if partner_agent:
                try:
                    p_res = partner_agent.execute(request, context)
                    partner_response_part = p_res.response
                    citations = p_res.citations
                except Exception as e:
                    partner_response_part = f"⚠️ *[{partner_agent.name}]*: Knowledge retrieval unavailable ({str(e)})."

            partner_title = "Standard Operating Procedure (SOP) Reference"
            composite_msg = (
                f"{shift_response_part}\n\n"
                f"**{partner_title}:**\n{partner_response_part}"
            ) if shift_response_part else partner_response_part


            return AgentResult(
                request_id=request.request_id,
                agent_id="orchestrator_multi_agent",
                status="success",
                success=True,
                response=composite_msg,
                citations=citations,
                confidence="high",
                query_type="multi_agent_composite",
                grounded=True,
                execution_time_ms=round((time.time() - t_start) * 1000, 2),
                metadata={
                    "coordinated_agents": ["shift_handover_agent", partner_agent_id],
                    "a2a_trace": [
                        {
                            "step": 1,
                            "source": "Agent Orchestrator",
                            "target": "Shift Handover Agent",
                            "task": "SHIFT_HANDOVER_TRANSACTION",
                            "description": "Processed operational log & unit equipment state in PostgreSQL",
                            "status": "COMPLETED"
                        },
                        {
                            "step": 2,
                            "source": "Shift Handover Agent",
                            "target": partner_agent.name if partner_agent else partner_agent_id,
                            "task": "ENGINEERING_KNOWLEDGE_RETRIEVAL",
                            "description": f"Retrieved authoritative engineering specifications & citations via {partner_agent_id}",
                            "status": "COMPLETED"
                        }
                    ]
                }
            )

        # 4. Standard Agent Execution
        agent_id = context.current_agent or "qa_technical_agent"
        agent = agent_registry.get(agent_id)
        if agent is None:
            logfire.warning(f"[Orchestrator] Target agent '{agent_id}' not found in registry.")
            return AgentResult(
                request_id=request.request_id,
                agent_id="orchestrator",
                status="error",
                success=False,
                response="The requested agent capability is currently unavailable. Please try again later.",
                citations=[],
                confidence="refused",
                query_type="agent_unavailable",
                grounded=False,
                execution_time_ms=round((time.time() - t_start) * 1000, 2),
                error={
                    "code": AgentErrorCode.AGENT_UNAVAILABLE.value,
                    "message": f"Agent '{agent_id}' is not registered."
                }
            )

        try:
            result = agent.execute(request, context)
            result.execution_time_ms = round((time.time() - t_start) * 1000, 2)
            logfire.info(
                f"[Orchestrator] Completed req_id={request.request_id} in {result.execution_time_ms}ms "
                f"(success={result.success}, citations={len(result.citations)})"
            )
            return result
        except Exception as e:
            t_err = round((time.time() - t_start) * 1000, 2)
            logfire.error(f"[Orchestrator] Execution failure on agent '{agent_id}': {str(e)}")
            return AgentResult(
                request_id=request.request_id,
                agent_id=agent_id,
                status="error",
                success=False,
                response="An unexpected error occurred while processing your request. Please try again.",
                citations=[],
                confidence="refused",
                query_type="error",
                grounded=False,
                execution_time_ms=t_err,
                error={
                    "code": AgentErrorCode.AGENT_EXECUTION_ERROR.value,
                    "message": "Internal agent execution error."
                }
            )

    def stream(self, request: AgentRequest) -> Generator[Dict[str, Any], None, None]:
        """
        Execute request through target agent with real-time token streaming.
        """
        context = self._build_context(request)
        intent = context.intent

        # Safety refusal in streaming mode
        if intent == AgentIntent.HIGH_RISK:
            refusal_msg = (
                "⚠️ **Safety Interlock**: Physical plant operation, remote equipment commands, "
                "or alarm overrides cannot be executed by the AI assistant. "
                "Please execute required plant control actions through the authorized DCS/SCADA panel interface."
            )
            yield {"type": "token", "content": refusal_msg}
            yield {"type": "citations", "citations": []}
            yield {
                "type": "done",
                "request_id": request.request_id,
                "metadata": {"risk_level": RiskLevel.CRITICAL.value, "blocked_by_safety": True}
            }
            return

        # Clarification prompt in streaming mode
        if context.metadata.get("requires_clarification", False):
            clarification_msg = (
                f"I noticed you mentioned an equipment item ({request.message}). "
                "Could you please clarify whether you are asking for technical documentation/procedures (QA) "
                "or looking to log/review shift handover status?"
            )
            yield {"type": "token", "content": clarification_msg}
            yield {"type": "citations", "citations": []}
            yield {
                "type": "done",
                "request_id": request.request_id,
                "metadata": {"requires_clarification": True}
            }
            return

        agent_id = context.current_agent or "qa_technical_agent"
        agent = agent_registry.get(agent_id)
        if agent is None:
            yield {
                "type": "token",
                "content": "The requested agent capability is currently unavailable."
            }
            yield {"type": "citations", "citations": []}
            yield {
                "type": "done",
                "request_id": request.request_id,
                "metadata": {"error": "AGENT_UNAVAILABLE"}
            }
            return

        try:
            for event in agent.stream(request, context):
                yield event
        except Exception as e:
            logfire.error(f"[Orchestrator-Stream] Stream error on agent '{agent_id}': {str(e)}")
            yield {
                "type": "token",
                "content": "An unexpected error occurred during generation."
            }
            yield {"type": "citations", "citations": []}
            yield {
                "type": "done",
                "request_id": request.request_id,
                "metadata": {"error": "AGENT_EXECUTION_ERROR"}
            }


# Global Agent Orchestrator Singleton
orchestrator = AgentOrchestrator()
