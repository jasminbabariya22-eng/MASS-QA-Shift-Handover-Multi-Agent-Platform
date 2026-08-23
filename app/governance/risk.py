import re
from typing import Optional, Dict, Any
import logfire

from app.governance.contracts import RiskLevel


class RiskClassifier:
    """
    Centralized, deterministic 4-tier risk classification engine.
    Ensures consistent risk evaluation across all multi-agent domains.
    """

    CRITICAL_PATTERNS = [
        r"\b(?:turn|switch|shut)\s*(?:off|down)\b",
        r"\b(?:open|close)\s+(?:the\s+)?(?:control\s+|isolation\s+)?valve\b",
        r"\btrip\b.*?\b(?:compressor|pump|turbine|unit|boiler|furnace|reactor|system|[A-Z]{1,3}-?\d{2,4})\b",
        r"\bbypass\b.*?\b(?:esd|sis|interlock|safety|alarm)\b",
        r"\boverride\b.*?\b(?:alarm|interlock|safety|trip|setpoint)\b",
        r"\bchange\s+setpoint\b",
        r"\bstart\s+(?:the\s+)?(?:motor|pump|compressor|generator)\s+remotely\b",
        r"\bpurge\s+(?:the\s+)?vessel\b",
        r"\bdepressurize\s+(?:the\s+)?system\b",
        r"\bdisable\s+(?:the\s+)?(?:safety|alarm|interlock|trip)\b"
    ]

    HIGH_RISK_ACTIONS = {
        "SUBMIT",
        "SUBMIT_HANDOVER",
        "APPROVE",
        "APPROVE_HANDOVER",
        "REJECT",
        "REJECT_HANDOVER",
        "RETURN",
        "RETURN_HANDOVER",
        "ACKNOWLEDGE",
        "ACKNOWLEDGE_HANDOVER",
        "ACKNOWLEDGE_SAFETY_ITEM",
        "CHANGE_CUSTODY",
        "OVERRIDE_SAFETY"
    }

    MEDIUM_RISK_ACTIONS = {
        "CREATE",
        "CREATE_HANDOVER",
        "CREATE_DRAFT",
        "EDIT",
        "EDIT_HANDOVER",
        "SAVE",
        "SAVE_DRAFT",
        "ADD_OBSERVATION",
        "UPDATE_DRAFT"
    }

    LOW_RISK_ACTIONS = {
        "GET",
        "GET_HANDOVER",
        "LIST",
        "LIST_HANDOVERS",
        "READ",
        "READ_LOOP",
        "READ_INSTRUMENT",
        "SOP_LOOKUP",
        "TECHNICAL_QA",
        "SEARCH",
        "GENERAL_QA",
        "SUMMARY"
    }

    def __init__(self):
        self._critical_regex = re.compile("|".join(self.CRITICAL_PATTERNS), re.IGNORECASE)

    def classify(
        self,
        action: Optional[str] = None,
        message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> RiskLevel:
        """
        Evaluate operation and determine risk tier: LOW, MEDIUM, HIGH, or CRITICAL.
        """
        # 1. Check for Critical Physical Plant Control
        if message and self._critical_regex.search(message):
            logfire.warning(f"[RiskClassifier] Classified as CRITICAL: '{message[:60]}'")
            return RiskLevel.CRITICAL

        # 2. Check Action Classification
        act = (action or "").strip().upper()
        if act in self.HIGH_RISK_ACTIONS:
            return RiskLevel.HIGH

        if act in self.MEDIUM_RISK_ACTIONS:
            # Check if payload contains safety-critical changes (elevates to HIGH)
            if payload and (payload.get("safety_items") or payload.get("has_safety_critical_deviation")):
                logfire.info(f"[RiskClassifier] Elevated MEDIUM action '{act}' to HIGH due to safety-critical items.")
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        if act in self.LOW_RISK_ACTIONS:
            return RiskLevel.LOW

        # 3. Message-based fallback classification
        if message:
            msg_lower = message.lower()
            if any(w in msg_lower for w in ["submit handover", "approve handover", "reject handover", "acknowledge handover", "accept handover"]):
                return RiskLevel.HIGH
            if any(w in msg_lower for w in ["create handover", "draft handover", "add note", "update note"]):
                return RiskLevel.MEDIUM

        return RiskLevel.LOW


# Global Risk Classifier Singleton
risk_classifier = RiskClassifier()
