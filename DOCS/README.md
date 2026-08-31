# MASS QA & Shift Handover Multi-Agent Platform — Technical Documentation Hub

Welcome to the central technical documentation repository for the **MASS QA & Shift Handover Multi-Agent Platform**.

> **Audience**: Architects, Backend Engineers, DevOps, QA Engineers, Industrial Operations Specialists, and Security Auditors.

---

## 1. Sequential Documentation Index

```
DOCS/
├── 00_PROJECT_OVERVIEW.md                     # 1. Problem domain, refinery architecture, tech stack & multi-agent features
├── 01_SYSTEM_ARCHITECTURE.md                  # 2. Subsystem topology, data flow, gateway, and multi-agent interaction
├── 02_INGESTION_ENGINE.md                     # 3. Document parsing, structure preservation, multimodal chunking & voice ingestion
├── 03_CHUNKING_EMBEDDING_VECTORSTORE.md       # 4. Chunking strategy, 3072-dim Gemini embeddings, Qdrant collection mass_qa_multimodal (2,079 points frozen)
├── 04_BASELINE_RAG_QA.md                      # 5. Multimodal RAG QA pipeline, evidence checker, RAGResponse & citation preservation
├── 05_LLM_GATEWAY_AND_MODEL_MESH.md           # 6. LLM Gateway, Model Mesh API, 3 open-source model routing, Portkey integration
├── 06_CACHING_ARCHITECTURE.md                 # 7. Multi-tier caching architecture (Layer A Response Cache, Layer B Candidate Cache, Session Cache)
├── 07_PROMPT_ENGINEERING_CATALOG.md          # 8. Complete prompt engineering inventory, purpose, location, and exact prompt content
├── 08_MULTI_AGENT_FOUNDATION.md               # 9. BaseAgent interface, agent capabilities & strongly typed contracts
├── 09_AGENT_ORCHESTRATOR_ROUTER.md            # 10. Intent routing, risk levels & safety interlocks
├── 10_QA_AGENT_ADAPTER.md                     # 11. QA Technical Agent Adapter wrapping frozen RAG engine
├── 11_SHIFT_HANDOVER_WORKFLOW.md              # 12. FSM state transitions, workflow engine, validation rules & personnel role permissions
├── 12_SHIFT_HANDOVER_DATABASE.md              # 13. PostgreSQL 18 relational persistence, optimistic concurrency locking, schema definitions
├── 13_SHIFT_HANDOVER_AGENT.md                 # 14. Conversational Shift Agent, operational logging, and voice integration
├── 14_VOICE_TRANSCRIPTION_AND_INGESTION.md   # 15. Gemini 3.6 Flash audio speech-to-text transcriber & equipment tag extractor
├── 15_AI_QUALITY_GATE_ENGINE.md               # 16. 0–100% Shift Handover Completeness Scoring Engine across 4 operational dimensions
├── 16_P2P_BIDIRECTIONAL_AGENT_COMMUNICATION.md # 17. Multi-turn P2P Peer Exchange Protocol & shared session state
├── 17_REACT_VITE_SPA_FRONTEND.md              # 18. React Vite SPA frontend (frontend/src/), ChatGPT-style Chat History Sidebar, dual-choice text/voice
├── 18_DATABASE_AUTHENTICATION_AND_RBAC.md    # 19. Database login_id & password authentication, 8 Personnel Job Roles matrix, JWT token generation
├── 19_HARNESS_ENGINEERING_AND_HITL.md        # 20. AI Harness governance, budget tracking, secret masking, and HITL supervisor approval queue
├── 20_SECURITY_OBSERVABILITY_CACHING.md       # 21. Security invariants, Logfire distributed tracing, OpenTelemetry integration
├── 21_EVALS_AND_TESTING_OPERATIONS.md        # 22. Verification test suite (232/232 tests passing), Docker runbooks, deployment & operations
├── 22_GLOSSARY.md                             # 23. Technical & industrial petroleum refining terminology
└── DOCUMENTATION_STATUS.md                    # 24. Documentation audit matrix & verification status
```

---

## 2. Platform Verification Status

```
================================================================================
PLATFORM VERIFICATION STATUS: 100% COMPLETE & VERIFIED
================================================================================
Step 1:  MASS QA Baseline & Qdrant Freeze (2,079 points, 3072d)  [VERIFIED]
Step 2:  Multi-Agent Foundation & Contracts                      [VERIFIED]
Step 3:  Agent Orchestrator & Router                             [VERIFIED]
Step 4:  QA Agent Adapter                                        [VERIFIED]
Step 5:  Shift Handover Workflow Engine (FSM)                    [VERIFIED]
Step 6:  PostgreSQL 18 Shift Handover Persistence                [VERIFIED]
Step 7:  Shift Handover Agent & Gemini Voice Transcriber         [VERIFIED]
Step 8:  AI Quality Gate Completeness Engine (0-100%)            [VERIFIED]
Step 9:  Model Mesh Gateway (3 Open-Source Models + Mesh API)    [VERIFIED]
Step 10: AI Harness & HITL Risk Governance                       [VERIFIED]
Step 11: Bidirectional P2P Peer Exchange Protocol               [VERIFIED]
Step 12: React Vite SPA Frontend & ChatGPT Chat History Sidebar  [VERIFIED]
Step 13: Database Auth & 8 Personnel Roles Matrix                [VERIFIED]
--------------------------------------------------------------------------------
TOTAL VERIFIED AUTOMATED TEST BASELINE: 232 / 232 TESTS PASSING (100%)
================================================================================
```

---

## 3. Core System Invariants

1. **Qdrant Vector Database Freeze**:
   The collection `mass_qa_multimodal` (2,079 points, 3072 dims, Cosine distance) is **permanently frozen**. No inserts, updates, deletes, or schema alterations are permitted.
2. **Physical Plant Control Prohibition**:
   The platform operates strictly as an intelligence and handover system. Under no circumstances can AI initiate physical plant manipulation (valves, pumps, ESD bypasses).
3. **Shift Handover Caching Rule**:
   **Shift handover operational state must NEVER be served from a stale cache.** Live PostgreSQL database state is always authoritative.
4. **Separation of Duties & HITL Safety**:
   A user submitting a high-risk handover cannot approve their own submission. High-risk approvals require authorized supervisor review.
5. **Open-Source Cost Optimization**:
   Query intent automatically routes across 3 cost-optimized open-source models: `llama-3.1-8b-instant` (sub-100ms planning), `mixtral-8x7b-32768` (MoE conversational), and `llama-3.3-70b-versatile` (heavy RAG reasoning).

---

## 4. Complete Application Execution Guide

### Step 1: Environment Setup
```bash
# 1. Activate Python virtual environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# 2. Install backend dependencies (if needed)
pip install -r requirements.txt
```

### Step 2: Launch FastAPI Backend Gateway (`http://localhost:8000`)
```bash
# Run database migrations
alembic upgrade head

# Launch FastAPI Uvicorn server on port 8000
$env:LOGFIRE_IGNORE_NO_CONFIG="1"; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
- 🌐 **Backend API Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- ⚙️ **Backend Health Endpoint**: [http://localhost:8000/ready](http://localhost:8000/ready)

### Step 3: Launch React Vite Single-Page Frontend (`http://localhost:5173`)
```bash
# Navigate to frontend directory
cd frontend

# Install frontend dependencies
npm install

# Launch React Vite dev server on port 5173
npm run dev -- --host 0.0.0.0 --port 5173
```
- ⚛️ **React Single-Page Portal**: [http://localhost:5173](http://localhost:5173)
- 🔑 **Demo Credentials**: `op_console_1` / `pass123` (Console Operator), `sup_shift_1` / `pass123` (Shift Supervisor), `mgr_plant_1` / `pass123` (Plant Manager)

### Step 4: Run Automated Verification Tests
```bash
pytest -v
# Verified Baseline: 232 / 232 tests passing (100% success rate)
```
