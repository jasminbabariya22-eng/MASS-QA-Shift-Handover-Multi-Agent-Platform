# MASS QA & Shift Handover Multi-Agent Platform — Documentation Hub

Welcome to the central technical documentation repository for the **MASS QA & Shift Handover Multi-Agent Platform**.

> **Audience**: Architects, Backend Engineers, DevOps, QA Engineers, Industrial Operations Specialists, and Security Auditors.

---

## 1. Documentation Index & Recommended Reading Order

```
DOCS/
├── 00_PROJECT_OVERVIEW.md              # 1. Start here: Problem domain, features & technology stack
├── 01_SYSTEM_ARCHITECTURE.md           # 2. Complete subsystem architecture & data topology
├── 02_BASELINE_RAG_QA.md               # 3. Multimodal RAG pipeline & frozen Qdrant vector database
├── 03_MULTI_AGENT_FOUNDATION.md        # 4. BaseAgent interface, registry & strongly typed contracts
├── 04_AGENT_ORCHESTRATOR_ROUTER.md     # 5. Intent routing, composite execution & safety interlocks
├── 05_QA_AGENT_ADAPTER.md              # 6. Multi-agent adapter wrapping the frozen RAG engine
├── 06_SHIFT_HANDOVER_WORKFLOW.md       # 7. Finite state machine, transition rules & role matrix
├── 07_SHIFT_HANDOVER_DATABASE.md       # 8. PostgreSQL 18 relational persistence & optimistic locking
├── 08_SHIFT_HANDOVER_AGENT.md          # 9. Natural language conversational interface for handovers
├── 09_API_CHATBOT_INTEGRATION.md       # 10. FastAPI Gateway, SSE streaming & REST routes
├── 10_HARNESS_ENGINEERING.md           # 11. AI Harness governance, budget tracking & secret masking
├── 11_HITL_HUMAN_IN_THE_LOOP.md        # 12. Human authorization gates, risk matrix & replay checks
├── 12_SECURITY_OBSERVABILITY_CACHING.md# 13. JWT auth, Logfire distributed tracing & caching invariants
├── 13_END_TO_END_WORKFLOW.md           # 14. Seven complete real-world operational execution flows
├── 14_TESTING_DEPLOYMENT_OPERATIONS.md # 15. Verified test baselines, Docker runbooks & deployment
├── 15_GLOSSARY.md                      # 16. Technical & industrial petroleum terminology
└── DOCUMENTATION_STATUS.md             # 17. Documentation audit, verification & completeness report
```

---

## 2. Current Implementation Status

```
================================================================================
PLATFORM VERIFICATION STATUS: 100% COMPLETE & VERIFIED
================================================================================
Step 1:  MASS QA Baseline & Qdrant Freeze (2,079 points, 3072d)  [VERIFIED]
Step 2:  Multi-Agent Foundation & Contracts                      [VERIFIED]
Step 3:  Agent Orchestrator & Router (64/64 tests)               [VERIFIED]
Step 4:  QA Agent Adapter (10/10 tests + 11 regressions)         [VERIFIED]
Step 5:  Shift Handover Workflow Engine (14/14 tests)            [VERIFIED]
Step 6:  PostgreSQL Shift Persistence (20/20 tests)              [VERIFIED]
Step 7:  Production Shift Handover Agent (25/25 tests)           [VERIFIED]
Step 8:  Production API & Chatbot Transport (25/25 tests)        [VERIFIED]
Step 9:  API Mesh Hardening & Loop Engineering (40/40 tests)     [VERIFIED]
Step 10: AI Harness & HITL Risk Governance (48/48 tests)         [VERIFIED]
--------------------------------------------------------------------------------
TOTAL VERIFIED AUTOMATED TEST BASELINE: 291 / 291 TESTS PASSING (100%)
================================================================================
```

---

## 3. Critical System Invariants

1. **Qdrant Vector Database Freeze**:
   The collection `mass_qa_multimodal` (2,079 points, 3072 dims, Cosine distance) is **permanently frozen**. No inserts, updates, deletes, or schema alterations are permitted.
2. **Physical Plant Control Prohibition**:
   The platform operates strictly as an intelligence and handover system. Under no circumstances can AI initiate physical plant manipulation (valves, pumps, ESD bypasses).
3. **Shift Handover Caching Rule**:
   **Shift handover operational state must NEVER be served from a stale cache.** Live PostgreSQL database state is always authoritative.
4. **Separation of Duties**:
   A user submitting a high-risk handover cannot approve their own submission.

---

## 4. Developer Quick Start

```bash
# 1. Activate Python virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Run database migrations
alembic upgrade head

# 3. Launch FastAPI backend (:8000)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Launch Streamlit UI (:8501)
streamlit run ui/app.py
```

---

## 5. Where to Find Specific Information

- **Adding a new Agent**: See [03_MULTI_AGENT_FOUNDATION.md](file:///d:/Chatboat/DOCS/03_MULTI_AGENT_FOUNDATION.md#5-guide-how-to-add-a-new-domain-agent).
- **Modifying Shift Handover States**: See [06_SHIFT_HANDOVER_WORKFLOW.md](file:///d:/Chatboat/DOCS/06_SHIFT_HANDOVER_WORKFLOW.md#3-workflow-state-machine--lifecycle).
- **Investigating Concurrency Conflicts**: See [07_SHIFT_HANDOVER_DATABASE.md](file:///d:/Chatboat/DOCS/07_SHIFT_HANDOVER_DATABASE.md#4-optimistic-concurrency-control-version-column).
- **Understanding HITL Approval Gates**: See [11_HITL_HUMAN_IN_THE_LOOP.md](file:///d:/Chatboat/DOCS/11_HITL_HUMAN_IN_THE_LOOP.md#3-hitl-approval-request-lifecycle-appgovernancehitlpy).
- **Running Automated Tests**: See [14_TESTING_DEPLOYMENT_OPERATIONS.md](file:///d:/Chatboat/DOCS/14_TESTING_DEPLOYMENT_OPERATIONS.md#2-cost-conscious-incremental-testing-strategy).
