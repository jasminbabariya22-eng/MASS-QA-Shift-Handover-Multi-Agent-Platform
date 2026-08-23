from app.agents.base import BaseAgent
from app.agents.contracts import AgentRequest, RequestContext, AgentResult
from app.agents.registry import agent_registry
from app.agents.loop.agent import LoopEngineeringAgent, loop_engineering_agent

# Export LoopEngineeringAgent for full compatibility
__all__ = ["LoopEngineeringAgent", "loop_engineering_agent"]

# Ensure registered in registry singleton
if not agent_registry.has("loop_engineering_agent"):
    agent_registry.register(loop_engineering_agent)
