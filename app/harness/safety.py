import re
from typing import Tuple, Optional
import logfire

from app.harness.contracts import HarnessPolicyDecision


class HarnessSafetyPolicy:
    """
    Deterministic Safety Guardrail Policy.
    Acts as an upstream security boundary prohibiting physical plant manipulation.
    """

    PROHIBITED_COMMANDS = [
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

    def __init__(self):
        self._regex = re.compile("|".join(self.PROHIBITED_COMMANDS), re.IGNORECASE)

    def evaluate(self, message: str) -> Tuple[HarnessPolicyDecision, Optional[str], Optional[str]]:
        """
        Evaluate safety policy against user request.
        Returns (decision, reason_code, message).
        """
        cleaned = message.strip()
        if self._regex.search(cleaned):
            logfire.warning(f"[HarnessSafety] Refusal triggered for command: '{cleaned[:60]}'")
            refusal_msg = (
                "⚠️ **Safety Policy Restriction**: Physical equipment control, remote valve operation, "
                "alarm override, or trip commands cannot be executed by the AI assistant. "
                "Please perform physical plant operations in accordance with standard operating procedures and control room protocols."
            )
            return (
                HarnessPolicyDecision.DENY,
                "PHYSICAL_CONTROL_PROHIBITED",
                refusal_msg
            )

        return (HarnessPolicyDecision.ALLOW, None, None)


# Global Safety Policy Singleton
safety_policy = HarnessSafetyPolicy()
