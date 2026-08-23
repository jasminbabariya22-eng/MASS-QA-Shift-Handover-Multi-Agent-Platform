from typing import Dict, Optional, List, Any
import logfire

from app.agents.base import BaseAgent


class AgentRegistry:
    """
    Central repository for registering, retrieving, and inspecting active agents.
    Configuration/registration-driven design enables dynamic agent discovery.
    """

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """
        Register an agent instance in the registry.
        """
        if not isinstance(agent, BaseAgent):
            raise TypeError(f"Agent must inherit from BaseAgent, got {type(agent)}")
        self._agents[agent.agent_id] = agent
        logfire.info(f"Registered agent: '{agent.agent_id}' ({agent.name}) with capabilities: {agent.capabilities}")

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        """
        Retrieve a registered agent by ID.
        """
        return self._agents.get(agent_id)

    def has(self, agent_id: str) -> bool:
        """
        Check if an agent is registered.
        """
        return agent_id in self._agents

    def list_agents(self) -> List[Dict[str, Any]]:
        """
        List all registered agents and their metadata.
        """
        return [agent.get_info() for agent in self._agents.values()]

    def unregister(self, agent_id: str) -> bool:
        """
        Unregister an agent by ID.
        """
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False


# Global Agent Registry Singleton
agent_registry = AgentRegistry()
