import logfire
from langchain_groq import ChatGroq
from nemoguardrails import RailsConfig, LLMRails

from app.config import settings
from app.guardrails.colang_rules import COLANG_CONTENT, YAML_CONTENT, RAIL_INDICATORS


_rails: LLMRails | None = None

OFF_TOPIC_PATTERNS = [
    "recipe", "pizza", "fifa", "world cup", "cats and dogs", "poem", "tell me a joke",
    "capital of", "weather today", "dinner", "telescope to buy", "bypass enterprise firewall",
    "dan mode", "developer mode", "jailbreak", "ignore all previous", "song lyrics"
]


def initialize_rails() -> None:
    """
    Build the NeMo LLMRails singleton at app startup.
    Uses qwen/qwen3.6-27b on Groq for fast intent classification at the gate.
    """
    global _rails

    try:
        guard_llm = ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model="qwen/qwen3.6-27b",
            temperature=0,
            max_retries=0
        )

        config = RailsConfig.from_content(
            colang_content=COLANG_CONTENT,
            yaml_content=YAML_CONTENT
        )

        _rails = LLMRails(config, llm=guard_llm)
        logfire.info("🛡️ NeMo Guardrails initialised (qwen/qwen3.6-27b).")
    except Exception as e:
        logfire.warning(f"⚠️ NeMo Guardrails initialisation warning: {e}")
        _rails = None


DOMAIN_KEYWORDS = [
    "refin", "petroleum", "crude", "oil", "gas", "pipeline", "upstream", "downstream",
    "aramco", "marjan", "berri", "sulfur", "compressor", "blowdown", "cooling tower",
    "nsps", "epa", "pngrb", "nep", "kpmg", "ihs", "eia", "iea", "flare", "naphtha",
    "fcc", "hydrotreat", "catalytic", "distill", "coker", "ammonia", "methane",
    "turbin", "separator", "drilling", "well", "subsea", "capex", "opex", "brent",
    "wti", "barrel", "mb/d", "bcf", "lng", "lpg", "hazard", "safety", "standard",
    "regulation", "pressure", "temperature", "feedstock", "capacity", "cost", "trend",
    "governance", "chatham", "producer", "policy", "guideline", "emission", "standard",
    "report", "energy", "market", "forecast", "facility", "equipment", "operation",
    "procedure", "step", "unit", "system", "mass", "ors", "troubleshoot", "corrosion",
    "inspection", "flange", "valve", "heat exchanger", "maintenance", "diesel", "gasoline",
    "heavy fuel", "vacuum", "fractionator", "reboiler", "stripper", "amine", "sweetening"
]


GREETING_PATTERNS = [
    "hi", "hii", "hiii", "hello", "hey", "heyy", "greetings", "good morning", "good afternoon",
    "good evening", "who are you", "what can you do", "help me"
]

GREETING_RESPONSE = "Hello! I am the MASS QA Technical Intelligence Assistant. I can assist you with technical documentation, petroleum refining processes, equipment availability, operational workflows, and energy regulatory policies. How can I help you today?"


def guard(message: str) -> tuple[bool, str | None]:
    """
    Run a user message through the guardrails gate.

    Returns:
        (True,  rail_response) — a rail fired; return this response immediately,
                                skip the RAG pipeline entirely.
        (False, None)          — message is clean; proceed to RAG pipeline.
    """
    msg_lower = message.lower().strip()

    # 1. Fast-path greetings & introductory assistance
    if msg_lower in GREETING_PATTERNS or any(msg_lower.startswith(g + " ") for g in GREETING_PATTERNS if len(g) > 2):
        return True, GREETING_RESPONSE

    # 2. Fast-path refusal for known off-topic / jailbreak patterns
    if any(p in msg_lower for p in OFF_TOPIC_PATTERNS):
        refusal = "I can help with questions related to the MASS QA / ORS knowledge base, including product functionality, operational procedures, workflows, troubleshooting and technical documentation."
        return True, refusal

    # 3. Fast-path approval for known in-domain questions (zero LLM token consumption)
    if any(k in msg_lower for k in DOMAIN_KEYWORDS):
        return False, None


    if _rails is None:
        return False, None

    with logfire.span("🛡️ Guardrails Check"):
        try:
            result = _rails.generate(messages=[{"role": "user", "content": message}])
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            fired = any(indicator in content for indicator in RAIL_INDICATORS)

            if fired:
                logfire.info(f"🛡️ Guardrails fired | query='{message[:80]}'")
                return True, content

            logfire.info("✅ Guardrails passed.")
            return False, None
        except Exception as e:
            logfire.warning(f"⚠️ Guardrails evaluation warning ({e}) — passing to generation.")
            return False, None
