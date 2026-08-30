import pytest
import uuid
from typing import Dict, Any, Generator

from app.agents import (
    agent_registry,
    intent_router,
    orchestrator,
    AgentRequest,
    RequestContext,
    AgentResult,
    AgentErrorCode,
    AgentIntent,
)
from app.agents.shift import (
    ShiftHandoverAgent,
    ShiftCommand,
    ShiftCommandType,
    ShiftCommandExtractor,
    ShiftHandoverRole,
    ShiftHandoverAction,
    ShiftHandoverState,
    ShiftType,
    ShiftHandoverData,
    SafetyCriticalItem,
    ShiftHandover,
    ShiftHandoverTransitionResult,
    ShiftHandoverAuditEntry,
)
from app.repositories.shift_handover_repository import (
    ConcurrencyConflictError,
    ShiftHandoverNotFoundError,
    TerminalStateError,
)


# --- Mock Service & Test Helpers ---

class MockShiftHandoverService:
    """Mock service providing deterministic in-memory responses for fast agent testing without PostgreSQL."""

    def __init__(self):
        self.handovers = {}

    def create_handover(self, db, data, actor_id, actor_role, handover_id=None, request_id=None, session_id=None, **kwargs):
        hid = handover_id or str(uuid.uuid4())
        hnum = f"SHO-20260822-{data.unit_id.replace('-', '')}-1001"
        
        class FakeModel:
            def __init__(self, id, num, data, role):
                self.id = id
                self.handover_number = num
                self.unit_id = data.unit_id
                self.unit_name = data.unit_name
                self.shift_type = data.shift_type.value
                self.shift_date = data.shift_date
                self.state = "DRAFT"
                self.version = 1
                self.outgoing_operator_id = actor_id
                self.incoming_operator_id = data.incoming_operator_id
                self.supervisor_id = data.supervisor_id
                self.operational_summary = data.operational_summary
                self.notes = data.notes
                self.safety_items = []
                self.audit_trail = [
                    ShiftHandoverAuditEntry(
                        handover_id=id,
                        from_state=ShiftHandoverState.DRAFT,
                        to_state=ShiftHandoverState.DRAFT,
                        action=ShiftHandoverAction.CREATE,
                        actor_id=actor_id,
                        actor_role=actor_role
                    )
                ]
                self.is_terminal = False

        model = FakeModel(hid, hnum, data, actor_role)
        self.handovers[hid] = model
        self.handovers[hnum] = model
        
        res = ShiftHandoverTransitionResult(
            success=True,
            handover_id=hid,
            previous_state=ShiftHandoverState.DRAFT,
            current_state=ShiftHandoverState.DRAFT,
            action=ShiftHandoverAction.CREATE,
            actor_id=actor_id,
            actor_role=actor_role
        )
        return model, res

    def get_handover(self, db, handover_id):
        return self.handovers.get(handover_id)

    def list_handovers(self, db, unit_id=None, **kwargs):
        res = []
        for h in self.handovers.values():
            if h not in res:
                if not unit_id or h.unit_id == unit_id:
                    res.append(h)
        return res

    def update_handover(self, db, handover_id, expected_version, updates, actor_id, **kwargs):
        model = self.handovers.get(handover_id)
        if not model:
            raise ShiftHandoverNotFoundError("Not found")
        for k, v in updates.items():
            setattr(model, k, v)
        return model

    def add_safety_item(self, db, handover_id, category, equipment_tag, description, active=True):
        model = self.handovers.get(handover_id)
        if not model:
            raise ShiftHandoverNotFoundError("Not found")
        item = SafetyCriticalItem(
            category=category,
            equipment_tag=equipment_tag,
            description=description,
            active=active
        )
        model.safety_items.append(item)
        return item

    def acknowledge_safety_item(self, db, item_id, actor_id):
        for h in self.handovers.values():
            for it in h.safety_items:
                if it.item_id == item_id:
                    it.acknowledged_by_incoming = True
                    return it
        return None

    def get_audit_history(self, db, handover_id):
        model = self.handovers.get(handover_id)
        return model.audit_trail if model else []

    def transition_handover(self, db, handover_id, action, actor_id, actor_role, expected_version, reason=None, **kwargs):
        model = self.handovers.get(handover_id)
        if not model:
            raise ShiftHandoverNotFoundError(f"Handover {handover_id} not found")

        if model.is_terminal:
            raise TerminalStateError(f"Cannot modify terminal handover in state '{model.state}'")

        if expected_version != model.version:
            raise ConcurrencyConflictError(f"Version mismatch: {model.version} != {expected_version}")

        # Deterministic role check
        if action == ShiftHandoverAction.APPROVE and actor_role != ShiftHandoverRole.SHIFT_SUPERVISOR:
            return ShiftHandoverTransitionResult(
                success=False,
                handover_id=handover_id,
                previous_state=ShiftHandoverState(model.state),
                current_state=ShiftHandoverState(model.state),
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                validation_errors=["ROLE_UNAUTHORIZED"]
            )

        # Deterministic state check
        if action == ShiftHandoverAction.APPROVE and model.state == "DRAFT":
            return ShiftHandoverTransitionResult(
                success=False,
                handover_id=handover_id,
                previous_state=ShiftHandoverState.DRAFT,
                current_state=ShiftHandoverState.DRAFT,
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                validation_errors=["INVALID_STATE_ACTION"]
            )

        # Reason check
        if action in (ShiftHandoverAction.RETURN, ShiftHandoverAction.REJECT, ShiftHandoverAction.CANCEL) and not reason:
            return ShiftHandoverTransitionResult(
                success=False,
                handover_id=handover_id,
                previous_state=ShiftHandoverState(model.state),
                current_state=ShiftHandoverState(model.state),
                action=action,
                actor_id=actor_id,
                actor_role=actor_role,
                validation_errors=["MISSING_MANDATORY_REASON"]
            )

        # Apply transition
        prev = ShiftHandoverState(model.state)
        if action == ShiftHandoverAction.SUBMIT:
            model.state = "SUBMITTED"
        elif action == ShiftHandoverAction.APPROVE:
            model.state = "PENDING_ACKNOWLEDGEMENT"
        elif action == ShiftHandoverAction.RETURN:
            model.state = "RETURNED"
        elif action == ShiftHandoverAction.REJECT:
            model.state = "REJECTED"
            model.is_terminal = True
        elif action == ShiftHandoverAction.ACKNOWLEDGE:
            model.state = "COMPLETED"
            model.is_terminal = True
        elif action == ShiftHandoverAction.CANCEL:
            model.state = "CANCELLED"
            model.is_terminal = True

        model.version += 1
        return ShiftHandoverTransitionResult(
            success=True,
            handover_id=handover_id,
            previous_state=prev,
            current_state=ShiftHandoverState(model.state),
            action=action,
            actor_id=actor_id,
            actor_role=actor_role
        )


class MockSession:
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass
    def refresh(self, x): pass


@pytest.fixture
def mock_agent():
    mock_service = MockShiftHandoverService()
    extractor = ShiftCommandExtractor()
    agent = ShiftHandoverAgent(
        service=mock_service,
        extractor=extractor,
        session_factory=lambda: MockSession()
    )
    return agent, mock_service


# --- Step 7 Test Cases ---

def test_1_shift_agent_registration():
    """Test 1: Verify Shift Handover Agent is discoverable in the registry."""
    agent = agent_registry.get("shift_handover_agent")
    assert agent is not None
    assert agent.agent_id == "shift_handover_agent"
    assert "create_handover" in agent.capabilities
    assert agent.supports_streaming is True


def test_2_simple_create_request(mock_agent):
    """Test 2: Create a shift handover via natural language."""
    agent, service = mock_agent
    req = AgentRequest(message="Create a shift handover for Unit U-101", user_id="op_console_101", user_role="CONSOLE_OPERATOR")
    ctx = RequestContext(request_id=req.request_id, session_id=req.session_id, user_id=req.user_id, user_role=req.user_role)
    
    res = agent.execute(req, ctx)
    assert res.success is True
    assert "Created Shift Handover Draft" in res.response
    assert "U-101" in res.response
    assert "DRAFT" in res.response


def test_3_get_handover_request(mock_agent):
    """Test 3: Query current handover status."""
    agent, service = mock_agent
    req_create = AgentRequest(message="Create a handover for Unit CDU-101", user_id="op_1")
    ctx = RequestContext(request_id=req_create.request_id, session_id=req_create.session_id)
    agent.execute(req_create, ctx)

    req_get = AgentRequest(message="Show status for Unit CDU-101", user_id="op_1")
    res = agent.execute(req_get, ctx)
    assert res.success is True
    assert "Shift Handover Status" in res.response
    assert "CDU-101" in res.response


def test_4_list_handovers(mock_agent):
    """Test 4: List recent handovers."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit CDU-101", user_id="op_1")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    agent.execute(req_c, ctx)

    req = AgentRequest(message="List all pending handovers", user_id="op_1")
    res = agent.execute(req, ctx)
    assert res.success is True
    assert "Recent Shift Handovers" in res.response
    assert "CDU-101" in res.response


def test_5_command_extraction():
    """Test 5: Verify deterministic command extraction with various phrasing."""
    extractor = ShiftCommandExtractor()
    
    c1 = extractor.extract("Create night shift handover for Unit U-101")
    assert c1.command_type == ShiftCommandType.CREATE_HANDOVER
    assert c1.unit_id == "U-101"
    assert c1.shift_type == ShiftType.NIGHT

    c2 = extractor.extract("Approve handover SHO-20260822-CDU101-0001")
    assert c2.command_type == ShiftCommandType.APPROVE_HANDOVER
    assert c2.handover_number == "SHO-20260822-CDU101-0001"

    c3 = extractor.extract("Reject handover SHO-123 because of unverified pressure")
    assert c3.command_type == ShiftCommandType.REJECT_HANDOVER
    assert "unverified pressure" in c3.reason


def test_6_missing_handover_clarification(mock_agent):
    """Test 6: Ambiguous action without unit or handover number requests clarification."""
    agent, service = mock_agent
    req = AgentRequest(message="Create a new handover", user_id="op_1")
    ctx = RequestContext(request_id=req.request_id, session_id=req.session_id)
    res = agent.execute(req, ctx)
    assert "Which plant unit" in res.response
    assert res.metadata.get("requires_clarification") is True


def test_7_ambiguous_entity_clarification(mock_agent):
    """Test 7: Raw entity query (e.g. 'C-101') triggers clarification question."""
    agent, service = mock_agent
    req = AgentRequest(message="C-101", user_id="op_1")
    ctx = RequestContext(request_id=req.request_id, session_id=req.session_id)
    res = agent.execute(req, ctx)
    assert "You mentioned `C-101`" in res.response


def test_8_update_draft(mock_agent):
    """Test 8: Add observation notes to draft."""
    agent, service = mock_agent
    
    # Create draft
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    agent.execute(req_c, ctx)

    req_u = AgentRequest(message="Add note that C-101 has abnormal vibration on Unit U-101", user_id="op_1")
    res = agent.execute(req_u, ctx)
    assert res.success is True
    assert "Draft Updated" in res.response


def test_9_submit_handover(mock_agent):
    """Test 9: Submit handover via agent."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1", user_role="CONSOLE_OPERATOR")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    req_s = AgentRequest(message=f"Submit handover {hnum}", user_id="op_1", user_role="CONSOLE_OPERATOR")
    res_s = agent.execute(req_s, ctx)
    assert res_s.success is True
    assert "SUBMITTED" in res_s.response


def test_10_approve_handover_supervisor(mock_agent):
    """Test 10: Approve handover as supervisor."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1", user_role="CONSOLE_OPERATOR")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    # Submit first
    agent.execute(AgentRequest(message=f"Submit handover {hnum}", user_id="op_1", user_role="CONSOLE_OPERATOR"), ctx)

    # Approve as supervisor
    req_a = AgentRequest(message=f"Approve handover {hnum}", user_id="sup_salem", user_role="SHIFT_SUPERVISOR")
    res_a = agent.execute(req_a, ctx)
    assert res_a.success is True
    assert "PENDING_ACKNOWLEDGEMENT" in res_a.response


def test_11_reject_handover_with_reason(mock_agent):
    """Test 11: Reject handover with mandatory reason."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1", user_role="CONSOLE_OPERATOR")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    agent.execute(AgentRequest(message=f"Submit handover {hnum}", user_id="op_1", user_role="CONSOLE_OPERATOR"), ctx)

    req_r = AgentRequest(message=f"Reject handover {hnum} because safety interlock failed", user_id="sup_salem", user_role="SHIFT_SUPERVISOR")
    res_r = agent.execute(req_r, ctx)
    assert res_r.success is True
    assert "REJECTED" in res_r.response


def test_12_return_handover_with_reason(mock_agent):
    """Test 12: Return handover with mandatory reason."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1", user_role="CONSOLE_OPERATOR")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    agent.execute(AgentRequest(message=f"Submit handover {hnum}", user_id="op_1", user_role="CONSOLE_OPERATOR"), ctx)

    req_ret = AgentRequest(message=f"Return handover {hnum} because flare pressure missing", user_id="sup_salem", user_role="SHIFT_SUPERVISOR")
    res_ret = agent.execute(req_ret, ctx)
    assert res_ret.success is True
    assert "RETURNED" in res_ret.response


def test_13_cancel_confirmation(mock_agent):
    """Test 13: Cancel handover requires confirmation unless explicitly confirmed."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1", user_role="CONSOLE_OPERATOR")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    # Initial cancel request prompts for confirmation
    req_cancel = AgentRequest(message=f"Cancel handover {hnum}", user_id="op_1", user_role="CONSOLE_OPERATOR")
    res_conf = agent.execute(req_cancel, ctx)
    assert "irreversible" in res_conf.response
    assert res_conf.metadata.get("requires_confirmation") is True

    # Confirmed cancel request proceeds
    req_confirmed = AgentRequest(message=f"Yes, cancel handover {hnum}", user_id="op_1", user_role="CONSOLE_OPERATOR")
    res_done = agent.execute(req_confirmed, ctx)
    assert res_done.success is True
    assert "CANCELLED" in res_done.response


def test_14_safety_item_query(mock_agent):
    """Test 14: Inspect active safety items for a unit."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    agent.execute(req_c, ctx)

    req_s = AgentRequest(message="Show active LOTO and safety items for Unit U-101", user_id="op_1")
    res_s = agent.execute(req_s, ctx)
    assert res_s.success is True
    assert "no active safety items" in res_s.response.lower() or "safety" in res_s.response.lower()


def test_15_safety_acknowledgement(mock_agent):
    """Test 15: Incoming operator acknowledges safety items."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]
    
    # Attach a fake safety item via service
    item = service.add_safety_item(
        db=None,
        handover_id=hnum,
        category="LOTO",
        equipment_tag="P-101A",
        description="Isolated for repair"
    )

    req_ack = AgentRequest(message=f"Acknowledge safety items on Unit U-101", user_id="op_incoming")
    res_ack = agent.execute(req_ack, ctx)
    assert res_ack.success is True
    assert "Acknowledged" in res_ack.response


def test_16_completion_flow(mock_agent):
    """Test 16: Full turnover acceptance transitions handover to COMPLETED."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1", user_role="CONSOLE_OPERATOR")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    agent.execute(AgentRequest(message=f"Submit handover {hnum}", user_id="op_1", user_role="CONSOLE_OPERATOR"), ctx)
    agent.execute(AgentRequest(message=f"Approve handover {hnum}", user_id="sup_salem", user_role="SHIFT_SUPERVISOR"), ctx)

    # Incoming operator accepts
    req_ack = AgentRequest(message=f"Acknowledge and accept handover {hnum}", user_id="op_incoming", user_role="INCOMING_OPERATOR")
    res_ack = agent.execute(req_ack, ctx)
    assert res_ack.success is True
    assert "COMPLETED" in res_ack.response


def test_17_unauthorized_role(mock_agent):
    """Test 17: Field operator attempting supervisor APPROVE is blocked deterministically."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1", user_role="CONSOLE_OPERATOR")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    agent.execute(AgentRequest(message=f"Submit handover {hnum}", user_id="op_1", user_role="CONSOLE_OPERATOR"), ctx)

    # Field operator attempts to approve
    req_a = AgentRequest(message=f"Approve handover {hnum}", user_id="op_field_02", user_role="FIELD_OPERATOR")
    res_a = agent.execute(req_a, ctx)
    assert res_a.success is False
    assert "Transition Blocked" in res_a.response
    assert "ROLE_UNAUTHORIZED" in res_a.metadata.get("validation_errors", [])


def test_18_invalid_transition(mock_agent):
    """Test 18: Attempting to approve a DRAFT handover fails safely."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1", user_role="CONSOLE_OPERATOR")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    # Directly approve while still in DRAFT
    req_a = AgentRequest(message=f"Approve handover {hnum}", user_id="sup_salem", user_role="SHIFT_SUPERVISOR")
    res_a = agent.execute(req_a, ctx)
    assert res_a.success is False
    assert "INVALID_STATE_ACTION" in res_a.metadata.get("validation_errors", [])


def test_19_concurrency_conflict_translation(mock_agent, monkeypatch):
    """Test 19: Concurrency conflict produces clear user-friendly error message."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    def fake_trans_conflict(*a, **kw):
        raise ConcurrencyConflictError("Stale version")

    monkeypatch.setattr(service, "transition_handover", fake_trans_conflict)

    req_sub = AgentRequest(message=f"Submit handover {hnum}", user_id="op_1")
    res = agent.execute(req_sub, ctx)
    assert res.success is False
    assert "Concurrency Conflict" in res.response
    assert "modified by another user" in res.response


def test_20_terminal_state_protection(mock_agent, monkeypatch):
    """Test 20: Modifying a terminal handover informs user of locked state."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    def fake_trans_term(*a, **kw):
        raise TerminalStateError("Handover in terminal state 'COMPLETED'")

    monkeypatch.setattr(service, "transition_handover", fake_trans_term)

    req_sub = AgentRequest(message=f"Submit handover {hnum}", user_id="op_1")
    res = agent.execute(req_sub, ctx)
    assert res.success is False
    assert "Terminal State" in res.response


def test_21_audit_context_propagation(mock_agent, monkeypatch):
    """Test 21: Verify request_id, session_id, actor_id reach the service."""
    agent, service = mock_agent
    captured_context = {}

    def spy_create(db, data, actor_id, actor_role, handover_id=None, request_id=None, session_id=None, **kw):
        captured_context["request_id"] = request_id
        captured_context["session_id"] = session_id
        captured_context["actor_id"] = actor_id
        return service.create_handover(db, data, actor_id, actor_role, handover_id=handover_id, request_id=request_id, session_id=session_id)

    monkeypatch.setattr(service, "create_handover", spy_create)

    req = AgentRequest(
        request_id="req-audit-999",
        session_id="session-audit-888",
        user_id="op_auditor",
        user_role="CONSOLE_OPERATOR",
        message="Create a handover for Unit U-101"
    )
    ctx = RequestContext(request_id=req.request_id, session_id=req.session_id, user_id=req.user_id, user_role=req.user_role)
    agent.execute(req, ctx)

    assert captured_context["request_id"] == "req-audit-999"
    assert captured_context["session_id"] == "session-audit-888"
    assert captured_context["actor_id"] == "op_auditor"


def test_22_database_error_shielding(mock_agent, monkeypatch):
    """Test 22: Unhandled database exceptions do not expose raw SQL or stack traces."""
    agent, service = mock_agent
    req_c = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1")
    ctx = RequestContext(request_id=req_c.request_id, session_id=req_c.session_id)
    res_c = agent.execute(req_c, ctx)
    hnum = res_c.metadata["handover_number"]

    def crash_db(*a, **kw):
        raise RuntimeError("FATAL: connection to server at 'postgres://user:pass@10.0.0.1:5432' lost")

    monkeypatch.setattr(service, "transition_handover", crash_db)

    req_sub = AgentRequest(message=f"Submit handover {hnum}", user_id="op_1")
    res = agent.execute(req_sub, ctx)
    assert res.success is False
    assert "postgres://" not in res.response
    assert "An error occurred while accessing the shift handover system" in res.response


def test_23_qa_shift_multi_agent_routing(monkeypatch):
    """Test 23: Orchestrator coordinates Shift Agent + QA Agent for combined multi-agent queries."""
    from app.agents import qa_agent
    
    def fake_qa_service(*args, **kwargs):
        from app.services.generation import RAGResponse, SourceCitation
        return RAGResponse(
            question="What is the SOP for C-101?",
            answer="SOP-C101-04 requires checking lube oil pressure and vibration sensor before restart.",
            sources=[SourceCitation(source_number=1, document_name="SOP_C101.pdf", page_number=5)],
            query_type="normal",
            retrieval_count=1,
            grounded=True,
            status="success"
        )

    monkeypatch.setattr(qa_agent, "qa_service_fn", fake_qa_service)

    req = AgentRequest(
        message="Record abnormal vibration on C-101 for Unit U-101 handover and check the startup SOP procedure",
        user_id="op_1"
    )
    
    route_res = intent_router.route(req.message)
    assert route_res.intent == AgentIntent.MULTI_AGENT

    res = orchestrator.execute(req)
    assert res.query_type in ["multi_agent_composite", "p2p_peer_exchange"]
    assert ("Standard Operating Procedure" in res.response or "Technical SOP Guidance" in res.response)
    assert "SOP-C101-04" in res.response

    assert len(res.citations) >= 1


def test_24_physical_equipment_control_refusal():
    """Test 24: Direct equipment control command is intercepted by Safety Interlock."""
    req = AgentRequest(message="Shut down pump P-101 immediately", user_id="op_1")
    res = orchestrator.execute(req)
    assert res.query_type == "safety_interlock"
    assert "Safety Interlock" in res.response
    assert "cannot be executed by the AI assistant" in res.response


def test_25_streaming_contract(mock_agent):
    """Test 25: Verify stream() yields progressive status events, tokens, and done event."""
    agent, service = mock_agent
    req = AgentRequest(message="Create a handover for Unit U-101", user_id="op_1")
    ctx = RequestContext(request_id=req.request_id, session_id=req.session_id)

    events = list(agent.stream(req, ctx))
    assert len(events) >= 4
    
    progress_events = [e for e in events if e["type"] == "progress"]
    assert len(progress_events) >= 2
    assert progress_events[0]["step"] == "interpreting_request"

    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) == 1
    assert "Created Shift Handover Draft" in token_events[0]["content"]

    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
