from app.agents.qa.adapter import QAAgentAdapter, QAAgent
from app.agents.registry import agent_registry

# Instantiate and register production QA agent adapter singleton
qa_agent = QAAgentAdapter()
agent_registry.register(qa_agent)

__all__ = ["QAAgentAdapter", "QAAgent", "qa_agent"]
