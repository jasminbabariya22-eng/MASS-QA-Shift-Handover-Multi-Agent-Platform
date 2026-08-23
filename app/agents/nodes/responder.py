import logfire
from app.agents.state import AgentState
from app.gateway import portkey_client, extract_cache_status
from app.services.generation.generator import SYSTEM_GROUNDING_PROMPT


def generate_node(state: AgentState):
    """
    Synthesizes a response using both Documentation Context AND Conversation History.
    Uses the native Portkey client (not LangChain) with fallback to direct Groq.
    """
    query = state["current_query"]

    history_str = ""
    for msg in state["messages"][:-1]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_str += f"{role}: {msg['content']}\n"

    user_msg = state["messages"][-1]["content"] if state["messages"] else ""

    if query == "CONVERSATIONAL":
        logfire.info("Generating conversational response using memory.")
        messages = [
            {"role": "system", "content": "You are a friendly and helpful MASS QA Technical Assistant. Answer conversationally using the provided history."},
            {"role": "user", "content": f"CONVERSATION HISTORY:\n{history_str}\n\nUSER MESSAGE:\n\"{user_msg}\""}
        ]
    else:
        logfire.info("Generating technical RAG response.")
        full_context = "\n\n".join(state["documents"])

        user_prompt = f"""RETRIEVED KNOWLEDGE BASE SOURCES:
{full_context}

CONVERSATION HISTORY:
{history_str}

USER QUESTION:
\"{user_msg}\""""

        messages = [
            {"role": "system", "content": SYSTEM_GROUNDING_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

    with logfire.span("✍️ LLM Synthesis"):
        try:
            response = portkey_client.chat.completions.create(
                messages=messages,
                temperature=0.1
            )
            content = response.choices[0].message.content
            cache_status = extract_cache_status(response)
            is_cache_hit = cache_status == "HIT"

            if is_cache_hit:
                logfire.info("⚡ Gateway Cache Hit — response served from Portkey cache.")
                plan_update = state["plan"] + ["Cache: Hit ⚡"]
                status = "Cache hit — instant response."
            else:
                logfire.info("✅ Response synthesised via LLM.")
                plan_update = state["plan"]
                status = "Response generated."

            return {
                "final_answer": content,
                "status": status,
                "plan": plan_update,
                "messages": [{"role": "assistant", "content": content}]
            }

        except Exception as e:
            logfire.error(f"LLM Generation failed: {e}")
            raise e
