import json
import pytest
from unittest.mock import MagicMock, patch

from app.agents.contracts import (
    AgentRequest,
    RequestContext,
    AgentResult,
    AgentIntent,
    RiskLevel,
    AgentErrorCode
)
from app.agents.registry import agent_registry
from app.agents.router import intent_router
from app.agents.orchestrator import orchestrator
from app.agents.loop import (
    LoopEngineeringAgent,
    loop_engineering_agent,
    LoopEngineeringService,
    LoopCommandExtractor,
    Loop,
    Instrument,
    InstrumentType,
    SignalPath,
    Cable,
    JunctionBox,
    MarshallingPoint,
    IOChannel,
    SignalType,
    ControlSystem,
    Alarm,
    EngineeringDocument
)
from app.services.cache import cache_service


@pytest.fixture
def agent():
    return loop_engineering_agent


@pytest.fixture
def extractor():
    return LoopCommandExtractor()


@pytest.fixture
def custom_service():
    inst = Instrument(
        tag="FT-201",
        description="Crude Feed Flow Rate",
        instrument_type=InstrumentType.FLOW_TRANSMITTER,
        unit_id="CDU-101",
        range_min=0.0,
        range_max=500.0,
        engineering_units="m3/h"
    )
    path = SignalPath(
        loop_tag="201",
        instrument_tag="FT-201",
        junction_box=JunctionBox(jb_tag="JB-201", terminal_strip="TS-2"),
        marshalling_point=MarshallingPoint(cabinet_id="MARSH-02", terminal_number="5"),
        io_channel=IOChannel(card_id="AI-CARD-02", slot_number=1, channel_number=2, channel_address="AI-02", channel_type=SignalType.ANALOG_IN_4_20MA),
        control_system=ControlSystem(controller_tag="DCS-CTRL-01")
    )
    loop = Loop(
        loop_tag="201",
        service_description="Crude Feed Flow Control",
        unit_id="CDU-101",
        instruments=[inst],
        signal_path=path,
        alarms=[Alarm(alarm_tag="FT-201-FAL", alarm_type="L", setpoint=50.0, units="m3/h", priority="HIGH")],
        source_documents=[EngineeringDocument(document_name="DWG-LOOP-201.pdf", document_type="LOOP_DRAWING", page_number=2)]
    )
    return LoopEngineeringService(fixture_store={"201": loop, "FT-201": loop})


# ============================================================
# 16 FOCUSED LOOP ENGINEERING AGENT TEST SCENARIOS
# ============================================================

def test_1_agent_registration():
    """Test 1: LoopEngineeringAgent is registered in the central agent registry."""
    assert agent_registry.has("loop_engineering_agent")
    reg_agent = agent_registry.get("loop_engineering_agent")
    assert reg_agent is not None
    assert reg_agent.agent_id == "loop_engineering_agent"
    assert "signal_path_tracing" in reg_agent.capabilities


def test_2_instrument_tag_extraction(extractor):
    """Test 2: Deterministic extraction of instrument tags (PT-101, LT-204, etc.)."""
    intent = extractor.extract("Show me the loop drawing for PT-101 in CDU-101")
    assert intent.primary_entity is not None
    assert intent.primary_entity.normalized_tag == "PT-101"
    assert intent.primary_entity.instrument_type == InstrumentType.PRESSURE_TRANSMITTER
    assert intent.action == "DOCUMENT_LOOKUP"
    assert intent.unit_id == "CDU-101"


def test_3_equipment_tag_extraction(extractor):
    """Test 3: Extraction of equipment tags (C-101, P-101) distinguishing from instruments."""
    intent = extractor.extract("What is the connection between pump P-101 and the DCS?")
    assert intent.primary_entity is not None
    assert intent.primary_entity.normalized_tag == "P-101"
    assert intent.primary_entity.entity_type == "EQUIPMENT"


def test_4_ambiguous_tag_clarification(extractor, agent):
    """Test 4: Bare ambiguous tag triggers clarification prompt."""
    intent = extractor.extract("PT-101")
    assert intent.requires_clarification is True
    assert "Loop Signal Path" in intent.clarification_message

    req = AgentRequest(request_id="req-clarify", user_id="u1", session_id="s1", message="PT-101")
    ctx = RequestContext(request_id="req-clarify", user_id="u1", session_id="s1", current_agent="loop_engineering_agent")
    res = agent.execute(req, ctx)
    assert res.status == "success"
    assert res.query_type == "clarification_required"
    assert res.metadata["requires_clarification"] is True


def test_5_loop_lookup(agent):
    """Test 5: Loop lookup retrieves complete loop summary with instruments and documents."""
    req = AgentRequest(request_id="req-loop-1", user_id="u1", session_id="s1", message="Show me the loop information for PT-101")
    ctx = RequestContext(request_id="req-loop-1", user_id="u1", session_id="s1", current_agent="loop_engineering_agent")
    res = agent.execute(req, ctx)
    assert res.success is True
    assert "Control Loop Information" in res.response
    assert "PT-101" in res.response
    assert len(res.citations) >= 1
    assert res.citations[0]["document_type"] == "LOOP_DRAWING"


def test_6_signal_path_lookup(agent):
    """Test 6: Signal path query traces field instrument to DCS channel."""
    req = AgentRequest(request_id="req-sig-1", user_id="u1", session_id="s1", message="What is the complete signal path for PT-101?")
    ctx = RequestContext(request_id="req-sig-1", user_id="u1", session_id="s1", current_agent="loop_engineering_agent")
    res = agent.execute(req, ctx)
    assert res.success is True
    assert "Field Instrument" in res.response
    assert "JB-101" in res.response
    assert "MARSH-01" in res.response
    assert "AI-05" in res.response


def test_7_io_mapping_lookup(agent):
    """Test 7: DCS I/O card and channel mapping query."""
    req = AgentRequest(request_id="req-io-1", user_id="u1", session_id="s1", message="Which DCS input channel is connected to PT-101?")
    ctx = RequestContext(request_id="req-io-1", user_id="u1", session_id="s1", current_agent="loop_engineering_agent")
    res = agent.execute(req, ctx)
    assert res.success is True
    assert "DCS I/O Channel Mapping" in res.response
    assert "AI-CARD-01" in res.response
    assert "AI-05" in res.response


def test_8_alarm_configuration_lookup(agent):
    """Test 8: Alarm setpoints and priority lookup."""
    req = AgentRequest(request_id="req-alm-1", user_id="u1", session_id="s1", message="What are the alarm setpoints for PT-101?")
    ctx = RequestContext(request_id="req-alm-1", user_id="u1", session_id="s1", current_agent="loop_engineering_agent")
    res = agent.execute(req, ctx)
    assert res.success is True
    assert "Alarm Configuration" in res.response
    assert "PT-101-PAHH" in res.response
    assert "8.5 bar" in res.response


def test_9_missing_evidence_handling(agent):
    """Test 9: Missing signal path evidence is explicitly reported without fabrication."""
    req = AgentRequest(request_id="req-miss-1", user_id="u1", session_id="s1", message="What is the signal path for TT-999?")
    ctx = RequestContext(request_id="req-miss-1", user_id="u1", session_id="s1", current_agent="loop_engineering_agent")
    res = agent.execute(req, ctx)
    assert res.success is False
    assert "Signal path could not be fully established" in res.response
    assert res.query_type == "signal_path_incomplete"


def test_10_engineering_conflict_detection(agent):
    """Test 10: Inconsistent I/O channel between documents flags LOOP_CONFIGURATION_CONFLICT."""
    conflicting_evidence = {
        "io_list": {"channel_address": "AI-05"},
        "loop_drawing": {"channel_address": "AI-06"}
    }
    req = AgentRequest(
        request_id="req-conf-1",
        user_id="u1",
        session_id="s1",
        message="Check loop consistency for PT-101",
        metadata={"sources_evidence": conflicting_evidence}
    )
    ctx = RequestContext(request_id="req-conf-1", user_id="u1", session_id="s1", current_agent="loop_engineering_agent")
    res = agent.execute(req, ctx)
    assert res.success is False
    assert "Potential Engineering Inconsistency Detected" in res.response
    assert "'AI-05' in the I/O list but 'AI-06' in the loop drawing" in res.response
    assert res.error["code"] == "LOOP_CONFIGURATION_CONFLICT"


def test_11_safety_interlock_preservation():
    """Test 11: High-risk plant command like 'Trip P-101' is blocked by router safety interlock."""
    routing = intent_router.route("Trip P-101 immediately")
    assert routing.intent == AgentIntent.HIGH_RISK
    assert routing.risk_level == RiskLevel.CRITICAL
    assert len(routing.target_agents) == 0


def test_12_streaming_contract(agent):
    """Test 12: LoopEngineeringAgent streaming yields progress, token, and done events."""
    req = AgentRequest(request_id="req-st-1", user_id="u1", session_id="s1", message="Show DCS channel for PT-101")
    ctx = RequestContext(request_id="req-st-1", user_id="u1", session_id="s1", current_agent="loop_engineering_agent")
    
    events = list(agent.stream(req, ctx))
    event_types = [e.get("type") for e in events]
    assert "progress" in event_types
    assert "token" in event_types
    assert "done" in event_types


def test_13_multi_agent_routing():
    """Test 13: Multi-agent query combining shift log and loop drawing routes to both agents."""
    routing = intent_router.route("Record PT-101 high pressure in shift handover and show loop drawing")
    assert routing.intent == AgentIntent.MULTI_AGENT
    assert "shift_handover_agent" in routing.target_agents
    assert "loop_engineering_agent" in routing.target_agents


def test_14_custom_service_fixture_injection(custom_service):
    """Test 14: LoopEngineeringAgent operates cleanly with injected custom service fixtures."""
    custom_agent = LoopEngineeringAgent(service=custom_service)
    req = AgentRequest(request_id="req-cust-1", user_id="u1", session_id="s1", message="Show signal path for FT-201")
    ctx = RequestContext(request_id="req-cust-1", user_id="u1", session_id="s1", current_agent="loop_engineering_agent")
    res = custom_agent.execute(req, ctx)
    assert res.success is True
    assert "FT-201" in res.response
    assert "JB-201" in res.response
    assert "MARSH-02" in res.response


def test_15_caching_policy_respect():
    """Test 15: Loop Engineering queries adhere to cache policy invariants."""
    # Static QA is cacheable
    assert cache_service.is_cacheable(query_type="general_qa", intent="qa") is True
    # Shift operations are NOT cacheable
    assert cache_service.is_cacheable(query_type="create_handover", intent="shift") is False
    assert cache_service.is_cacheable(query_type="transition_success", intent="shift") is False


def test_16_orchestrator_execution_routing():
    """Test 16: Orchestrator automatically dispatches LOOP_ENGINEERING intent to loop_engineering_agent."""
    req = AgentRequest(request_id="req-orch-loop-1", user_id="u1", session_id="s1", message="Show signal path for PT-101")
    res = orchestrator.execute(req)
    assert res.success is True
    assert res.agent_id == "loop_engineering_agent"
    assert "Field Instrument" in res.response
