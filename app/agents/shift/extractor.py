import re
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone

from app.agents.shift.contracts import ShiftHandoverAction, ShiftType
from app.agents.shift.command import ShiftCommand, ShiftCommandType


class ShiftCommandExtractor:
    """
    Deterministic natural-language command extractor for the Shift Handover Agent.
    Parses intent, actions, unit codes, equipment tags, shift types, and reasons
    with sub-millisecond latency and zero LLM token overhead.
    """

    UNIT_REGEX = re.compile(r"\b(?:unit|area|plant)?\s*([A-Z]{2,4}-?[0-9]{3,4}|U-?[0-9]{3,4})\b", re.IGNORECASE)
    HANDOVER_NUM_REGEX = re.compile(r"\b(SHO-[0-9A-Z-]+)\b", re.IGNORECASE)
    EQUIPMENT_REGEX = re.compile(r"\b([PCEVKTX]-[0-9]{3,4}[A-Z]?|XV-[0-9]{3,4}|MOV-[0-9]{3,4})\b", re.IGNORECASE)
    PERMIT_REGEX = re.compile(r"\b(PTW-[0-9A-Z-]+)\b", re.IGNORECASE)
    DATE_REGEX = re.compile(r"\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b")

    def extract(self, query: str, context_metadata: Optional[Dict[str, Any]] = None) -> ShiftCommand:
        """
        Extract structured ShiftCommand from user query.
        """
        q = query.strip()
        q_lower = q.lower()
        meta = context_metadata or {}

        # 1. Extract Entities
        hnum_match = self.HANDOVER_NUM_REGEX.search(q)
        handover_number = hnum_match.group(1).upper() if hnum_match else meta.get("selected_handover_number")
        handover_id = meta.get("selected_handover_id")

        unit_match = self.UNIT_REGEX.search(q)
        unit_id = unit_match.group(1).upper() if unit_match else meta.get("selected_unit_id")
        if unit_id and not unit_id.startswith("U-") and not "-" in unit_id and unit_id.startswith("U"):
            unit_id = f"U-{unit_id[1:]}"

        eq_match = self.EQUIPMENT_REGEX.search(q)
        equipment_tag = eq_match.group(1).upper() if eq_match else None

        permit_match = self.PERMIT_REGEX.search(q)
        permit_id = permit_match.group(1).upper() if permit_match else None

        date_match = self.DATE_REGEX.search(q)
        shift_date = date_match.group(1) if date_match else datetime.now(timezone.utc).strftime("%Y-%m-%d")

        shift_type = ShiftType.DAY
        if "night" in q_lower:
            shift_type = ShiftType.NIGHT
        elif "swing" in q_lower:
            shift_type = ShiftType.SWING

        # Extract Reason if present
        reason = None
        reason_match = re.search(r"(?:reason|because|due to|with comment)[:\s]+(.+)", q, re.IGNORECASE)
        if reason_match:
            reason = reason_match.group(1).strip()

        # 2. Check for Ambiguous entity-only queries
        if q in ["C-101", "P-101", "CDU-101"] or len(q.split()) == 1 and not any(w in q_lower for w in ["list", "status", "audit", "draft", "cancel", "submit", "approve"]):
            return ShiftCommand(
                command_type=ShiftCommandType.AMBIGUOUS,
                requires_clarification=True,
                clarification_prompt=f"You mentioned `{q}`. Would you like to view its operational status, add it as a safety observation, or retrieve its SOP?",
                raw_query=q
            )

        # 3. Classify Command Types

        # A. Safety queries & management
        if any(k in q_lower for k in ["loto", "active permit", "safety item", "unacknowledged", "esd bypass", "safety status"]):
            if any(k in q_lower for k in ["add", "log", "record"]):
                cat = "LOTO" if "loto" in q_lower else ("PERMIT_TO_WORK" if "permit" in q_lower else "SAFETY_OBSERVATION")
                return ShiftCommand(
                    command_type=ShiftCommandType.ADD_SAFETY_ITEM,
                    unit_id=unit_id,
                    handover_number=handover_number,
                    safety_category=cat,
                    equipment_tag=equipment_tag or "GENERAL",
                    description=q,
                    raw_query=q
                )
            if any(k in q_lower for k in ["acknowledge", "ack"]):
                return ShiftCommand(
                    command_type=ShiftCommandType.ACKNOWLEDGE_SAFETY_ITEM,
                    unit_id=unit_id,
                    handover_number=handover_number,
                    equipment_tag=equipment_tag,
                    raw_query=q
                )
            return ShiftCommand(
                command_type=ShiftCommandType.GET_SAFETY_STATUS,
                unit_id=unit_id,
                handover_number=handover_number,
                raw_query=q
            )

        # Quality Gate Check Queries
        if any(k in q_lower for k in ["quality", "completeness", "score", "quality score", "check draft"]):
            return ShiftCommand(
                command_type=ShiftCommandType.CHECK_QUALITY,
                handover_number=handover_number,
                unit_id=unit_id,
                raw_query=q
            )

        # Voice Log Ingestion Queries
        if any(k in q_lower for k in ["voice note", "voice log", "audio note", "spoken log", "field recording"]):
            return ShiftCommand(
                command_type=ShiftCommandType.PROCESS_VOICE_NOTE,
                unit_id=unit_id,
                description=q,
                raw_query=q
            )

        # B. Audit history queries
        if any(k in q_lower for k in ["audit", "history", "who approved", "what changed", "audit log"]):

            return ShiftCommand(
                command_type=ShiftCommandType.GET_AUDIT_HISTORY,
                handover_number=handover_number,
                unit_id=unit_id,
                raw_query=q
            )

        # C. Create Handover
        if any(k in q_lower for k in ["create", "start", "new handover", "prepare handover", "initiate"]):
            if not unit_id:
                return ShiftCommand(
                    command_type=ShiftCommandType.CREATE_HANDOVER,
                    requires_clarification=True,
                    clarification_prompt="Which plant unit would you like to create the shift handover for? (e.g. Unit U-101, CDU-101)",
                    raw_query=q
                )
            return ShiftCommand(
                command_type=ShiftCommandType.CREATE_HANDOVER,
                unit_id=unit_id,
                shift_type=shift_type,
                shift_date=shift_date,
                operational_summary=q,
                raw_query=q
            )

        # D. Workflow State Transitions
        if "approve" in q_lower:
            return ShiftCommand(
                command_type=ShiftCommandType.APPROVE_HANDOVER,
                action=ShiftHandoverAction.APPROVE,
                handover_number=handover_number,
                unit_id=unit_id,
                reason=reason,
                raw_query=q
            )

        if "review" in q_lower and not any(k in q_lower for k in ["schedules", "sop"]):
            return ShiftCommand(
                command_type=ShiftCommandType.REVIEW_HANDOVER,
                action=ShiftHandoverAction.REVIEW,
                handover_number=handover_number,
                unit_id=unit_id,
                raw_query=q
            )

        if "return" in q_lower:
            return ShiftCommand(
                command_type=ShiftCommandType.RETURN_HANDOVER,
                action=ShiftHandoverAction.RETURN,
                handover_number=handover_number,
                unit_id=unit_id,
                reason=reason,
                raw_query=q
            )

        if "reject" in q_lower:
            return ShiftCommand(
                command_type=ShiftCommandType.REJECT_HANDOVER,
                action=ShiftHandoverAction.REJECT,
                handover_number=handover_number,
                unit_id=unit_id,
                reason=reason,
                raw_query=q
            )

        if any(k in q_lower for k in ["acknowledge", "accept handover", "custody"]):
            return ShiftCommand(
                command_type=ShiftCommandType.ACKNOWLEDGE_HANDOVER,
                action=ShiftHandoverAction.ACKNOWLEDGE,
                handover_number=handover_number,
                unit_id=unit_id,
                raw_query=q
            )

        if "cancel" in q_lower:
            # Check if explicit confirmation
            is_confirmed = any(w in q_lower for w in ["yes", "confirm", "proceed"])
            return ShiftCommand(
                command_type=ShiftCommandType.CANCEL_HANDOVER,
                action=ShiftHandoverAction.CANCEL,
                handover_number=handover_number,
                unit_id=unit_id,
                reason=reason or ("Cancelled by operator request" if is_confirmed else None),
                requires_confirmation=not is_confirmed and not reason,
                confirmation_prompt=f"You are about to cancel this handover ({handover_number or unit_id or 'current draft'}). This action is irreversible. Would you like to proceed?",
                raw_query=q
            )

        if "submit" in q_lower:
            return ShiftCommand(
                command_type=ShiftCommandType.SUBMIT_HANDOVER,
                action=ShiftHandoverAction.SUBMIT,
                handover_number=handover_number,
                unit_id=unit_id,
                raw_query=q
            )

        # E. Update Draft / Add Observations
        if any(k in q_lower for k in ["add", "update", "note", "vibration", "abnormality", "summary"]):
            return ShiftCommand(
                command_type=ShiftCommandType.UPDATE_HANDOVER,
                action=ShiftHandoverAction.SAVE,
                handover_number=handover_number,
                unit_id=unit_id,
                updates={"notes": q},
                raw_query=q
            )

        # F. List / Get Queries
        if any(k in q_lower for k in ["list", "show pending", "all handovers", "pending handovers"]):
            return ShiftCommand(
                command_type=ShiftCommandType.LIST_HANDOVERS,
                unit_id=unit_id,
                raw_query=q
            )

        if any(k in q_lower for k in ["show", "get", "status", "current", "draft", "my draft"]):
            return ShiftCommand(
                command_type=ShiftCommandType.GET_HANDOVER,
                handover_number=handover_number,
                unit_id=unit_id,
                raw_query=q
            )

        # Default fallback
        return ShiftCommand(
            command_type=ShiftCommandType.GET_HANDOVER,
            unit_id=unit_id,
            handover_number=handover_number,
            raw_query=q
        )
