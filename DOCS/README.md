# MASS QA & Shift Handover Multi-Agent Platform — Documentation Hub

Welcome to the central technical documentation repository for the **MASS QA & Shift Handover Multi-Agent Platform**.

> **Audience**: Architects, Backend Engineers, DevOps, QA Engineers, Industrial Operations Specialists, and Security Auditors.

---

## 1. Documentation Index & Recommended Reading Order

```
DOCS/
├── 00_PROJECT_OVERVIEW.md                    # 1. Problem domain, features, open-source models & tech stack
├── 01_SYSTEM_ARCHITECTURE.md                 # 2. Subsystem architecture & data topology
├── 02_BASELINE_RAG_QA.md                     # 3. Multimodal RAG pipeline & frozen Qdrant vector database
├── 03_MULTI_AGENT_FOUNDATION.md              # 4. BaseAgent interface, registry & strongly typed contracts
├── 04_AGENT_ORCHESTRATOR_ROUTER.md           # 5. Intent routing, risk levels & safety interlocks
├── 05_QA_AGENT_ADAPTER.md                    # 6. Multi-agent adapter wrapping frozen RAG engine
├── 06_SHIFT_HANDOVER_WORKFLOW.md             # 7. Finite state machine, transition rules & role matrix
├── 07_SHIFT_HANDOVER_DATABASE.md             # 8. PostgreSQL 18 relational persistence & optimistic locking
├── 08_SHIFT_HANDOVER_AGENT.md                # 9. Conversational shift interface, voice & quality gate
├── 09_API_CHATBOT_INTEGRATION.md             # 10. FastAPI Gateway, SSE streaming & REST routes
├── 09_LLM_GATEWAY.md                         # 11. Model Mesh Gateway (Mesh API & 3 Open-Source Models)
├── 10_HARNESS_ENGINEERING.md                 # 12. AI Harness governance, budget tracking & secret masking
├── 11_HITL_HUMAN_IN_THE_LOOP.md              # 13. Human authorization gates, risk matrix & replay checks
├── 12_SECURITY_OBSERVABILITY_CACHING.md      # 14. JWT auth, Logfire distributed tracing & caching invariants
├── 13_END_TO_END_WORKFLOW.md                 # 15. Real-world operational execution flows
├── 14_TESTING_DEPLOYMENT_OPERATIONS.md       # 16. Verified test baselines, Docker runbooks & deployment
├── 15_P2P_BIDIRECTIONAL_AGENT_COMMUNICATION.md # 17. Multi-turn Bidirectional P2P Peer Exchange Protocol
├── 16_VOICE_TRANSCRIPTION_AND_INGESTION.md  # 18. Gemini 3.6 Flash audio speech-to-text transcriber
├── 17_AI_QUALITY_GATE_ENGINE.md              # 19. 0-100% Shift Handover Completeness Scoring Engine
├── 18_REACT_VITE_SPA_FRONTEND.md             # 20. React Single-Page Frontend & ChatGPT Chat History Sidebar
├── 19_DATABASE_AUTHENTICATION_AND_RBAC.md   # 21. Database `login_id` & `password` auth and 8 Personnel Roles Matrix
├── 15_GLOSSARY.md                            # 22. Technical & industrial petroleum terminology
└── DOCUMENTATION_STATUS.md                   # 23. Documentation audit, verification & status report

```

---

## 2. Current Implementation Status

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

# 3. Ensure environment credentials in .env file:
# MESH_API_KEY=rsk_01M18Z...
# MESH_API_BASE_URL=https://api.meshapi.ai
# GEMINI_API_KEY=AIzaSy...
# POSTGRES_URL=postgresql://postgres:postgres@localhost:5433/mass_db
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

# Install frontend dependencies (lucide-react, vite, etc.)
npm install

# Launch React Vite dev server on port 5173
npm run dev -- --host 0.0.0.0 --port 5173
```
- ⚛️ **React Single-Page Portal**: [http://localhost:5173](http://localhost:5173)
- 🔑 **Demo Accounts**: `op_console_1` / `pass123` (Console Operator), `sup_shift_1` / `pass123` (Shift Supervisor), `mgr_plant_1` / `pass123` (Plant Manager)

### Step 4: Run Automated Verification Tests
```bash
pytest -v
# Verified Baseline: 232 / 232 tests passing (100% success rate)
```


---


## 5. Where to Find Specific Information

- **Adding a new Agent**: See [03_MULTI_AGENT_FOUNDATION.md](file:///d:/Chatboat/docs/03_MULTI_AGENT_FOUNDATION.md#5-guide-how-to-add-a-new-domain-agent).
- **Model Mesh & Open-Source Routing**: See [09_LLM_GATEWAY.md](file:///d:/Chatboat/docs/09_LLM_GATEWAY.md).
- **Bidirectional P2P Communication**: See [15_P2P_BIDIRECTIONAL_AGENT_COMMUNICATION.md](file:///d:/Chatboat/docs/15_P2P_BIDIRECTIONAL_AGENT_COMMUNICATION.md).
- **Gemini Audio Voice Ingestion**: See [16_VOICE_TRANSCRIPTION_AND_INGESTION.md](file:///d:/Chatboat/docs/16_VOICE_TRANSCRIPTION_AND_INGESTION.md).
- **AI Quality Gate Completeness Engine**: See [17_AI_QUALITY_GATE_ENGINE.md](file:///d:/Chatboat/docs/17_AI_QUALITY_GATE_ENGINE.md).
- **Understanding HITL Approval Gates**: See [11_HITL_HUMAN_IN_THE_LOOP.md](file:///d:/Chatboat/docs/11_HITL_HUMAN_IN_THE_LOOP.md).
- **Running Automated Tests**: See [14_TESTING_DEPLOYMENT_OPERATIONS.md](file:///d:/Chatboat/docs/14_TESTING_DEPLOYMENT_OPERATIONS.md).
