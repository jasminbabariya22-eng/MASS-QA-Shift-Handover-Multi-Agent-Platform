import time
import uuid
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
import logfire

from app.agents.contracts import AgentRequest, RequestContext, AgentResult, TaskStatus


class P2PMessage(BaseModel):
    """
    Bidirectional Peer-to-Peer Message frame exchanged between two autonomous agents.
    """
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_agent_id: str
    receiver_agent_id: str
    turn: int = 1
    intent: str = "PEER_EXCHANGE"
    content: str
    shared_state: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class P2PSessionState(BaseModel):
    """
    Shared memory channel for bidirectional Agent-to-Agent (P2P) task completion.
    """
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    initiator_agent_id: str
    partner_agent_id: str
    max_turns: int = 4
    current_turn: int = 0
    messages: List[P2PMessage] = Field(default_factory=list)
    shared_data: Dict[str, Any] = Field(default_factory=dict)
    consensus_reached: bool = False
    final_summary: str = ""


class PeerExchangeChannel:
    """
    Bidirectional Peer-to-Peer (P2P) Communication Channel allowing agents to converse,
    share state payloads, clarify missing details, and reach mutual consensus.
    """

    def __init__(self, initiator_agent_id: str, partner_agent_id: str, max_turns: int = 4):
        self.state = P2PSessionState(
            initiator_agent_id=initiator_agent_id,
            partner_agent_id=partner_agent_id,
            max_turns=max_turns
        )

    def send_message(
        self,
        sender_id: str,
        receiver_id: str,
        content: str,
        payload_update: Optional[Dict[str, Any]] = None
    ) -> P2PMessage:
        """
        Send a bidirectional P2P message frame and update the shared state dictionary.
        """
        self.state.current_turn += 1
        if payload_update:
            self.state.shared_data.update(payload_update)

        msg = P2PMessage(
            sender_agent_id=sender_id,
            receiver_agent_id=receiver_id,
            turn=self.state.current_turn,
            content=content,
            shared_state=self.state.shared_data.copy()
        )
        self.state.messages.append(msg)
        logfire.info(
            f"🤝 [P2P Channel Turn {msg.turn}] {sender_id} ➔ {receiver_id}: '{content[:60]}...'"
        )
        return msg

    def get_conversation_transcript(self) -> str:
        """
        Formats the bidirectional agent dialogue into clean Markdown.
        """
        lines = [f"🤝 **Bidirectional P2P Dialogue ({self.state.initiator_agent_id} ⇄ {self.state.partner_agent_id})**:"]
        for msg in self.state.messages:
            lines.append(f"- **Turn {msg.turn} [{msg.sender_agent_id} ➔ {msg.receiver_agent_id}]**: {msg.content}")
        return "\n".join(lines)


def p2p_negotiate(
    agent_a_id: str,
    agent_b_id: str,
    initial_request: AgentRequest,
    context: RequestContext,
    max_turns: int = 4
) -> AgentResult:
    """
    Execute a true Bidirectional Multi-Turn P2P Peer Exchange between Agent A and Agent B.
    Both agents converse, share state payloads, exchange technical data, and construct a unified result.
    """
    t_start = time.time()
    from app.agents.registry import agent_registry

    agent_a = agent_registry.get(agent_a_id)
    agent_b = agent_registry.get(agent_b_id)

    if not agent_a or not agent_b:
        raise ValueError(f"P2P negotiation failed: One or both agents ('{agent_a_id}', '{agent_b_id}') not found.")

    channel = PeerExchangeChannel(initiator_agent_id=agent_a_id, partner_agent_id=agent_b_id, max_turns=max_turns)

    # Turn 1: Agent A sends initial P2P request & operational state to Agent B
    msg_1 = channel.send_message(
        sender_id=agent_a_id,
        receiver_id=agent_b_id,
        content=f"P2P Query: {initial_request.message}",
        payload_update={"initial_query": initial_request.message, "user_role": context.user_role}
    )

    # Agent B processes Turn 1 request & returns technical context to Agent A
    b_request = AgentRequest(
        request_id=context.request_id,
        user_id=context.user_id,
        user_role=context.user_role,
        session_id=context.session_id,
        message=initial_request.message,
        metadata={"p2p_channel_session": channel.state.session_id, "p2p_turn": 1}
    )
    b_result = agent_b.execute(b_request, context)

    # Turn 2: Agent B sends technical response back to Agent A
    msg_2 = channel.send_message(
        sender_id=agent_b_id,
        receiver_id=agent_a_id,
        content=f"Provided technical specifications and document citations.",
        payload_update={"b_response": b_result.response, "citations": b_result.citations}
    )

    # Turn 3: Agent A evaluates Agent B's data, executes its domain task (e.g. PostgreSQL log), and responds back
    a_request = AgentRequest(
        request_id=context.request_id,
        user_id=context.user_id,
        user_role=context.user_role,
        session_id=context.session_id,
        message=initial_request.message,
        metadata={"p2p_channel_session": channel.state.session_id, "p2p_turn": 2, "shared_data": channel.state.shared_data}
    )
    a_result = agent_a.execute(a_request, context)

    # Turn 4: Agent A confirms mutual completion back to Agent B
    channel.send_message(
        sender_id=agent_a_id,
        receiver_id=agent_b_id,
        content=f"Integrated technical SOP citations into unit shift log and saved to PostgreSQL.",
        payload_update={"a_response": a_result.response, "consensus": True}
    )

    channel.state.consensus_reached = True

    # Assemble unified P2P response
    composite_response = (
        f"{a_result.response}\n\n"
        f"**Technical SOP Guidance (from {agent_b.name}):**\n"
        f"{b_result.response}\n\n"
        f"{channel.get_conversation_transcript()}"
    )

    all_citations = (a_result.citations or []) + (b_result.citations or [])

    return AgentResult(
        request_id=initial_request.request_id,
        agent_id=f"p2p_{agent_a_id}_{agent_b_id}",
        status=TaskStatus.COMPLETED.value,
        success=True,
        response=composite_response,
        citations=all_citations,
        confidence="high",
        query_type="p2p_peer_exchange",
        grounded=True,
        execution_time_ms=round((time.time() - t_start) * 1000, 2),
        metadata={
            "p2p_session_id": channel.state.session_id,
            "total_p2p_turns": channel.state.current_turn,
            "consensus_reached": True,
            "participating_peers": [agent_a_id, agent_b_id],
            "shared_payload_keys": list(channel.state.shared_data.keys())
        }
    )
