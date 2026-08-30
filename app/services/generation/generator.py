import time
import re
from typing import List, Dict, Any, Optional, Tuple
import logfire

from app.config import settings
from app.gateway.client import portkey_client, extract_cache_status
from app.services.cache import cache_service

from app.services.retrieval.models import RetrievalCandidate
from app.services.retrieval.query_router import QueryRouter, QueryAnalysisResult, QueryType
from app.services.retrieval.hybrid import retrieve, get_hybrid_retriever
from app.services.generation.models import SourceCitation, RAGResponse
from app.services.generation.context_builder import ContextBuilder
from app.services.generation.evidence_checker import EvidenceChecker, EvidenceAssessment


SYSTEM_GROUNDING_PROMPT = """You are the MASS QA Technical Intelligence Assistant, an enterprise AI assistant specializing in petroleum refining, process engineering, equipment SOPs, and operational workflows.

Formatting & Response Guidelines:
1. **Direct Executive Tone**: Answer directly, clearly, and professionally. NEVER begin answers with robotic disclaimers like "Based on the provided sources...", "According to the document...", or pedantic meta-notes like "(note: the sources do not explicitly use...)".
2. **Beautiful Markdown Layout**:
   - Structure answers into clean sections with descriptive subheadings (`### Summary`, `### Process Workflow`, `### Key Operating Parameters`).
   - Use bold text for key figures, equipment tags, and temperatures (e.g., **470 to 525°C**, **Pump P-101**, **Reactor Riser**).
   - Use numbered lists with clear step titles for sequential workflows.
3. **Grounding & Accuracy**:
   - Answer using facts stated in the PROVIDED RETRIEVED SOURCES.
   - Preserve numerical values, engineering units (°C, °F, psig), and dates EXACTLY as written.
   - If sources lack sufficient information, state clearly: "I don't have enough information in the available knowledge base to answer this confidently."
4. **Sleek In-Text Citations**:
   - Place source citations cleanly at the end of sentences or bullet points: `[Source 1: 5.1_petroleum_refining.pdf, Page 5]`.
   - Never fabricate citations or page numbers."""



class RAGAnswerGenerator:
    """
    Production RAG Answer Generation Engine with Multi-Layer Caching & Streaming.
    Coordinates Query Analysis -> Hybrid Retrieval V2 -> Evidence Verification ->
    Context Construction -> Grounded LLM Synthesis -> Citation Validation.
    """

    def __init__(self):
        self.hybrid_retriever = get_hybrid_retriever()

    def generate_answer(
        self,
        question: str,
        top_k: int = 5,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        use_cache: bool = True
    ) -> RAGResponse:
        t_start = time.time()
        thought_process = []
        latency_breakdown = {}

        # Layer A: Check Query Response Cache
        resp_cache_key = cache_service.make_response_key(question)
        if use_cache:
            cached_resp = cache_service.get(resp_cache_key)
            if cached_resp:
                try:
                    rag_resp = RAGResponse.model_validate(cached_resp)
                    rag_resp.latency_breakdown["total"] = time.time() - t_start
                    rag_resp.latency_breakdown["cache_lookup"] = time.time() - t_start
                    rag_resp.thought_process.append("⚡ Response served from Cache (Layer A HIT)")
                    return rag_resp
                except Exception as e:
                    logfire.warning(f"Failed to deserialize cached response ({e}).")

        # Stage 1: Query Analysis & Routing
        t_route_start = time.time()
        analysis = QueryRouter.analyze(question)
        t_route = time.time() - t_route_start
        latency_breakdown["routing"] = t_route
        thought_process.append(f"Query Classification: {analysis.query_type.value.upper()} (Routing Latency: {t_route:.4f}s)")

        # Stage 2: Hybrid Retrieval V2 (with Layer B Retrieval Cache)
        t_ret_start = time.time()
        ret_cache_key = cache_service.make_retrieval_key(question, top_k=top_k)
        candidates = None
        if use_cache:
            cached_cands = cache_service.get(ret_cache_key)
            if cached_cands:
                try:
                    candidates = [RetrievalCandidate.model_validate(c) for c in cached_cands]
                    thought_process.append(f"⚡ Retrieval candidates served from Cache (Layer B HIT: {len(candidates)} items)")
                except Exception:
                    candidates = None

        if candidates is None:
            candidates = self.hybrid_retriever.retrieve(question, top_k=top_k, mode="auto")
            if use_cache and candidates:
                cache_service.set(ret_cache_key, [c.model_dump() for c in candidates], ttl_seconds=settings.RETRIEVAL_CACHE_TTL_SECONDS)

        t_ret = time.time() - t_ret_start
        latency_breakdown["retrieval"] = t_ret
        thought_process.append(f"Retrieved {len(candidates)} candidates via Hybrid V2 (Latency: {t_ret:.4f}s)")

        # Stage 3: Evidence Quality & Sufficiency Check
        assessment = EvidenceChecker.evaluate_evidence(question, candidates, analysis)
        thought_process.append(f"Evidence Assessment: {assessment.confidence_level.upper()} ({assessment.reason})")

        if not assessment.is_sufficient:
            t_total = time.time() - t_start
            latency_breakdown["total"] = t_total
            resp = RAGResponse(
                question=question,
                answer="I don't have enough information in the available knowledge base to answer this confidently.",
                sources=[],
                query_type=analysis.query_type.value,
                retrieval_count=len(candidates),
                grounded=True,
                confidence="insufficient",
                thought_process=thought_process + ["Abstention triggered due to insufficient evidence."],
                latency_breakdown=latency_breakdown,
                status="insufficient_evidence"
            )
            if use_cache:
                cache_service.set(resp_cache_key, resp.model_dump(), ttl_seconds=settings.CACHE_TTL_SECONDS)
            return resp

        # Stage 4: Context Construction
        t_ctx_start = time.time()
        context_str, citations = ContextBuilder.build_context(candidates)
        t_ctx = time.time() - t_ctx_start
        latency_breakdown["context_building"] = t_ctx
        thought_process.append(f"Formatted context with {len(citations)} source blocks (Latency: {t_ctx:.4f}s)")

        # Stage 5: Prompt Assembly
        history_str = ""
        if conversation_history:
            history_blocks = []
            for msg in conversation_history[-4:]:  # last 4 turns max
                role = "User" if msg.get("role") == "user" else "Assistant"
                history_blocks.append(f"{role}: {msg.get('content', '')}")
            if history_blocks:
                history_str = "\nRelevant Conversation History:\n" + "\n".join(history_blocks) + "\n"

        user_prompt = f"""RETRIEVED KNOWLEDGE BASE SOURCES:
{context_str}
{history_str}
USER QUESTION:
"{question}"

Please provide a comprehensive, strictly grounded answer based ONLY on the sources above. Include precise [Source X: Document, Page Y] citations for all factual assertions."""

        # Stage 6: LLM Synthesis via Gateway
        t_llm_start = time.time()
        with logfire.span("✍️ Grounded LLM Generation", query=question, num_sources=len(citations)):
            try:
                response = portkey_client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": SYSTEM_GROUNDING_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.1
                )
                raw_answer = response.choices[0].message.content.strip()
                # Clean reasoning / chain-of-thought tags if emitted by reasoning models
                clean_answer = re.sub(r"<think>.*?</think>", "", raw_answer, flags=re.DOTALL).strip()
                if not clean_answer:
                    clean_answer = raw_answer

                cache_status = extract_cache_status(response)
                is_cache = (cache_status == "HIT")
                t_llm = time.time() - t_llm_start
                latency_breakdown["llm_generation"] = t_llm
                cache_flag = " [Cache: HIT ⚡]" if is_cache else ""
                thought_process.append(f"LLM Synthesis completed in {t_llm:.4f}s{cache_flag}")
            except Exception as e:
                logfire.error(f"LLM Generation failed: {e}")
                t_total = time.time() - t_start
                latency_breakdown["total"] = t_total
                return RAGResponse(
                    question=question,
                    answer="An error occurred while generating the answer from retrieved context. Please try again.",
                    sources=citations,
                    query_type=analysis.query_type.value,
                    retrieval_count=len(candidates),
                    grounded=False,
                    confidence="low",
                    thought_process=thought_process + [f"Error in LLM call: {str(e)}"],
                    latency_breakdown=latency_breakdown,
                    status="llm_error"
                )

        t_total = time.time() - t_start
        latency_breakdown["total"] = t_total

        # Filter citations to only those actually referenced or keep top retrieved
        used_citations = self._filter_used_citations(clean_answer, citations)

        rag_resp = RAGResponse(
            question=question,
            answer=clean_answer,
            sources=used_citations,
            query_type=analysis.query_type.value,
            retrieval_count=len(candidates),
            grounded=True,
            confidence=assessment.confidence_level,
            thought_process=thought_process,
            latency_breakdown=latency_breakdown,
            status="success"
        )

        # Store in Layer A Response Cache
        if use_cache and rag_resp.status == "success":
            cache_service.set(resp_cache_key, rag_resp.model_dump(), ttl_seconds=settings.CACHE_TTL_SECONDS)

        return rag_resp

    def stream_answer(
        self,
        question: str,
        top_k: int = 5,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        use_cache: bool = True
    ):
        """
        Server-Sent Events (SSE) streaming generator.
        Yields JSON event dictionaries:
        - {"type": "token", "content": "..."}
        - {"type": "citations", "citations": [...]}
        - {"type": "done", "metadata": {...}}
        """
        t_start = time.time()
        resp_cache_key = cache_service.make_response_key(question)

        # 1. Check Cache
        if use_cache:
            cached_resp = cache_service.get(resp_cache_key)
            if cached_resp:
                try:
                    rag_resp = RAGResponse.model_validate(cached_resp)
                    # Stream cached text in small realistic token chunks
                    words = rag_resp.answer.split(" ")
                    for i, w in enumerate(words):
                        chunk = w if i == len(words) - 1 else w + " "
                        yield {"type": "token", "content": chunk}
                        time.sleep(0.015)

                    yield {
                        "type": "citations",
                        "citations": [c.model_dump() for c in rag_resp.sources]
                    }
                    yield {
                        "type": "done",
                        "metadata": {
                            "cached": True,
                            "confidence": rag_resp.confidence,
                            "query_type": rag_resp.query_type,
                            "total_latency_ms": round((time.time() - t_start) * 1000, 2)
                        }
                    }
                    return
                except Exception:
                    pass

        # 2. Synchronous Generation Pipeline execution
        rag_resp = self.generate_answer(
            question=question,
            top_k=top_k,
            conversation_history=conversation_history,
            use_cache=use_cache
        )

        # 3. Stream generated response tokens
        words = rag_resp.answer.split(" ")
        for i, w in enumerate(words):
            chunk = w if i == len(words) - 1 else w + " "
            yield {"type": "token", "content": chunk}
            time.sleep(0.015)

        # 4. Stream structured citations
        yield {
            "type": "citations",
            "citations": [c.model_dump() for c in rag_resp.sources]
        }

        # 5. Stream final completion event
        yield {
            "type": "done",
            "metadata": {
                "cached": False,
                "confidence": rag_resp.confidence,
                "query_type": rag_resp.query_type,
                "retrieval_count": rag_resp.retrieval_count,
                "latency_breakdown": rag_resp.latency_breakdown,
                "total_latency_ms": round((time.time() - t_start) * 1000, 2)
            }
        }

    def _filter_used_citations(
        self,
        answer: str,
        citations: List[SourceCitation]
    ) -> List[SourceCitation]:
        """
        Extracts referenced source numbers from the answer text (e.g. [Source 1...]).
        If in-text source tags are found, filters citations to those referenced;
        otherwise returns all candidate citations to maintain provenance.
        """
        pattern = r"\[Source\s+(\d+)"
        matches = set(int(m) for m in re.findall(pattern, answer, re.IGNORECASE))

        if matches:
            referenced = [c for c in citations if c.source_number in matches]
            if referenced:
                return referenced
        return citations


_generator: Optional[RAGAnswerGenerator] = None

def get_answer_generator() -> RAGAnswerGenerator:
    global _generator
    if _generator is None:
        _generator = RAGAnswerGenerator()
    return _generator


def answer_query(
    question: str,
    top_k: int = 5,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    use_cache: bool = True
) -> RAGResponse:
    """
    Public production entrypoint for grounded RAG answer generation.
    """
    generator = get_answer_generator()
    return generator.generate_answer(
        question,
        top_k=top_k,
        conversation_history=conversation_history,
        use_cache=use_cache
    )


def stream_answer_query(
    question: str,
    top_k: int = 5,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    use_cache: bool = True
):
    """
    Public production entrypoint for streaming RAG answers.
    """
    generator = get_answer_generator()
    return generator.stream_answer(
        question,
        top_k=top_k,
        conversation_history=conversation_history,
        use_cache=use_cache
    )

