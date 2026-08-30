import pytest
from app.agents.shift.contracts import ShiftHandoverData, ShiftType, ShiftHandoverRole, SafetyCriticalItem
from app.agents.shift.quality_gate import ShiftHandoverQualityGate, shift_quality_gate
from app.agents.shift.voice import ShiftVoiceIngestionService, shift_voice_service
from app.agents.shift.extractor import ShiftCommandExtractor
from app.agents.shift.command import ShiftCommandType
from app.agents.shift.agent import ShiftHandoverAgent
from app.agents.contracts import AgentRequest, RequestContext


def test_quality_gate_complete_handover():
    gate = ShiftHandoverQualityGate(passing_threshold=75.0)
    data = ShiftHandoverData(
        unit_id="CDU-101",
        shift_type=ShiftType.DAY,
        shift_date="2026-08-29",
        outgoing_operator_id="op_john",
        operational_summary="Normal CDU-101 operation maintained steady crude feed rate of 120,000 bpd with stable column pressure.",
        equipment_abnormalities=["Compressor C-101 high vibration reading at 4.5 mm/s"],
        loto_isolations=["Pump P-101A LOTO isolation active for seal replacement"],
        safety_items=[
            SafetyCriticalItem(
                category="LOTO",
                equipment_tag="P-101A",
                description="Pump P-101A suction and discharge valves locked out",
                active=True,
                acknowledged_by_incoming=True
            )
        ]
    )

    report = gate.evaluate(data, handover_id="SHO-101")
    assert report.overall_score >= 75.0
    assert report.is_passing is True
    assert report.unit_id == "CDU-101"
    assert "summary_clarity" in report.dimension_scores


def test_quality_gate_deficient_handover():
    gate = ShiftHandoverQualityGate(passing_threshold=75.0)
    data = ShiftHandoverData(
        unit_id="CDU-101",
        shift_type=ShiftType.DAY,
        shift_date="2026-08-29",
        outgoing_operator_id="op_john",
        operational_summary="",  # Empty operational summary
        equipment_abnormalities=["Pump noise"],  # Untagged abnormality
        loto_isolations=["Valve isolation"],  # Untagged LOTO
    )

    report = gate.evaluate(data, handover_id="SHO-102")
    assert report.overall_score < 75.0
    assert report.is_passing is False
    assert len(report.missing_items) >= 1
    assert len(report.recommendations) >= 1


def test_voice_ingestion_service():
    service = ShiftVoiceIngestionService()
    transcript = "Field walkdown note for unit CDU-101: Found minor flange weeping on Pump P-101A discharge valve and LOTO active on compressor C-101."
    result = service.process_voice_note(
        transcript=transcript,
        actor_id="field_op_steve",
        actor_role=ShiftHandoverRole.FIELD_OPERATOR,
        unit_id="CDU-101"
    )

    assert result.success is True
    assert result.unit_id == "CDU-101"
    assert "P-101A" in result.extracted_equipment_tags
    assert "C-101" in result.extracted_equipment_tags
    assert len(result.extracted_abnormalities) >= 1 or len(result.extracted_loto_items) >= 1


def test_extractor_quality_command():
    extractor = ShiftCommandExtractor()
    cmd = extractor.extract("Check quality score for CDU-101 shift handover draft")
    assert cmd.command_type == ShiftCommandType.CHECK_QUALITY
    assert cmd.unit_id == "CDU-101"


def test_extractor_voice_command():
    extractor = ShiftCommandExtractor()
    cmd = extractor.extract("Record field voice note for unit HCU-202: Pump P-202 high temperature 95°C")
    assert cmd.command_type == ShiftCommandType.PROCESS_VOICE_NOTE
    assert cmd.unit_id == "HCU-202"
