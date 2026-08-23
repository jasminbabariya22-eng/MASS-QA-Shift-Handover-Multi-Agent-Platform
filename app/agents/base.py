from abc import ABC, abstractmethod
from typing import List, Dict, Any, Generator, Optional

from app.agents.contracts import AgentRequest, RequestContext, AgentResult, AgentContext, AgentResponse


class BaseAgent(ABC):
    """
    Abstract Base Class for all agents registered with the Agent Orchestrator.
    Provides a standardized contract for synchronous and streaming execution.
    """

    agent_id: str
    name: str
    description: str
    capabilities: List[str]
    supports_streaming: bool = True

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        capabilities: List[str],
        supports_streaming: bool = True
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.capabilities = capabilities
        self.supports_streaming = supports_streaming

    @abstractmethod
    def execute(
        self,
        request: AgentRequest,
        context: RequestContext
    ) -> AgentResult:
        """
        Execute synchronous task and return a normalized AgentResult.
        """
        pass

    def stream(
        self,
        request: AgentRequest,
        context: RequestContext
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Execute streaming task yielding token/citation events.
        Default implementation yields the synchronous execute() result.
        """
        result = self.execute(request, context)
        yield {"type": "token", "content": result.response}
        if result.citations:
            yield {"type": "citations", "citations": result.citations}
        yield {
            "type": "done",
            "request_id": result.request_id,
            "metadata": result.metadata
        }

    def health_check(self) -> Dict[str, Any]:
        """
        Perform a liveness/readiness health check for the agent.
        """
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": "HEALTHY",
            "capabilities": self.capabilities,
            "supports_streaming": self.supports_streaming
        }

    def get_info(self) -> Dict[str, Any]:
        """
        Return metadata information about the agent.
        """
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "supports_streaming": self.supports_streaming
        }

    def delegate(
        self,
        target_agent_id: str,
        message: str,
        context: RequestContext,
        task_type: str = "A2A_DELEGATION",
        payload: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        """
        Standard Agent-to-Agent (A2A) task delegation helper.
        Dispatches typed subtasks to registered partner agents while preserving execution context.
        """
        from app.agents.registry import agent_registry
        target_agent = agent_registry.get(target_agent_id)
        if target_agent is None:
            raise ValueError(f"A2A delegation target '{target_agent_id}' not found in registry.")

        delegated_req = AgentRequest(
            request_id=context.request_id,
            user_id=context.user_id,
            user_role=context.user_role,
            session_id=context.session_id,
            conversation_id=context.conversation_id,
            message=message,
            metadata={
                **(payload or {}),
                "a2a_source": self.agent_id,
                "a2a_target": target_agent_id,
                "a2a_task_type": task_type
            }
        )

        delegated_ctx = RequestContext(
            request_id=context.request_id,
            user_id=context.user_id,
            user_role=context.user_role,
            session_id=context.session_id,
            conversation_id=context.conversation_id,
            current_agent=target_agent_id,
            previous_agent=self.agent_id,
            parent_task_id=context.request_id,
            metadata={"is_a2a_delegation": True, "a2a_source": self.agent_id}
        )

        return target_agent.execute(delegated_req, delegated_ctx)
