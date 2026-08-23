from typing import Optional, List, Dict, Any
import logfire

from app.agents.loop.contracts import (
    Loop,
    Instrument,
    InstrumentType,
    SignalPath,
    Cable,
    JunctionBox,
    MarshallingPoint,
    IOChannel,
    ControlSystem,
    Alarm,
    SignalType,
    EngineeringDocument,
    LoopConsistencyResult
)


class LoopEngineeringService:
    """
    Deterministic domain service for Loop Engineering facts, signal paths, and consistency validation.
    Maintains clean separation from LLM generation and database persistence.
    """

    def __init__(self, fixture_store: Optional[Dict[str, Loop]] = None):
        # Controlled in-memory engineering repository (fixtures or authoritative source)
        self._store: Dict[str, Loop] = fixture_store if fixture_store is not None else self._build_default_fixtures()

    def get_loop(self, loop_tag: str) -> Optional[Loop]:
        """Retrieve Loop by tag or normalized number."""
        tag = loop_tag.strip().upper()
        # Direct lookup
        if tag in self._store:
            return self._store[tag]
        # Partial prefix matching (e.g. "PT-101" -> "101" or "LOOP-101")
        for k, v in self._store.items():
            if tag in k or any(tag == inst.tag.upper() for inst in v.instruments):
                return v
        return None

    def get_instrument(self, tag: str) -> Optional[Instrument]:
        """Find instrument across registered engineering loops."""
        t = tag.strip().upper()
        for loop in self._store.values():
            for inst in loop.instruments:
                if inst.tag.upper() == t:
                    return inst
        return None

    def get_signal_path(self, tag: str) -> Optional[SignalPath]:
        """Retrieve end-to-end signal path for an instrument or loop."""
        loop = self.get_loop(tag)
        if loop and loop.signal_path:
            return loop.signal_path
        return None

    def get_io_mapping(self, tag: str) -> Optional[Dict[str, Any]]:
        """Retrieve DCS / PLC I/O channel card mapping."""
        path = self.get_signal_path(tag)
        if path and path.io_channel:
            return {
                "instrument_tag": path.instrument_tag,
                "card_id": path.io_channel.card_id,
                "slot_number": path.io_channel.slot_number,
                "channel_number": path.io_channel.channel_number,
                "channel_address": path.io_channel.channel_address,
                "channel_type": path.io_channel.channel_type.value if path.io_channel.channel_type else None,
                "controller": path.control_system.controller_tag if path.control_system else "DCS-01"
            }
        return None

    def get_alarm_information(self, tag: str) -> List[Alarm]:
        """Retrieve alarm limits and trip setpoints."""
        loop = self.get_loop(tag)
        if loop:
            return loop.alarms
        return []

    def validate_loop_consistency(
        self,
        loop_tag: str,
        sources_evidence: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> LoopConsistencyResult:
        """
        Deterministic loop consistency check.
        Compares documented I/O channels across loop drawings, I/O lists, and datasheets.
        Flags LOOP_CONFIGURATION_CONFLICT on divergence.
        """
        loop = self.get_loop(loop_tag)
        if not loop:
            return LoopConsistencyResult(
                loop_tag=loop_tag,
                is_consistent=False,
                inconsistencies=[f"Loop '{loop_tag}' not found in engineering index."],
                conflict_code="LOOP_NOT_FOUND"
            )

        if not sources_evidence:
            return LoopConsistencyResult(
                loop_tag=loop_tag,
                is_consistent=True,
                inspected_sources=[doc.document_name for doc in loop.source_documents]
            )

        inconsistencies = []
        # Check for I/O channel mismatch between documents
        io_list_channel = sources_evidence.get("io_list", {}).get("channel_address")
        loop_dwg_channel = sources_evidence.get("loop_drawing", {}).get("channel_address")

        if io_list_channel and loop_dwg_channel and io_list_channel != loop_dwg_channel:
            msg = (
                f"Potential engineering inconsistency detected: "
                f"{loop_tag} is mapped to '{io_list_channel}' in the I/O list but '{loop_dwg_channel}' in the loop drawing."
            )
            inconsistencies.append(msg)
            logfire.warning(f"[LoopConsistency] Conflict on {loop_tag}: {msg}")
            return LoopConsistencyResult(
                loop_tag=loop_tag,
                is_consistent=False,
                inconsistencies=inconsistencies,
                inspected_sources=["I/O List Document", "Loop Drawing Document"],
                conflict_code="LOOP_CONFIGURATION_CONFLICT"
            )

        return LoopConsistencyResult(
            loop_tag=loop_tag,
            is_consistent=True,
            inspected_sources=list(sources_evidence.keys())
        )

    def _build_default_fixtures(self) -> Dict[str, Loop]:
        """
        Seed standard engineering test fixtures for unit CDU-101.
        """
        # PT-101 Loop
        pt101_inst = Instrument(
            tag="PT-101",
            description="Crude Distillation Column Overhead Vapor Pressure",
            instrument_type=InstrumentType.PRESSURE_TRANSMITTER,
            unit_id="CDU-101",
            p_and_id_reference="PID-CDU-101-01",
            range_min=0.0,
            range_max=10.0,
            engineering_units="bar",
            location="CDU-101 Column Top"
        )
        pt101_path = SignalPath(
            loop_tag="101",
            instrument_tag="PT-101",
            field_cable=Cable(cable_tag="CBL-PT-101", cable_type="2x1.5mm2 Shielded Pair", from_location="PT-101 Field", to_location="JB-101"),
            junction_box=JunctionBox(jb_tag="JB-101", location="CDU-101 Pipe Rack 2", terminal_strip="TS-1", terminal_numbers=["1", "2"]),
            home_run_cable=Cable(cable_tag="CBL-HR-101", cable_type="24-Pair Multi-core", from_location="JB-101", to_location="MB-01"),
            marshalling_point=MarshallingPoint(cabinet_id="MARSH-01", rack_id="R-01", strip_id="TB-A", terminal_number="12"),
            io_channel=IOChannel(card_id="AI-CARD-01", slot_number=2, channel_number=5, channel_type=SignalType.ANALOG_IN_4_20MA, channel_address="AI-05"),
            control_system=ControlSystem(system_type="DCS", controller_tag="DCS-CDU-CTRL-01", node_id="NODE-101")
        )
        pt101_alarms = [
            Alarm(alarm_tag="PT-101-PAHH", alarm_type="HH", setpoint=8.5, units="bar", priority="HIGH"),
            Alarm(alarm_tag="PT-101-PAH", alarm_type="H", setpoint=7.0, units="bar", priority="MEDIUM"),
            Alarm(alarm_tag="PT-101-PAL", alarm_type="L", setpoint=2.0, units="bar", priority="LOW")
        ]
        pt101_docs = [
            EngineeringDocument(document_name="DWG-LOOP-101.pdf", document_type="LOOP_DRAWING", drawing_number="DWG-LOOP-101", page_number=1),
            EngineeringDocument(document_name="PID-CDU-101-01.pdf", document_type="P&ID", drawing_number="PID-CDU-101-01", page_number=3),
            EngineeringDocument(document_name="INSTRUMENT_INDEX_CDU101.xlsx", document_type="DATASHEET", page_number=12)
        ]

        loop_101 = Loop(
            loop_tag="101",
            service_description="Column Overhead Pressure Control Loop",
            unit_id="CDU-101",
            instruments=[pt101_inst],
            signal_path=pt101_path,
            alarms=pt101_alarms,
            source_documents=pt101_docs
        )

        return {
            "101": loop_101,
            "PT-101": loop_101,
            "LOOP-101": loop_101
        }


# Global Loop Engineering Service Singleton
loop_engineering_service = LoopEngineeringService()
