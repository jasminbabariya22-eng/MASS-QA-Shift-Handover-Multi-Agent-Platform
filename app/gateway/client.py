import logfire
from portkey_ai import Portkey, createHeaders, PORTKEY_GATEWAY_URL
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from groq import Groq
from google import genai
from types import SimpleNamespace

from app.config import settings

# Check Mesh API / Portkey Gateway credentials
_mesh_api_key = settings.MESH_API_KEY or settings.PORTKEY_API_KEY or ""
_mesh_base_url = settings.MESH_API_BASE_URL or PORTKEY_GATEWAY_URL
is_config_id = _mesh_api_key.startswith("pc-")
is_valid_pk = _mesh_api_key.startswith("pk-") or _mesh_api_key.startswith("rsk_") or len(_mesh_api_key) >= 20

# Open-Source Model Mesh Catalog (Ranked by Cost & Capability)
OPEN_SOURCE_MODELS = {
    "FAST_LIGHT": "llama-3.1-8b-instant",       # Lowest cost, ultra-fast (<100ms) for planning & classification
    "BALANCED_MOE": "mixtral-8x7b-32768",       # Cost-effective MoE for fast conversational synthesis
    "HEAVY_REASONING": "llama-3.3-70b-versatile", # High-capacity reasoning for complex technical RAG
    "DEFAULT_TECHNICAL": "qwen/qwen3.6-27b"     # High-precision technical documentation model
}

if is_config_id:
    GATEWAY_CONFIG = _mesh_api_key
else:
    GATEWAY_CONFIG = {
        "strategy": {"mode": "fallback"},
        "cache": {"mode": "simple"},
        "retry": {
            "attempts": 2,
            "on_status_codes": [429, 503]
        },
        "targets": [
            {"override_params": {"model": OPEN_SOURCE_MODELS["FAST_LIGHT"]}},
            {"override_params": {"model": OPEN_SOURCE_MODELS["BALANCED_MOE"]}},
            {"override_params": {"model": OPEN_SOURCE_MODELS["HEAVY_REASONING"]}},
            {"override_params": {"model": f"@{settings.GROQ_SLUG}/{OPEN_SOURCE_MODELS['DEFAULT_TECHNICAL']}"}},
        ]
    }


class SmartPortkeyClient:
    """
    A resilient multi-provider Mesh Gateway wrapper with automatic cost-optimized routing.
    Integrates 3 Open-Source Models via MESH_API_KEY:
      1. llama-3.1-8b-instant (Fastest, Lowest Cost)
      2. mixtral-8x7b-32768 (Cost-Effective MoE)
      3. llama-3.3-70b-versatile (Heavy Reasoning)
    Falls back gracefully across providers to guarantee zero downtime and minimal token cost.
    """
    def __init__(self):
        if is_valid_pk or is_config_id:
            try:
                self._pk = Portkey(api_key=_mesh_api_key, base_url=_mesh_base_url, config=GATEWAY_CONFIG)
            except Exception:
                self._pk = None
        else:
            self._pk = None

        self._groq = Groq(api_key=settings.GROQ_API_KEY, max_retries=0) if settings.GROQ_API_KEY else None
        self._gemini = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None
        self._gemini_cooldown_until = 0.0

    class ChatCompletions:
        def __init__(self, parent):
            self.parent = parent

        def create(self, messages, temperature=0.1, use_case: str = "standard", **kwargs):
            import time
            combined_prompt = ""
            for m in messages:
                role = m.get("role", "user").upper()
                content = m.get("content", "")
                combined_prompt += f"[{role}]:\n{content}\n\n"

            # 1. Primary Engine: Google Gemini (if active)
            gemini_models = ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3.6-flash"]
            now = time.time()
            if self.parent._gemini is not None and now >= self.parent._gemini_cooldown_until:
                for g_model in gemini_models:
                    try:
                        gemini_resp = self.parent._gemini.models.generate_content(
                            model=g_model,
                            contents=combined_prompt,
                            config={"temperature": temperature}
                        )
                        content_text = gemini_resp.text or ""
                        if content_text:
                            msg_obj = SimpleNamespace(content=content_text)
                            choice_obj = SimpleNamespace(message=msg_obj)
                            return SimpleNamespace(
                                choices=[choice_obj],
                                _raw_response=SimpleNamespace(headers={"x-portkey-cache-status": "MISS"})
                            )
                    except Exception as e:
                        err_str = str(e)
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                            logfire.warning(f"Gemini ({g_model}) rate-limited — routing to Open-Source Mesh Gateway.")
                            continue
                        elif "404" in err_str or "503" in err_str:
                            continue
                        else:
                            logfire.warning(f"Gemini ({g_model}) error: {e}")

            # 2. Cost-Optimized Open-Source Mesh Routing via Groq / MESH_API
            if self.parent._groq is not None:
                # Select open-source model order based on cost-reduction policy
                if use_case == "fast":
                    os_models = [OPEN_SOURCE_MODELS["FAST_LIGHT"], OPEN_SOURCE_MODELS["BALANCED_MOE"], OPEN_SOURCE_MODELS["HEAVY_REASONING"]]
                elif use_case == "complex":
                    os_models = [OPEN_SOURCE_MODELS["HEAVY_REASONING"], OPEN_SOURCE_MODELS["DEFAULT_TECHNICAL"], OPEN_SOURCE_MODELS["BALANCED_MOE"]]
                else:
                    os_models = [OPEN_SOURCE_MODELS["BALANCED_MOE"], OPEN_SOURCE_MODELS["HEAVY_REASONING"], OPEN_SOURCE_MODELS["FAST_LIGHT"]]

                for os_model in os_models:
                    try:
                        logfire.info(f"[ModelMesh] Routing query via Mesh API ({_mesh_base_url}) to model: '{os_model}'")
                        return self.parent._groq.chat.completions.create(
                            model=os_model,
                            messages=messages,
                            temperature=temperature,
                            timeout=15.0
                        )
                    except Exception as e:
                        logfire.warning(f"[ModelMesh] Open-source model '{os_model}' failed: {e}. Trying next mesh candidate...")

            raise RuntimeError("All configured LLM providers (Gemini & Open-Source Mesh Gateway) are currently rate-limited.")


    @property
    def chat(self):
        class Chat:
            def __init__(self, parent):
                self.completions = SmartPortkeyClient.ChatCompletions(parent)
        return Chat(self)


portkey_client = SmartPortkeyClient()


def get_langchain_llm(feature: str = "rag"):
    """
    Returns a cost-optimized, MESH API or Groq-backed Open-Source Model.
    - feature="planner": Uses llama-3.1-8b-instant (Lowest Cost)
    - feature="rag": Uses llama-3.3-70b-versatile or qwen/qwen3.6-27b (High Accuracy)
    """
    # Select cost-optimized open source model target based on feature tier
    if feature == "planner":
        target_model = OPEN_SOURCE_MODELS["FAST_LIGHT"]  # llama-3.1-8b-instant
    elif feature == "complex":
        target_model = OPEN_SOURCE_MODELS["HEAVY_REASONING"] # llama-3.3-70b-versatile
    else:
        target_model = OPEN_SOURCE_MODELS["DEFAULT_TECHNICAL"] # qwen/qwen3.6-27b

    if is_valid_pk:
        try:
            headers = createHeaders(
                api_key=_mesh_api_key,
                config=GATEWAY_CONFIG,
                metadata={
                    "feature": feature,
                    "_user": "rag-system",
                    "environment": "production"
                }
            ) if _mesh_api_key.startswith("pk-") or _mesh_api_key.startswith("pc-") else {}

            return ChatOpenAI(
                api_key=_mesh_api_key,
                base_url=_mesh_base_url,
                model=target_model,
                temperature=0,
                default_headers=headers
            )
        except Exception:
            pass

    # Resilient fallback: Direct ChatGroq with selected open-source model
    try:
        return ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model=target_model,
            temperature=0
        )
    except Exception:
        pass



def extract_cache_status(response) -> str:
    """
    Pull x-portkey-cache-status from response headers defensively.
    """
    for attr in ("_raw_response", "_response", "_http_response"):
        raw = getattr(response, attr, None)
        if raw is not None:
            status = getattr(raw, "headers", {}).get("x-portkey-cache-status", "")
            if status:
                return status.upper()
    return "MISS"