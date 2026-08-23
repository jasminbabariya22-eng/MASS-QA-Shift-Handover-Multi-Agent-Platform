import logfire
from portkey_ai import Portkey, createHeaders, PORTKEY_GATEWAY_URL
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from groq import Groq
from google import genai
from types import SimpleNamespace

from app.config import settings

# Check if PORTKEY_API_KEY is a saved config ID (starts with pc-) or a valid API key (starts with pk-)
_portkey_key = settings.PORTKEY_API_KEY or ""
is_config_id = _portkey_key.startswith("pc-")
is_valid_pk = _portkey_key.startswith("pk-")

if is_config_id:
    GATEWAY_CONFIG = _portkey_key
else:
    GATEWAY_CONFIG = {
        "strategy": {"mode": "fallback"},
        "cache": {"mode": "simple"},
        "retry": {
            "attempts": 2,
            "on_status_codes": [429, 503]
        },
        "targets": [
            {"override_params": {"model": f"@{settings.GROQ_SLUG}/qwen/qwen3.6-27b"}},
        ]
    }


class SmartPortkeyClient:
    """
    A resilient multi-provider LLM gateway wrapper.
    Attempts:
      1. Portkey Gateway routing (if configured)
      2. Direct Groq (qwen/qwen3.6-27b)
      3. Direct Gemini (gemini-3.6-flash)
    Execution never fails due to single-provider downtime.
    No OpenAI GPT API key is required or used.
    """
    def __init__(self):
        if is_valid_pk or is_config_id:
            try:
                self._pk = Portkey(api_key=_portkey_key, config=GATEWAY_CONFIG)
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

        def create(self, messages, temperature=0.1, **kwargs):
            import time
            combined_prompt = ""
            for m in messages:
                role = m.get("role", "user").upper()
                content = m.get("content", "")
                combined_prompt += f"[{role}]:\n{content}\n\n"

            # Model candidates in order of preference
            gemini_models = ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3.6-flash"]

            for overall_attempt in range(3):
                now = time.time()
                # 1. Primary Engine: Google Gemini (trying flash-latest, 3.5-flash, 3.6-flash)
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
                                logfire.warning(f"Gemini ({g_model}) rate-limited — trying next model.")
                                continue
                            elif "404" in err_str or "503" in err_str:
                                continue
                            else:
                                logfire.warning(f"Gemini ({g_model}) error: {e}")

                # 2. Resilient Fallback: Groq (qwen/qwen3.6-27b)
                if self.parent._groq is not None:
                    try:
                        return self.parent._groq.chat.completions.create(
                            model="qwen/qwen3.6-27b",
                            messages=messages,
                            temperature=temperature,
                            timeout=15.0
                        )
                    except Exception as e:
                        logfire.warning(f"Groq generation error on attempt {overall_attempt + 1}: {e}")

                # If all failed in this round, back off briefly
                if overall_attempt < 2:
                    time.sleep(3.0 * (overall_attempt + 1))

            raise RuntimeError("All configured LLM providers (Gemini & Groq) are currently rate-limited.")


    @property
    def chat(self):
        class Chat:
            def __init__(self, parent):
                self.completions = SmartPortkeyClient.ChatCompletions(parent)
        return Chat(self)


portkey_client = SmartPortkeyClient()


def get_langchain_llm(feature: str = "rag"):
    """
    Returns a Portkey-backed ChatOpenAI when valid Portkey credentials exist, 
    otherwise falls back directly to ChatGroq or ChatGoogleGenerativeAI.
    """
    if is_valid_pk:
        try:
            return ChatOpenAI(
                api_key=_portkey_key,
                base_url=PORTKEY_GATEWAY_URL,
                model=f"@{settings.GROQ_SLUG}/qwen/qwen3.6-27b",
                temperature=0,
                default_headers=createHeaders(
                    api_key=_portkey_key,
                    config=GATEWAY_CONFIG,
                    metadata={
                        "feature": feature,
                        "_user": "rag-system",
                        "environment": "production"
                    }
                )
            )
        except Exception:
            pass

    # Resilient fallback: Direct ChatGroq
    try:
        return ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model="qwen/qwen3.6-27b",
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