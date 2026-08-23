import logfire
from app.agents.state import AgentState
from app.services.retrieval.hybrid import retrieve
from app.services.generation.context_builder import ContextBuilder

def retrieve_node(state: AgentState):
    """
    Performs Hybrid Retrieval V2 (Dense + BM25 + RRF + FlashRank) for technical queries.
    """
    query = state["current_query"]

    with logfire.span("🔍 Hybrid Retrieval V2 Node", query=query):
        candidates = retrieve(query, top_k=5, mode="auto")
        logfire.info(f"Retrieved {len(candidates)} candidates via Hybrid V2.")

        # Build structured context string preserving tables and provenance
        context_str, citations = ContextBuilder.build_context(candidates)

        formatted_docs = [
            f"SOURCE [{c.source_number}] {c.document_name} (Page: {c.page_number or 'N/A'}, Slide: {c.slide_number or 'N/A'}):\n{c.snippet}"
            for c in citations
        ]

    return {
        "documents": [context_str],
        "status": "Technical context retrieved via Hybrid V2.",
        "plan": state["plan"] + ["Context Retrieved via Hybrid V2"]
    }
