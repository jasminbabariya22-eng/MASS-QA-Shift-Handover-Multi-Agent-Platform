# 12. MASS QA Production Baseline & Frozen Architecture

## 1. Overview & Baseline Scope

This document defines and freezes the production baseline for the **MASS QA Technical Intelligence Chatbot**. The RAG pipeline, multimodal ingestion, hybrid retrieval, and grounded generation logic are stable and verified.

---

## 2. Frozen Architecture

```
                       USER QUERY
                           │
                           ▼
            NeMo Guardrails & Greetings Fast-Path
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
           [Greeting / Refused]    [In-Domain Technical Query]
                 │                   │
                 │                   ▼
                 │           Multi-Level Cache Check
                 │         (Redis / In-Memory TTL)
                 │                   │
                 │                   ▼
                 │          Hybrid Retrieval V2
                 │      ┌────────────┴────────────┐
                 │      ▼                         ▼
                 │  Dense Qdrant (3072d)    BM25 Sparse Index
                 │      └────────────┬────────────┘
                 │                   ▼
                 │        Reciprocal Rank Fusion (RRF)
                 │                   │
                 │                   ▼
                 │     FlashRank Cross-Encoder Reranker
                 │                   │
                 │                   ▼
                 │      Document Diversity Filtering
                 │                   │
                 │                   ▼
                 │          Context Builder V2
                 │     (Markdown Tables & Visual Captions)
                 │                   │
                 │                   ▼
                 │         Evidence Sufficiency Gate
                 │                   │
                 │                   ▼
                 │         Grounded LLM Generation
                 │      (Gemini Flash Pool -> Groq Fallback)
                 │                   │
                 └───────────────────┼───────────────────┐
                                     ▼                   ▼
                          Assistant Answer + Citations   PostgreSQL Persistence
                                                         (MASS.public Schema)
```

---

## 3. Stable Component Boundaries

| Layer | Component | Implementation File | Status |
| :--- | :--- | :--- | :--- |
| **Vector DB** | Qdrant Collection (`mass_qa_multimodal`) | 2,079 vectors, 3072 dims | **FROZEN** |
| **Sparse DB** | BM25 Inverted Index | `data/retrieval/bm25/` | **FROZEN** |
| **Reranker** | FlashRank CPU Cross-Encoder | `app/services/retrieval/reranker.py` | **FROZEN** |
| **Retrieval Engine** | Hybrid Retrieval V2 + RRF | `app/services/retrieval/hybrid.py` | **FROZEN** |
| **Guardrails** | NeMo Guardrails Fast-Path | `app/guardrails/rails.py` | **FROZEN** |
| **LLM Gateway** | Resilient Gemini & Groq Pool | `app/gateway/client.py` | **FROZEN** |
| **Context & Generation** | Context Builder + Evidence Checker | `app/services/generation/` | **FROZEN** |
| **Agent Interface** | Formal QA Agent Wrapper | `app/agents/qa_agent.py` | **ACTIVE** |
| **Relational DB** | PostgreSQL 18 Persistence | `app/db/` | **ACTIVE** |
| **Cache Engine** | Redis + In-Memory Fallback | `app/services/cache/cache_service.py` | **ACTIVE** |

---

## 4. QA Agent Formal Contract

### Input Contract (`QAAgentInput`):
```python
class QAAgentInput(BaseModel):
    query: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    top_k: int = 5
    use_cache: bool = True
    conversation_history: Optional[List[Dict[str, str]]] = []
```

### Output Contract (`QAAgentOutput`):
```python
class QAAgentOutput(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    confidence: str
    query_type: str
    grounded: bool
    retrieval_count: int
    latency_breakdown: Dict[str, float]
    metadata: Dict[str, Any] = {}
```

---

## 5. Non-Negotiable Guardrails for Future Steps
1. **Zero modifications to Qdrant collection `mass_qa_multimodal`** (2,079 vectors, 3072 dimensions, Cosine distance).
2. **No modifications to hybrid retrieval algorithm, weights, or reranking logic.**
3. **No shift-handover logic in the QA Agent.**
4. **All future multi-agent routing must treat `QAAgent` as a self-contained black-box tool.**
