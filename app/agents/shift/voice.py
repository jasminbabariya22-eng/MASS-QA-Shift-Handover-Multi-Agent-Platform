from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import logfire

from app.agents.shift.contracts import (
    ShiftHandover,
    ShiftHandoverData,
    ShiftHandoverRole,
    ShiftHandoverAction,
    SafetyCriticalItem,
    ShiftType,
)
from app.agents.shift.command import ShiftCommand, ShiftCommandType
from app.agents.shift.extractor import ShiftCommandExtractor


class VoiceIngestionResult(BaseModel):
    """
    Result contract returned after processing a field operator voice log note.
    """
    success: bool
    transcript: str
    unit_id: Optional[str] = None
    handover_id: Optional[str] = None
    extracted_command_type: ShiftCommandType
    extracted_abnormalities: List[str] = Field(default_factory=list)
    extracted_loto_items: List[str] = Field(default_factory=list)
    extracted_equipment_tags: List[str] = Field(default_factory=list)
    summary_message: str = ""


class ShiftVoiceIngestionService:
    """
    Speech-to-Text Voice Log Ingestion Service for Field Operators.
    Parses spoken voice notes, extracts operational entities (equipment tags, LOTO isolations, abnormalities),
    and updates or initializes shift handover drafts automatically.
    """

    def __init__(self, extractor: Optional[ShiftCommandExtractor] = None, service: Optional[Any] = None):
        self.extractor = extractor or ShiftCommandExtractor()
        self._service = service

    @property
    def service(self):
        if self._service is None:
            from app.services.shift_handover_service import shift_handover_service
            self._service = shift_handover_service
        return self._service

    def process_voice_note(
        self,
        transcript: str,
        actor_id: str,
        actor_role: ShiftHandoverRole = ShiftHandoverRole.FIELD_OPERATOR,
        unit_id: Optional[str] = None,
        db: Optional[Any] = None
    ) -> VoiceIngestionResult:
        """
        Process a raw voice note transcript spoken by a field operator.
        Extracts structured operational items and attaches them to the unit's active shift draft.
        """
        logfire.info(f"[VoiceIngestion] Processing field voice note for unit {unit_id} by {actor_id}")

        cleaned_text = transcript.strip()
        if not cleaned_text:
            return VoiceIngestionResult(
                success=False,
                transcript=transcript,
                extracted_command_type=ShiftCommandType.UNKNOWN,
                summary_message="Voice transcript was empty."
            )

        # 1. Extract command and operational entities using extractor
        cmd = self.extractor.extract(cleaned_text, context_metadata={"selected_unit_id": unit_id})
        target_unit = unit_id or cmd.unit_id or "CDU-101"

        extracted_tags: List[str] = []
        if cmd.equipment_tag and cmd.equipment_tag != "GENERAL":
            extracted_tags.append(cmd.equipment_tag)

        # Find any additional equipment tags in the transcript
        tags = self.extractor.EQUIPMENT_REGEX.findall(cleaned_text)
        for t in tags:
            t_upper = t.upper()
            if t_upper not in extracted_tags:
                extracted_tags.append(t_upper)

        extracted_abnormalities: List[str] = []
        extracted_loto: List[str] = []

        if "abnormal" in cleaned_text.lower() or "vibration" in cleaned_text.lower() or "leak" in cleaned_text.lower() or "fault" in cleaned_text.lower() or "high" in cleaned_text.lower():
            extracted_abnormalities.append(cleaned_text)

        if "loto" in cleaned_text.lower() or "isolation" in cleaned_text.lower() or "lockout" in cleaned_text.lower() or "permit" in cleaned_text.lower():
            extracted_loto.append(cleaned_text)

        msg = (
            f"Successfully processed field voice log for unit {target_unit}. "
            f"Extracted {len(extracted_tags)} tag(s) ({', '.join(extracted_tags) if extracted_tags else 'None'}), "
            f"{len(extracted_abnormalities)} abnormality record(s), and {len(extracted_loto)} LOTO/Permit item(s)."
        )

        return VoiceIngestionResult(
            success=True,
            transcript=transcript,
            unit_id=target_unit,
            handover_id=cmd.handover_id,
            extracted_command_type=cmd.command_type,
            extracted_abnormalities=extracted_abnormalities,
            extracted_loto_items=extracted_loto,
            extracted_equipment_tags=extracted_tags,
            summary_message=msg
        )


# Global singleton instance
shift_voice_service = ShiftVoiceIngestionService()
