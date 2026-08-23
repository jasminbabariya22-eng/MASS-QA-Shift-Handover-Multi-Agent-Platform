import re
from typing import Optional, List
import logfire

from app.agents.contracts import (
    AgentIntent,
    RiskLevel,
    RoutingResult,
    RequestContext
)


class IntentRouter:
    """
    Hybrid Intent and Safety Router for the Multi-Agent Orchestration Layer.
    
    Responsibilities:
    1. Safety & High-Risk Plant Control Filter (CRITICAL risk guardrail)
    2. Multi-Agent Request Classification (Handover + SOP Retrieval)
    3. Shift Handover Domain Intent Classification
    4. General Greetings / Capabilities Detection
    5. Ambiguity & Clarification Detection
    6. Technical QA Routing (Default RAG Path)
    """

    # High-risk physical plant / SCADA / DCS control commands (Safety Interlock)
    HIGH_RISK_PATTERNS = [
        r"\b(?:turn|switch|shut)\s*(?:off|down)\b",
        r"\b(?:open|close)\s+(?:the\s+)?(?:control\s+|isolation\s+)?valve\b",
        r"\btrip\b.*?\b(?:compressor|pump|turbine|unit|boiler|furnace|reactor|system|[A-Z]{1,3}-?\d{2,4})\b",
        r"\bbypass\b.*?\b(?:esd|sis|interlock|safety|alarm)\b",
        r"\boverride\b.*?\b(?:alarm|interlock|safety|trip|setpoint)\b",
        r"\bchange\s+setpoint\b",
        r"\bstart\s+(?:the\s+)?(?:motor|pump|compressor|generator)\s+remotely\b",
        r"\bpurge\s+(?:the\s+)?vessel\b",
        r"\bdepressurize\s+(?:the\s+)?system\b",
    ]

    # Shift Handover operational terms
    SHIFT_PATTERNS = [
        r"\bshift\b",
        r"\bhandover\b",
        r"\bshift\s*handover\b",
        r"\boperator\s*handover\b",
        r"\bshift\s*log\b",
        r"\bshift\s*notes\b",
        r"\bshift\s*report\b",
        r"\boutgoing\s*shift\b",
        r"\bincoming\s*shift\b",
        r"\bshift\s*status\b",
        r"\bshift\s*summary\b",
        r"\bturnover\b",
        r"\bhand\s*over\b",
        r"\bnight\s*shift\b",
        r"\bday\s*shift\b",
        r"\bshift\s*change\b",
        r"\bunresolved\s*actions?\b",
        r"\bcarried?\s*forward\b",
        r"\bloto\b",
        r"\bsafety\s*items?\b",
        r"\baudit\s*(?:trail|history|log)\b",
    ]

    # Loop Engineering & Instrumentation patterns
    LOOP_PATTERNS = [
        r"\bloop\b",
        r"\bloop\s*drawing\b",
        r"\bloop\s*diagram\b",
        r"\bsignal\s*path\b",
        r"\bjunction\s*box\b",
        r"\bjb-?\d+\b",
        r"\bmarshalling\b",
        r"\bio\s*(?:channel|card|list|mapping|assignment)\b",
        r"\bdcs\s*input\b",
        r"\bdcs\s*output\b",
        r"\binstrument\s*datasheet\b",
        r"\binstrument\s*index\b",
        r"\bcable\s*schedule\b",
        r"\btermination\s*drawing\b",
        r"\bcontrol\s*loop\b",
        r"\bsetpoint\b",
        r"\balarm\s*(?:setpoint|limit|config|configuration|schedule)\b",
        r"\btransmitter\b",
    ]

    # Technical knowledge / SOP retrieval keywords
    PROCEDURE_PATTERNS = [
        r"\bprocedure\b",
        r"\bsop\b",
        r"\boperating\s*manual\b",
        r"\bguideline\b",
        r"\bmanual\b",
        r"\bchecklist\b",
        r"\bwork\s*instruction\b",
        r"\bhow\s*to\b",
        r"\bwhat\s*is\b",
        r"\bexplain\b",
        r"\brestart\s*procedure\b",
        r"\bstartup\s*procedure\b",
    ]

    # General system greetings / overview
    GENERAL_PATTERNS = [
        r"^(?:hi|hello|hey|greetings|good\s*(?:morning|afternoon|evening))\b",
        r"\bwhat\s*can\s*you\s*do\b",
        r"\bwho\s*are\s*you\b",
        r"\bhelp\b",
    ]

    def __init__(self):
        self._high_risk_regex = re.compile("|".join(self.HIGH_RISK_PATTERNS), re.IGNORECASE)
        self._shift_regex = re.compile("|".join(self.SHIFT_PATTERNS), re.IGNORECASE)
        self._loop_regex = re.compile("|".join(self.LOOP_PATTERNS), re.IGNORECASE)
        self._procedure_regex = re.compile("|".join(self.PROCEDURE_PATTERNS), re.IGNORECASE)
        self._general_regex = re.compile("|".join(self.GENERAL_PATTERNS), re.IGNORECASE)

    def route(self, message: str, context: Optional[RequestContext] = None) -> RoutingResult:
        """
        Evaluate user message and return a strongly-typed RoutingResult.
        """
        cleaned = message.strip()
        if not cleaned:
            return RoutingResult(
                intent=AgentIntent.UNKNOWN,
                confidence=0.0,
                reason="Empty query provided.",
                target_agents=["qa_technical_agent"],
                requires_clarification=True,
                risk_level=RiskLevel.LOW
            )

        # 1. Explicit Override in RequestContext metadata
        if context and context.metadata.get("forced_intent"):
            forced = str(context.metadata.get("forced_intent")).upper()
            if forced in ["SHIFT", "SHIFT_HANDOVER"]:
                return RoutingResult(
                    intent=AgentIntent.SHIFT,
                    confidence=1.0,
                    reason="Forced intent via context metadata.",
                    target_agents=["shift_handover_agent"],
                    requires_clarification=False,
                    risk_level=RiskLevel.LOW
                )
            elif forced in ["LOOP", "LOOP_ENGINEERING"]:
                return RoutingResult(
                    intent=AgentIntent.LOOP_ENGINEERING,
                    confidence=1.0,
                    reason="Forced intent via context metadata.",
                    target_agents=["loop_engineering_agent"],
                    requires_clarification=False,
                    risk_level=RiskLevel.LOW
                )
            elif forced == "QA":
                return RoutingResult(
                    intent=AgentIntent.QA,
                    confidence=1.0,
                    reason="Forced intent via context metadata.",
                    target_agents=["qa_technical_agent"],
                    requires_clarification=False,
                    risk_level=RiskLevel.LOW
                )

        # 2. Safety Interlock: High-Risk Autonomous Physical Plant Control
        if self._high_risk_regex.search(cleaned):
            logfire.warning(f"High-Risk Plant Control request detected: '{cleaned[:60]}'")
            return RoutingResult(
                intent=AgentIntent.HIGH_RISK,
                confidence=1.0,
                reason="Plant physical control or equipment manipulation is safety-restricted.",
                target_agents=[],
                requires_clarification=False,
                risk_level=RiskLevel.CRITICAL
            )

        has_shift = bool(self._shift_regex.search(cleaned))
        has_loop = bool(self._loop_regex.search(cleaned))
        has_procedure = bool(self._procedure_regex.search(cleaned))

        # 3. Multi-Agent Intent Detection (Handover update + Loop/Knowledge retrieval)
        if has_shift and (has_procedure or has_loop):
            partner_agent = "loop_engineering_agent" if has_loop else "qa_technical_agent"
            logfire.info(f"Router matched MULTI_AGENT intent for query: '{cleaned[:50]}...'")
            return RoutingResult(
                intent=AgentIntent.MULTI_AGENT,
                confidence=0.95,
                reason="Query requires both Shift Handover logging and Technical Engineering/QA lookup.",
                target_agents=["shift_handover_agent", partner_agent],
                requires_clarification=False,
                risk_level=RiskLevel.LOW
            )

        # 4. Loop Engineering Domain
        if has_loop:
            logfire.info(f"Router matched LOOP_ENGINEERING intent for query: '{cleaned[:50]}...'")
            return RoutingResult(
                intent=AgentIntent.LOOP_ENGINEERING,
                confidence=0.95,
                reason="Matched instrumentation and control loop engineering query.",
                target_agents=["loop_engineering_agent"],
                requires_clarification=False,
                risk_level=RiskLevel.LOW
            )

        # 5. Shift Handover Domain
        if has_shift:
            logfire.info(f"Router matched SHIFT intent for query: '{cleaned[:50]}...'")
            return RoutingResult(
                intent=AgentIntent.SHIFT,
                confidence=0.95,
                reason="Matched operational shift/handover terminology.",
                target_agents=["shift_handover_agent"],
                requires_clarification=False,
                risk_level=RiskLevel.LOW
            )

        # 6. General Greetings / System Inquiry
        if self._general_regex.search(cleaned) and len(cleaned.split()) <= 6:
            return RoutingResult(
                intent=AgentIntent.GENERAL,
                confidence=0.90,
                reason="General conversational greeting or capability inquiry.",
                target_agents=["qa_technical_agent"],
                requires_clarification=False,
                risk_level=RiskLevel.LOW
            )

        # 6. Ambiguous / Underspecified Equipment Inquiries
        # Example: "Tell me about C-101." or "C-101" without operational or procedural context
        equipment_tag_match = re.fullmatch(r"(?:tell\s+me\s+about\s+)?([A-Z]{1,3}-?\d{2,4}[A-Z]?)\.?", cleaned, re.IGNORECASE)
        if equipment_tag_match and not has_procedure and not has_shift:
            tag = equipment_tag_match.group(1).upper()
            return RoutingResult(
                intent=AgentIntent.UNKNOWN,
                confidence=0.40,
                reason=f"Ambiguous reference to equipment tag '{tag}'.",
                target_agents=["qa_technical_agent"],
                requires_clarification=True,
                risk_level=RiskLevel.LOW
            )

        # 7. Default to Technical QA (Hybrid Retrieval V2 + Grounded RAG)
        return RoutingResult(
            intent=AgentIntent.QA,
            confidence=0.95,
            reason="Technical query routed to Knowledge Retrieval & Grounding QA Agent.",
            target_agents=["qa_technical_agent"],
            requires_clarification=False,
            risk_level=RiskLevel.LOW
        )


# Global Intent Router Singleton
intent_router = IntentRouter()
