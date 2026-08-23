from typing import Dict, Any, Generator

from app.agents.base import BaseAgent
from app.agents.contracts import AgentRequest, RequestContext, AgentResult
from app.agents.registry import agent_registry
from app.agents.shift.agent import ShiftHandoverAgent

# Export ShiftHandoverAgent for full compatibility
__all__ = ["ShiftHandoverAgent", "shift_handover_agent"]

# Instantiate and register production agent singleton in registry
shift_handover_agent = ShiftHandoverAgent()
agent_registry.register(shift_handover_agent)
