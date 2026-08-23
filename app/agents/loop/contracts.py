from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class SignalType(str, Enum):
    ANALOG_IN_4_20MA = "4-20mA_AI"
    ANALOG_OUT_4_20MA = "4-20mA_AO"
    DIGITAL_IN_24VDC = "24VDC_DI"
    DIGITAL_OUT_24VDC = "24VDC_DO"
    HART = "HART"
    FOUNDATION_FIELDBUS = "FOUNDATION_FIELDBUS"
    MODBUS = "MODBUS"
    ETHERNET = "ETHERNET"


class InstrumentType(str, Enum):
    PRESSURE_TRANSMITTER = "PRESSURE_TRANSMITTER"
    TEMPERATURE_TRANSMITTER = "TEMPERATURE_TRANSMITTER"
    FLOW_TRANSMITTER = "FLOW_TRANSMITTER"
    LEVEL_TRANSMITTER = "LEVEL_TRANSMITTER"
    PRESSURE_INDICATING_CONTROLLER = "PRESSURE_INDICATING_CONTROLLER"
    LEVEL_INDICATING_CONTROLLER = "LEVEL_INDICATING_CONTROLLER"
    FLOW_INDICATING_CONTROLLER = "FLOW_INDICATING_CONTROLLER"
    CONTROL_VALVE = "CONTROL_VALVE"
    SHUTDOWN_VALVE = "SHUTDOWN_VALVE"
    MOTOR_OPERATED_VALVE = "MOTOR_OPERATED_VALVE"
    PRESSURE_SAFETY_VALVE = "PRESSURE_SAFETY_VALVE"
    SWITCH = "SWITCH"
    ANALYZER = "ANALYZER"
    UNKNOWN = "UNKNOWN"


class Instrument(BaseModel):
    tag: str = Field(..., description="Unique ISA instrument tag (e.g. PT-101).")
    description: Optional[str] = None
    instrument_type: InstrumentType = InstrumentType.UNKNOWN
    unit_id: Optional[str] = None
    p_and_id_reference: Optional[str] = None
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    engineering_units: Optional[str] = None
    fail_state: Optional[str] = None  # e.g. "FAIL_CLOSE", "FAIL_OPEN", "FAIL_LOCKED"
    location: Optional[str] = None


class Cable(BaseModel):
    cable_tag: str
    cable_type: Optional[str] = None
    core_count: Optional[int] = None
    from_location: Optional[str] = None
    to_location: Optional[str] = None


class JunctionBox(BaseModel):
    jb_tag: str
    location: Optional[str] = None
    terminal_strip: Optional[str] = None
    terminal_numbers: List[str] = Field(default_factory=list)


class MarshallingPoint(BaseModel):
    cabinet_id: str
    rack_id: Optional[str] = None
    strip_id: Optional[str] = None
    terminal_number: Optional[str] = None


class IOChannel(BaseModel):
    card_id: str
    slot_number: Optional[int] = None
    channel_number: Optional[int] = None
    channel_type: Optional[SignalType] = None
    channel_address: Optional[str] = None  # e.g. "AI-05", "101.04.01"


class ControlSystem(BaseModel):
    system_type: str = "DCS"  # DCS, SIS, PLC, F&G
    controller_tag: Optional[str] = None
    node_id: Optional[str] = None
    scan_time_ms: Optional[int] = None


class Alarm(BaseModel):
    alarm_tag: str
    alarm_type: str  # "HH", "H", "L", "LL", "DEV"
    setpoint: float
    units: Optional[str] = None
    priority: str = "MEDIUM"  # "LOW", "MEDIUM", "HIGH", "EMERGENCY"


class SignalPath(BaseModel):
    loop_tag: str
    instrument_tag: str
    field_cable: Optional[Cable] = None
    junction_box: Optional[JunctionBox] = None
    home_run_cable: Optional[Cable] = None
    marshalling_point: Optional[MarshallingPoint] = None
    io_channel: Optional[IOChannel] = None
    control_system: Optional[ControlSystem] = None


class EngineeringDocument(BaseModel):
    document_name: str
    document_type: str  # "LOOP_DRAWING", "P&ID", "DATASHEET", "IO_LIST", "CABLE_SCHEDULE"
    drawing_number: Optional[str] = None
    revision: Optional[str] = None
    page_number: Optional[int] = None


class Loop(BaseModel):
    loop_tag: str = Field(..., description="Loop identifier (e.g. 101, 204, PT-101).")
    service_description: Optional[str] = None
    unit_id: Optional[str] = None
    instruments: List[Instrument] = Field(default_factory=list)
    signal_path: Optional[SignalPath] = None
    alarms: List[Alarm] = Field(default_factory=list)
    source_documents: List[EngineeringDocument] = Field(default_factory=list)


class LoopEvidence(BaseModel):
    source_document: str
    document_type: str
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    snippet: str
    extracted_facts: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0


class LoopConsistencyResult(BaseModel):
    loop_tag: str
    is_consistent: bool = True
    inconsistencies: List[str] = Field(default_factory=list)
    inspected_sources: List[str] = Field(default_factory=list)
    conflict_code: Optional[str] = None
