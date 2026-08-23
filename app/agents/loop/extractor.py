import re
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field

from app.agents.loop.contracts import InstrumentType


class ParsedEngineeringEntity(BaseModel):
    tag: str
    entity_type: str  # "INSTRUMENT", "EQUIPMENT", "LOOP", "UNIT", "JUNCTION_BOX", "CABLE"
    instrument_type: InstrumentType = InstrumentType.UNKNOWN
    normalized_tag: str
    is_ambiguous: bool = False
    clarification_prompt: Optional[str] = None


class LoopQueryIntent(BaseModel):
    action: str  # "LOOP_SUMMARY", "SIGNAL_PATH", "IO_MAPPING", "ALARM_INFO", "DOCUMENT_LOOKUP", "CONSISTENCY_CHECK", "GENERAL_QA"
    primary_entity: Optional[ParsedEngineeringEntity] = None
    secondary_entities: List[ParsedEngineeringEntity] = Field(default_factory=list)
    unit_id: Optional[str] = None
    target_attribute: Optional[str] = None
    requires_clarification: bool = False
    clarification_message: Optional[str] = None


class LoopCommandExtractor:
    """
    Deterministic zero-token regex extractor for Loop Engineering entities and intents.
    Sub-millisecond latency; enforces strict ISA tag classification.
    """

    # ISA Standard Instrument Tag Pattern (e.g. PT-101, PIC-101, TT-204, XV-101, PSV-101, FT-301A)
    INSTRUMENT_TAG_PATTERN = re.compile(
        r"\b([A-Z]{2,4})-?(\d{2,4})([A-Z])?\b",
        re.IGNORECASE
    )

    # Equipment Tag Pattern (e.g. P-101, C-101, E-102, V-101, KT-101, T-101)
    EQUIPMENT_TAG_PATTERN = re.compile(
        r"\b([PCEVTK]|KT|PU|TK|BLR|FURN)-?(\d{2,4})([A-Z])?\b",
        re.IGNORECASE
    )

    # Unit Tag Pattern (e.g. Unit CDU-101, U-101, CDU-101, VDU-201, HCU-301)
    UNIT_PATTERN = re.compile(
        r"\b(?:Unit\s+)?(CDU|VDU|HCU|FCCU|SRU|ARU|UTILITY|U)-?(\d{2,4})\b",
        re.IGNORECASE
    )

    # Junction Box Pattern (e.g. JB-101, JB-01, JB101)
    JB_PATTERN = re.compile(
        r"\b(JB)-?(\d{1,4})\b",
        re.IGNORECASE
    )

    # Cable Pattern (e.g. CBL-101, CABLE-101)
    CABLE_PATTERN = re.compile(
        r"\b(CBL|CABLE)-?(\d{1,4})\b",
        re.IGNORECASE
    )

    INSTRUMENT_PREFIX_MAP = {
        "PT": InstrumentType.PRESSURE_TRANSMITTER,
        "PI": InstrumentType.PRESSURE_TRANSMITTER,
        "PIT": InstrumentType.PRESSURE_TRANSMITTER,
        "PIC": InstrumentType.PRESSURE_INDICATING_CONTROLLER,
        "TT": InstrumentType.TEMPERATURE_TRANSMITTER,
        "TE": InstrumentType.TEMPERATURE_TRANSMITTER,
        "TIC": InstrumentType.TEMPERATURE_TRANSMITTER,
        "FT": InstrumentType.FLOW_TRANSMITTER,
        "FE": InstrumentType.FLOW_TRANSMITTER,
        "FIC": InstrumentType.FLOW_INDICATING_CONTROLLER,
        "LT": InstrumentType.LEVEL_TRANSMITTER,
        "LE": InstrumentType.LEVEL_TRANSMITTER,
        "LIC": InstrumentType.LEVEL_INDICATING_CONTROLLER,
        "CV": InstrumentType.CONTROL_VALVE,
        "FV": InstrumentType.CONTROL_VALVE,
        "PV": InstrumentType.CONTROL_VALVE,
        "LV": InstrumentType.CONTROL_VALVE,
        "TV": InstrumentType.CONTROL_VALVE,
        "XV": InstrumentType.SHUTDOWN_VALVE,
        "SDV": InstrumentType.SHUTDOWN_VALVE,
        "MOV": InstrumentType.MOTOR_OPERATED_VALVE,
        "PSV": InstrumentType.PRESSURE_SAFETY_VALVE,
        "PRV": InstrumentType.PRESSURE_SAFETY_VALVE,
        "AT": InstrumentType.ANALYZER,
        "PSH": InstrumentType.SWITCH,
        "PSL": InstrumentType.SWITCH,
        "TSH": InstrumentType.SWITCH,
        "TSL": InstrumentType.SWITCH,
        "LSH": InstrumentType.SWITCH,
        "LSL": InstrumentType.SWITCH,
    }

    def extract(self, query: str) -> LoopQueryIntent:
        """
        Parse user engineering query into strongly-typed LoopQueryIntent.
        """
        q = query.strip()
        entities = self.extract_entities(q)
        unit_id = self.extract_unit(q)

        # Detect Action Type using word boundaries
        action = "LOOP_SUMMARY"
        q_lower = q.lower()

        if re.search(r"\b(?:signal\s*path|wiring|route|connection\s*path|cable\s*to\s*dcs|path\s*for)\b", q_lower):
            action = "SIGNAL_PATH"
        elif re.search(r"\b(?:compare|conflict|match|inconsistency|consistency|mismatch)\b", q_lower):
            action = "CONSISTENCY_CHECK"
        elif re.search(r"\b(?:i/o|io|channel|card|slot|dcs\s*input|dcs\s*output|terminal\s*strip)\b", q_lower) and not re.search(r"\binformation\b", q_lower):
            action = "IO_MAPPING"
        elif re.search(r"\b(?:alarm|setpoint|trip\s*limit|\bhh\b|\bll\b|high\s*limit|low\s*limit)\b", q_lower):
            action = "ALARM_INFO"
        elif re.search(r"\b(?:document|drawing|p&id|pid|datasheet|schedule|diagram)\b", q_lower):
            action = "DOCUMENT_LOOKUP"

        if not entities:
            # Check for general query or bare loop number
            loop_num_match = re.search(r"\bloop\s+(\d{2,4})\b", q, re.IGNORECASE)
            if loop_num_match:
                num = loop_num_match.group(1)
                primary = ParsedEngineeringEntity(
                    tag=f"Loop-{num}",
                    entity_type="LOOP",
                    normalized_tag=num
                )
                return LoopQueryIntent(action=action, primary_entity=primary, unit_id=unit_id)

            return LoopQueryIntent(
                action="GENERAL_QA",
                unit_id=unit_id,
                requires_clarification=False
            )

        primary = entities[0]
        secondary = entities[1:] if len(entities) > 1 else []

        # Ambiguity Check: User provided just a tag without context
        if len(q.split()) <= 3 and action == "LOOP_SUMMARY" and primary.entity_type in ["INSTRUMENT", "EQUIPMENT"]:
            return LoopQueryIntent(
                action=action,
                primary_entity=primary,
                secondary_entities=secondary,
                unit_id=unit_id,
                requires_clarification=True,
                clarification_message=(
                    f"Tag `{primary.tag}` appears in multiple engineering contexts. "
                    f"Would you like to see the **Loop Signal Path**, **DCS I/O Mapping**, **Alarm Limits**, or **P&ID Document Reference**?"
                )
            )

        return LoopQueryIntent(
            action=action,
            primary_entity=primary,
            secondary_entities=secondary,
            unit_id=unit_id,
            requires_clarification=False
        )

    def extract_entities(self, text: str) -> List[ParsedEngineeringEntity]:
        """
        Extract all recognized engineering objects with normalized ISA format.
        """
        results: List[ParsedEngineeringEntity] = []
        seen_tags = set()

        # 1. Match Instruments
        for m in self.INSTRUMENT_TAG_PATTERN.finditer(text):
            prefix = m.group(1).upper()
            number = m.group(2)
            suffix = m.group(3).upper() if m.group(3) else ""
            
            # Check if this prefix is known instrument
            if prefix in self.INSTRUMENT_PREFIX_MAP:
                norm_tag = f"{prefix}-{number}{suffix}"
                if norm_tag not in seen_tags:
                    seen_tags.add(norm_tag)
                    results.append(ParsedEngineeringEntity(
                        tag=m.group(0),
                        entity_type="INSTRUMENT",
                        instrument_type=self.INSTRUMENT_PREFIX_MAP[prefix],
                        normalized_tag=norm_tag
                    ))

        # 2. Match Equipment Tags (e.g. C-101, P-101)
        for m in self.EQUIPMENT_TAG_PATTERN.finditer(text):
            prefix = m.group(1).upper()
            number = m.group(2)
            suffix = m.group(3).upper() if m.group(3) else ""
            norm_tag = f"{prefix}-{number}{suffix}"
            if norm_tag not in seen_tags:
                seen_tags.add(norm_tag)
                results.append(ParsedEngineeringEntity(
                    tag=m.group(0),
                    entity_type="EQUIPMENT",
                    normalized_tag=norm_tag
                ))

        # 3. Match Junction Boxes
        for m in self.JB_PATTERN.finditer(text):
            norm_tag = f"JB-{m.group(2)}"
            if norm_tag not in seen_tags:
                seen_tags.add(norm_tag)
                results.append(ParsedEngineeringEntity(
                    tag=m.group(0),
                    entity_type="JUNCTION_BOX",
                    normalized_tag=norm_tag
                ))

        # 4. Match Cables
        for m in self.CABLE_PATTERN.finditer(text):
            norm_tag = f"CBL-{m.group(2)}"
            if norm_tag not in seen_tags:
                seen_tags.add(norm_tag)
                results.append(ParsedEngineeringEntity(
                    tag=m.group(0),
                    entity_type="CABLE",
                    normalized_tag=norm_tag
                ))

        return results

    def extract_unit(self, text: str) -> Optional[str]:
        m = self.UNIT_PATTERN.search(text)
        if m:
            prefix = m.group(1).upper()
            num = m.group(2)
            return f"{prefix}-{num}"
        return None
