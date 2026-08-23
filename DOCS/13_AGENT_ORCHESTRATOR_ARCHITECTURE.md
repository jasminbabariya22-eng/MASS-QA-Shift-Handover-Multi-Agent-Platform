# MASS QA — Agent Orchestrator Architecture (Step 2)

> **Status**: ✅ Step 2 Complete  
> **Last Updated**: 2026-08-22  
> **Depends On**: Step 1 QA Baseline Freeze  
> **Next Step**: Step 3 — Shift Handover Business Workflow Design

---

## 1. Overview

Step 2 introduces a **production-grade Agent Foundation and Agent Orchestrator** around the existing frozen QA/RAG pipeline without modifying any retrieval, embedding, LLM, or database behavior.

The key principle is:

> **Wrap — do not rewrite.**

The existing QA chatbot remains the stable foundation. The Agent Foundation adds a thin, safe orchestration layer that routes user requests to registered agents and normalizes their results.

---

## 2. Architecture Diagram

```text
                         Chat UI (Streamlit)
                              │
                              ▼
                   ┌─────────────────────┐
                   │    FastAPI /query    │
                   │   Auth + Guardrails  │
                   └──────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  AgentOrchestrator  │
                    │  ┌───────────────┐  │
                    │  │ IntentRouter  │  │
                    │  └───────┬───────┘  │
                    │          │          │
                    │  ┌───────▼───────┐  │
                    │  │ AgentRegistry │  │
                    │  └───────┬───────┘  │
                    └──────────┼──────────┘
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
          ┌─────────────┐          ┌──────────────────┐
          │  QA Agent   │          │ Shift Handover   │
          │  (active)   │          │ Agent (skeleton)  │
          └──────┬──────┘          └──────────────────┘
                 │
                 ▼
         Existing QA Service
                 │
    ┌────────────┼────────────┐
    ▼            ▼            ▼
 Qdrant        BM25       FlashRank
    │            │            │
    └────────────┼────────────┘
                 ▼
         LLM (Gemini/Groq)
                 │
                 ▼
           RAGResponse
```

---

## 3. Module Inventory

| Module | File | Purpose |
|--------|------|---------|
| **Agent Contracts** | `app/agents/contracts.py` | `AgentRequest`, `AgentContext`, `AgentResult`, `AgentTask`, `AgentIntent`, `AgentErrorCode` |
| **Base Agent** | `app/agents/base.py` | Abstract `BaseAgent` class with `execute()` and `stream()` |
| **Agent Registry** | `app/agents/registry.py` | Configuration-driven `AgentRegistry` singleton |
| **Intent Router** | `app/agents/router.py` | Deterministic regex-based `IntentRouter` |
| **QA Agent** | `app/agents/qa_agent.py` | Production adapter delegating to frozen `answer_query` / `stream_answer_query` |
| **Shift Agent** | `app/agents/shift_agent.py` | Skeleton placeholder returning safe disabled status |
| **Orchestrator** | `app/agents/orchestrator.py` | Central `AgentOrchestrator` coordinating routing, execution, errors, and tracing |
| **Exports** | `app/agents/__init__.py` | Public API for all agent modules |

---

## 4. Data Contracts

### 4.1 AgentIntent (Enum)

```python
QA              # Technical petroleum / knowledge-base questions
SHIFT_HANDOVER  # Operational shift management (Step 3)
UNKNOWN         # Unclassified — defaults to QA
```

### 4.2 AgentRequest

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | `str` | UUID — auto-generated, traceable through full pipeline |
| `user_id` | `Optional[str]` | From authenticated JWT context |
| `conversation_id` | `Optional[str]` | PostgreSQL conversation record ID |
| `session_id` | `str` | Session/thread identifier for memory |
| `message` | `str` | Raw user prompt |
| `intent` | `Optional[AgentIntent]` | Pre-classified intent (optional override) |
| `top_k` | `int` | Retrieval depth (default 5) |
| `use_cache` | `bool` | Cache lookup flag |
| `conversation_history` | `List[Dict]` | Sliding context window |
| `metadata` | `Dict` | Extensible key-value pairs |
| `created_at` | `datetime` | UTC timestamp |

### 4.3 AgentContext

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | `str` | Propagated from `AgentRequest` |
| `user_id` | `Optional[str]` | Authenticated identity |
| `conversation_id` | `Optional[str]` | DB conversation ID |
| `session_id` | `str` | Session ID |
| `current_agent` | `Optional[str]` | Target agent ID selected by router |
| `previous_agent` | `Optional[str]` | For future inter-agent chains |
| `intent` | `AgentIntent` | Detected intent |
| `permissions` | `List[str]` | `["qa.read", "shift.read"]` |

### 4.4 AgentResult

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | True if agent completed normally |
| `agent_id` | `str` | Which agent produced this result |
| `request_id` | `str` | Traceable request UUID |
| `response` | `str` | The answer text |
| `citations` | `List[Dict]` | Source citations from retrieval |
| `confidence` | `str` | `high`, `medium`, `low`, `refused` |
| `query_type` | `str` | Classification of the query |
| `grounded` | `bool` | Whether the answer is evidence-grounded |
| `retrieval_count` | `int` | Number of chunks retrieved |
| `execution_time_ms` | `float` | End-to-end agent latency |
| `latency_breakdown` | `Dict` | Per-stage timing |
| `error` | `Optional[Dict]` | Error code + message (only on failure) |

### 4.5 AgentTask (Future Inter-Agent)

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | UUID for this task |
| `parent_task_id` | `Optional[str]` | For chaining (Shift Agent → QA Agent) |
| `request_id` | `str` | Original request ID |
| `source_agent` | `str` | Who created the task |
| `target_agent` | `str` | Who should execute it |
| `task_type` | `str` | Task classification |
| `payload` | `Dict` | Task-specific data |

---

## 5. Agent Registry

The `AgentRegistry` is configuration/registration-driven, avoiding hardcoded `if/elif` agent selection.

```python
agent_registry = AgentRegistry()

# Agents self-register at module import time:
# qa_agent.py    → agent_registry.register(qa_agent)
# shift_agent.py → agent_registry.register(shift_handover_agent)
```

**Current registered agents:**

| Agent ID | Status | Capabilities |
|----------|--------|-------------|
| `qa_technical_agent` | ✅ Active | `answer_question`, `search_knowledge_base`, `return_citations` |
| `shift_handover_agent` | 🔒 Skeleton | `shift_handover_status` (returns disabled message) |

**API endpoint:**

```
GET /agents → lists all registered agents
```

---

## 6. Intent Router

The `IntentRouter` uses deterministic regex pattern matching — no LLM-based intent classification.

**Shift Handover patterns** (case-insensitive):

```
shift, handover, shift handover, operator handover,
shift log, shift notes, shift report, outgoing shift,
incoming shift, shift status, shift summary, turnover,
hand over, night shift, day shift, shift change
```

**Routing rules:**

| Intent | Target Agent | Behavior |
|--------|-------------|----------|
| `QA` | `qa_technical_agent` | Full RAG pipeline |
| `SHIFT_HANDOVER` | `shift_handover_agent` | Safe disabled message |
| `UNKNOWN` | `qa_technical_agent` | Defaults to QA |

**Context override:** If `context.metadata["forced_intent"]` is set, it takes precedence over regex matching.

---

## 7. Orchestrator Execution Flow

```text
1. Receive AgentRequest (from /query endpoint)
        ↓
2. Build AgentContext (_build_context)
   ├── Run IntentRouter.route(message)
   ├── Determine target_agent_id
   └── Set permissions, metadata
        ↓
3. Lookup agent in AgentRegistry.get(target_agent_id)
   ├── If not found → AGENT_UNAVAILABLE error result
   └── If found → proceed
        ↓
4. Execute agent.execute(request, context)
   ├── On success → return AgentResult
   └── On exception → AGENT_EXECUTION_ERROR safe response
        ↓
5. Record execution_time_ms
        ↓
6. Log via Logfire (request_id, agent_id, intent, latency, status)
        ↓
7. Return normalized AgentResult
```

### Streaming Flow

The same flow applies for `orchestrator.stream()`, except:
- Agent's `stream()` method is called, yielding SSE events
- On error, a safe error token + done event is yielded
- PostgreSQL persistence happens in the caller (`app/main.py`)

---

## 8. Error Handling

| Error Code | Trigger | User-Facing Response |
|------------|---------|---------------------|
| `AGENT_TIMEOUT` | Agent exceeds `AGENT_TIMEOUT_SECONDS` | "Request timed out. Please try again." |
| `AGENT_UNAVAILABLE` | Agent ID not found in registry | "The requested agent capability is currently unavailable." |
| `AGENT_EXECUTION_ERROR` | Unhandled exception during execution | "An unexpected error occurred while processing your request." |
| `INVALID_AGENT` | Invalid agent reference | Safe fallback |
| `INVALID_REQUEST` | Malformed request | 400 Bad Request |
| `UNKNOWN_INTENT` | Cannot classify intent | Defaults to QA Agent |

**Security:** No stack traces, database credentials, API keys, or internal paths are ever exposed in user-facing error responses.

---

## 9. Request Tracing

The same `request_id` flows through the entire pipeline:

```text
POST /query (req_id generated)
    → AgentRequest.request_id
    → AgentContext.request_id
    → Agent.execute() receives request_id
    → Logfire spans tagged with request_id
    → AgentResult.request_id
    → PostgreSQL QueryLog.request_id
    → API response metadata.request_id
```

---

## 10. Backward Compatibility

All external API contracts remain unchanged:

| Endpoint | Status |
|----------|--------|
| `POST /query` | ✅ Working — internally routes through Orchestrator → QA Agent |
| `POST /query/stream` | ✅ Working — delegates to `/query` with `stream=True` |
| `GET /health` | ✅ Unchanged |
| `GET /agents` | 🆕 New endpoint listing registered agents |
| `POST /auth/token` | ✅ Unchanged |
| `POST /feedback` | ✅ Unchanged |

The Streamlit frontend requires zero changes.

---

## 11. What Was NOT Changed (Preservation Checklist)

| Component | Status |
|-----------|--------|
| Qdrant `mass_qa_multimodal` (2,079 vectors, 3072 dims) | ✅ Untouched |
| PostgreSQL `MASS.public` (port 5433) | ✅ Untouched |
| BM25 sparse index | ✅ Untouched |
| RRF fusion | ✅ Untouched |
| FlashRank cross-encoder | ✅ Untouched |
| NeMo Guardrails | ✅ Untouched |
| Gemini/Groq gateway | ✅ Untouched |
| Conversation/session management | ✅ Untouched |
| JWT authentication | ✅ Untouched |
| Redis/in-memory cache | ✅ Untouched |

---

## 12. Security Boundaries

```text
┌─────────────────────────────────────┐
│           Orchestrator              │
│  ┌───────────────────────────────┐  │
│  │   Never logs:                │  │
│  │   • JWT tokens               │  │
│  │   • Database passwords       │  │
│  │   • API keys                 │  │
│  │   • Qdrant credentials       │  │
│  │   • LLM API keys            │  │
│  │   • Internal file paths      │  │
│  └───────────────────────────────┘  │
│                                     │
│  Agents can only access:           │
│  • Their registered services       │
│  • Data within their permissions   │
│  • No unrestricted DB access       │
│  • No arbitrary tool execution     │
└─────────────────────────────────────┘
```

---

## 13. Future Architecture (Step 3+)

```text
              Agent Orchestrator
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
      QA Agent             Shift Agent
         │                       │
      Qdrant               PostgreSQL
         │                  Shift Tables
    Existing RAG            Shift Tools
                            Equipment
                            Escalations
```

**Step 3 will design** the Shift Handover business workflow first, then implement:
- Shift database tables
- Operator handover workflows
- Equipment status tracking
- Operational escalations
- Agent-to-agent communication (Shift Agent → QA Agent for knowledge lookup)

---

## 14. Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/test_agent_orchestrator.py` | 9 tests | ✅ All passing |
| `tests/test_qa_agent.py` | 2 tests | ✅ All passing |
| `tests/test_database_persistence.py` | 12 tests | ✅ All passing |
| Other test modules | ~40+ tests | ✅ Regression passing |

**Key test areas:**
- Agent registry registration and lookup
- Intent router classification (QA vs Shift vs Unknown)
- Shift agent controlled skeleton response
- Orchestrator execution and routing
- Orchestrator streaming
- Error handling on unregistered agents
- `GET /agents` API endpoint
- `POST /query` through orchestrator
- Qdrant collection integrity (2,079 vectors, 3072 dims, green)
