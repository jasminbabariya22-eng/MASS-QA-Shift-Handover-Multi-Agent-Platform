# MASS QA & Shift Handover Multi-Agent Platform

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL 18](https://img.shields.io/badge/PostgreSQL-18-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Qdrant](https://img.shields.io/badge/Qdrant-3072d%20Frozen-red.svg?logo=qdrant)](https://qdrant.tech)
[![Tests Passing](https://img.shields.io/badge/tests-291%2F291%20passing-brightgreen.svg)](tests/)
[![Architecture](https://img.shields.io/badge/Architecture-Multi--Agent%20A2A-orange.svg)](DOCS/01_SYSTEM_ARCHITECTURE.md)

An enterprise-grade, safety-critical **Multi-Agent Intelligence & Shift Handover Management Platform** designed for downstream oil refineries, petrochemical processing plants, and energy infrastructure.

Combines **Multimodal Hybrid RAG (3072-dim Qdrant + BM25 + FlashRank)** with a **Deterministic Shift Handover Workflow Engine (PostgreSQL 18, Optimistic Concurrency, LOTO Safety Sign-Offs, and HITL Governance)**.

---

## 🏗️ System Architecture Topology

```mermaid
flowchart TD
    subgraph INGRESS ["1. Ingress & Client Layer"]
        USER["👤 Operators / Supervisors / Engineers"]
        STREAMLIT["Streamlit Operations UI (:8501)<br/>• Operations Chat & SSE Streaming<br/>• HITL Governance Center<br/>• Telemetry & Audit Logs"]
        USER --> STREAMLIT
    end

    subgraph GATEWAY ["2. FastAPI API Gateway (:8000)"]
        STREAMLIT -->|REST / SSE Stream| FASTAPI["FastAPI API Layer<br/>• Gateway Correlation ID Middleware<br/>• JWT Bearer Authentication & RBAC<br/>• Sliding-Window Rate Limiting"]
    end

    subgraph HARNESS ["3. AI Harness & Safety Governance"]
        FASTAPI --> HARNESS_CONTAINER["AI Harness Container<br/>• Pre/Post Execution Governance<br/>• Execution Budget & Loop Detector [A,B,A,B]<br/>• Safety Interlock Refusal Guard<br/>• Secret & Token Masking"]
    end

    subgraph ORCHESTRATION ["4. Multi-Agent Mesh & Routing"]
        HARNESS_CONTAINER --> ROUTER{"IntentRouter<br/>(<1ms Deterministic Classification)"}
        ROUTER -->|Intent: QA| QA_AGENT["QAAgentAdapter<br/>(Technical QA Agent)"]
        ROUTER -->|Intent: SHIFT| SHIFT_AGENT["ShiftHandoverAgent<br/>(Turnover Workflow Agent)"]
        ROUTER -->|Intent: LOOP| LOOP_AGENT["LoopEngineeringAgent<br/>(ISA-5.1 Signal Tracing)"]
        ROUTER -->|Intent: MULTI_AGENT| COMPOSITE["Multi-Agent Mesh Coordinator<br/>(A2A Composite Synthesis)"]
        ROUTER -->|Intent: HIGH_RISK| REFUSAL["🛑 Safety Refusal<br/>(Prohibits Physical Plant Control)"]
    end

    subgraph RETRIEVAL_PIPELINE ["5. Frozen Multimodal Hybrid RAG V2"]
        QA_AGENT --> HYBRID["Hybrid Retriever Engine<br/>• Dense: Qdrant Cloud (3072d, 2,079 points, FROZEN)<br/>• Sparse: Local Okapi BM25 Index<br/>• Fusion: Reciprocal Rank Fusion (RRF, k=60)<br/>• Rerank: FlashRank Cross-Encoder (MiniLM-L-6-v2)<br/>• Gate: Anti-Hallucination Evidence Checker"]
        HYBRID --> LLM_GATEWAY["Resilient LLM Gateway<br/>(Gemini 2.5 Flash / Groq Portkey Fallback)"]
    end

    subgraph PERSISTENCE ["6. Enterprise Relational Persistence"]
        SHIFT_AGENT --> WORKFLOW["ShiftHandoverWorkflowEngine<br/>• 8-State Deterministic FSM<br/>• Role Matrix Authorization<br/>• LOTO & Safety Item Checks"]
        WORKFLOW --> POSTGRES[("PostgreSQL 18 Database<br/>• shift_handovers (Optimistic Locking 'version')<br/>• shift_safety_critical_items (LOTO/Permits)<br/>• shift_handover_audits (Immutable Trail)<br/>• hitl_approval_requests (Separation of Duties)")]
    end

    LLM_GATEWAY --> STREAMLIT
    POSTGRES --> STREAMLIT
```

---

## ⚡ Key Capabilities & Core Components

### 1. Multimodal Hybrid RAG QA Engine (`qa_technical_agent`)
- **Dual Retrieval**: Parallel execution of dense semantic search against Qdrant (3072-dim embeddings) and sparse keyword search via BM25 on disk.
- **Reciprocal Rank Fusion (RRF)**: Merges dense and lexical results ($k=60$) to boost documents matching both semantics and exact equipment tags (e.g., `P-101`, `CDU-101`).
- **FlashRank Cross-Encoder**: Reranks top 35 candidates locally using `ms-marco-MiniLM-L-6-v2`.
- **Anti-Hallucination Gatekeeper**: `EvidenceChecker` enforces a 4-tier confidence evaluation (`HIGH`, `MEDIUM`, `LOW`, `INSUFFICIENT`); automatically abstains if evidence is lacking.
- **Frozen Qdrant Invariant**: Collection `mass_qa_multimodal` (2,079 points, 3072 dimensions, Cosine) is permanently frozen and immutable.

### 2. Shift Handover Workflow Engine (`shift_handover_agent`)
- **8-State Deterministic FSM**: `DRAFT` $\to$ `SUBMITTED` $\to$ `PENDING_REVIEW` $\to$ `REVISED` $\to$ `PENDING_ACKNOWLEDGEMENT` $\to$ `COMPLETED` (or `REJECTED` / `ESCALATED`).
- **PostgreSQL 18 Persistence**: Strongly typed SQLAlchemy models managed via Alembic migrations.
- **Optimistic Concurrency Control**: Uses a monotonic `version` integer column to eliminate lost-update race conditions in busy control rooms.
- **Safety Sign-Off Enforcement**: Strictly blocks incoming custody transfer (`ACKNOWLEDGE`) if any active Lockout/Tagout (LOTO) or Permit-to-Work (PTW) items remain unacknowledged.
- **Zero-Stale-Cache Invariant**: Live shift handover state is **never served from cache**—PostgreSQL live state is always authoritative.

### 3. Loop Engineering Agent (`loop_engineering_agent`)
- **ISA-5.1 Instrumentation Tracing**: Validates process measurement control loops, equipment tags, and signal paths from field sensors (`PT-101`, `FT-202`) to Distributed Control Systems (DCS).

### 4. Production AI Harness & Safety Interlocks
- **Autonomous Control Refusal**: Permanent safety interlock automatically blocks and refuses any autonomous physical equipment actuation commands (e.g., *"Trip pump P-101"*).
- **Execution Budgeting & Loop Prevention**: Limits tool invocation depth (Max Depth: 5, Max Steps: 15) and detects repeating tool cycles (`[A, B, A, B]`).
- **Secret Redaction**: Automatically masks API keys, JWT bearer tokens, and credentials in execution traces and logs.

### 5. Human-in-the-Loop (HITL) Governance Center
- **4-Tier Risk Matrix**: Deterministically scores actions into `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.
- **Separation of Duties**: Strictly prohibits self-approval (e.g., a requester cannot approve their own high-risk shift turnover).
- **Approval Lifecycle**: `/approvals` routes for supervisor authorization, rejection with mandatory operational reason, return for rework, and expiration tracking.

### 6. Production FastAPI Gateway & Real-Time SSE
- **Streaming**: Server-Sent Events (`/query/stream`) yielding incremental text tokens, citation objects, and telemetry metadata.
- **Security & RBAC**: JWT Bearer token authentication supporting 7 operational personas (`CONSOLE_OPERATOR`, `SHIFT_SUPERVISOR`, `INCOMING_OPERATOR`, `FIELD_OPERATOR`, `OPERATIONS_ENGINEER`, `HSE_REPRESENTATIVE`, `ADMIN`).
- **Observability**: Distributed tracing with **Pydantic Logfire** and correlation ID propagation.

---

## 📊 Verified Test Baseline (291 / 291 Passing Tests)

The platform includes an extensive automated test suite covering all 10 major architectural steps:

| Step / Component | Test Suite File | Scenarios | Status |
| :--- | :--- | :--- | :--- |
| **Step 3**: Orchestrator & Router | `tests/test_agent_orchestrator.py` | 64 / 64 | ✅ 100% PASS |
| **Step 4**: QA Agent Adapter | `tests/test_qa_agent.py` | 10 / 10 | ✅ 100% PASS |
| **Step 4**: Orchestrator Regressions | `tests/test_orchestrator_regression.py` | 11 / 11 | ✅ 100% PASS |
| **Step 5**: Shift Workflow Engine | `tests/test_shift_handover_workflow.py` | 14 / 14 | ✅ 100% PASS |
| **Step 6**: PostgreSQL Persistence | `tests/test_shift_handover_persistence.py` | 20 / 20 | ✅ 100% PASS |
| **Step 7**: Shift Handover Agent | `tests/test_shift_agent.py` | 25 / 25 | ✅ 100% PASS |
| **Step 8**: Production API Gateway | `tests/test_production_api.py` | 25 / 25 | ✅ 100% PASS |
| **Step 9**: API Mesh Hardening | `tests/test_api_mesh.py` | 24 / 24 | ✅ 100% PASS |
| **Step 9**: Loop Engineering Agent | `tests/test_loop_engineering_agent.py` | 16 / 16 | ✅ 100% PASS |
| **Step 10**: AI Harness Governance | `tests/test_harness.py` | 28 / 28 | ✅ 100% PASS |
| **Step 10**: HITL Risk Governance | `tests/test_hitl_governance.py` | 20 / 20 | ✅ 100% PASS |
| **TOTAL VERIFIED SUITE** | — | **291 / 291** | **✅ 100% PASSING** |

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python 3.11+**
- **PostgreSQL 18** (or compatible 14+)
- **Redis** (optional; in-memory fallback is automatic)

### 1. Clone & Environment Setup
```powershell
# Clone repository
git clone https://github.com/jasminbabariya22-eng/MASS-QA-Shift-Handover-Multi-Agent-Platform.git
cd MASS-QA-Shift-Handover-Multi-Agent-Platform

# Create & activate Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the template `.env.example` to `.env` and fill in your keys:
```powershell
Copy-Item .env.example .env
```
Key configurations in `.env`:
```env
# LLM Gateway
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key

# Qdrant Vector Store (Frozen)
QDRANT_API_KEY=your_qdrant_api_key
QDRANT_CLUSTER_ENDPOINT=https://your-cluster-id.aws.cloud.qdrant.io
QDRANT_COLLECTION=mass_qa_multimodal

# PostgreSQL Persistence
DATABASE_URL=postgresql://mass_user:secret_password@localhost:5432/mass_db

# Security & JWT
JWT_SECRET_KEY=super-secret-cryptographic-key-32-chars-minimum
```

### 3. Run Database Migrations (Alembic)
```powershell
alembic upgrade head
```

### 4. Launch Application Services

**Terminal 1: Start FastAPI Backend Gateway (`:8000`)**
```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2: Start Streamlit Operations UI (`:8501`)**
```powershell
streamlit run ui/app.py
```

Open your browser at **`http://localhost:8501`**.

---

## 🧪 Running the Live E2E Verification Runner

Execute all 14 end-to-end scenarios (Auth, RAG QA, Shift Handover, LOTO, Supervisor Approval, HITL, A2A Multi-Agent, Safety Interlock, and SSE Streaming):

```powershell
python scripts/live_e2e_demo_runner.py
```

---

## 📂 Project Repository Structure

```text
├── app/
│   ├── agents/
│   │   ├── base.py                 # BaseAgent abstract contract
│   │   ├── contracts.py            # Strongly typed AgentRequest / AgentResponse
│   │   ├── orchestrator.py         # Multi-Agent Central Orchestrator
│   │   ├── registry.py             # Agent discovery and capability registry
│   │   ├── router.py               # Deterministic <1ms Intent Router
│   │   ├── qa_agent.py             # Multimodal QA Agent Adapter
│   │   ├── shift/                  # Shift Handover Agent & Command Extractor
│   │   └── loop/                   # ISA-5.1 Loop Engineering Agent
│   ├── db/
│   │   ├── database.py             # SQLAlchemy engine & session factory
│   │   └── models/                 # PostgreSQL ORM models (handovers, audits, HITL)
│   ├── governance/
│   │   ├── hitl.py                 # HITL Approval Service & Lifecycle
│   │   ├── policy.py               # Separation of Duties & RBAC Policies
│   │   ├── risk.py                 # 4-Tier Deterministic Risk Classifier
│   │   └── contracts.py            # HITL domain schemas
│   ├── harness/
│   │   ├── harness.py              # AI Harness Execution Wrapper
│   │   ├── budget.py               # Execution budget & loop detector
│   │   └── safety.py               # Plant control safety refusal guards
│   ├── services/
│   │   ├── retrieval/              # Hybrid RAG V2 (Qdrant + BM25 + FlashRank)
│   │   ├── generation/             # ContextBuilder, EvidenceChecker, Generator
│   │   ├── cache/                  # Multi-Tier Caching (Redis + In-Memory)
│   │   └── db_services.py          # Message, citation & audit persistence
│   ├── security/                   # JWT Auth, RBAC hierarchies, Rate Limiting
│   └── main.py                     # FastAPI API Gateway & SSE Streaming routes
├── alembic/                        # PostgreSQL migration versions
├── DOCS/                           # 18-Chapter Technical & Operational Documentation
├── evals/                          # RAGAS benchmark datasets & evaluation scripts
├── scripts/                        # Live E2E test runner & BM25 index builder
├── tests/                          # 291 passing automated tests (Steps 3 - 10)
├── ui/                             # Streamlit Web UI (app.py)
├── Dockerfile                      # Production container definition
├── requirements.txt                # Pinned dependencies
└── README.md                       # Main Documentation Entry Point
```

---

## 📖 Complete Technical Documentation Hub

For exhaustive architectural specifications, refer to the [`DOCS/`](DOCS/) documentation suite:

1. [00_PROJECT_OVERVIEW.md](DOCS/00_PROJECT_OVERVIEW.md) — Business domain, refinery context & roadmap.
2. [01_SYSTEM_ARCHITECTURE.md](DOCS/01_SYSTEM_ARCHITECTURE.md) — End-to-end subsystem topology and boundary contracts.
3. [02_BASELINE_RAG_QA.md](DOCS/02_BASELINE_RAG_QA.md) — Hybrid retrieval (Qdrant 3072d, BM25, RRF, FlashRank).
4. [03_MULTI_AGENT_FOUNDATION.md](DOCS/03_MULTI_AGENT_FOUNDATION.md) — BaseAgent interface, registry & contracts.
5. [04_AGENT_ORCHESTRATOR_ROUTER.md](DOCS/04_AGENT_ORCHESTRATOR_ROUTER.md) — Intent routing & physical control refusal.
6. [05_QA_AGENT_ADAPTER.md](DOCS/05_QA_AGENT_ADAPTER.md) — Multi-agent adapter wrapping the frozen RAG engine.
7. [06_SHIFT_HANDOVER_WORKFLOW.md](DOCS/06_SHIFT_HANDOVER_WORKFLOW.md) — 8-state FSM, transition rules & role matrix.
8. [07_SHIFT_HANDOVER_DATABASE.md](DOCS/07_SHIFT_HANDOVER_DATABASE.md) — PostgreSQL 18 schema & optimistic locking.
9. [08_SHIFT_HANDOVER_AGENT.md](DOCS/08_SHIFT_HANDOVER_AGENT.md) — Conversational shift agent & extraction rules.
10. [09_API_CHATBOT_INTEGRATION.md](DOCS/09_API_CHATBOT_INTEGRATION.md) — FastAPI endpoints, SSE streaming & security.
11. [10_HARNESS_ENGINEERING.md](DOCS/10_HARNESS_ENGINEERING.md) — AI Harness execution container & budget guards.
12. [11_HITL_HUMAN_IN_THE_LOOP.md](DOCS/11_HITL_HUMAN_IN_THE_LOOP.md) — Risk matrix & human authorization gates.
13. [12_SECURITY_OBSERVABILITY_CACHING.md](DOCS/12_SECURITY_OBSERVABILITY_CACHING.md) — JWT auth, Logfire tracing & caching rules.
14. [13_END_TO_END_WORKFLOW.md](DOCS/13_END_TO_END_WORKFLOW.md) — 7 real-world operational execution flows.
15. [14_TESTING_DEPLOYMENT_OPERATIONS.md](DOCS/14_TESTING_DEPLOYMENT_OPERATIONS.md) — 291-test baseline & Docker runbooks.
16. [15_GLOSSARY.md](DOCS/15_GLOSSARY.md) — Technical & industrial petroleum terminology.
17. [live_end_to_end_demo.md](DOCS/live_end_to_end_demo.md) — Complete live demonstration execution report.

---

## 🔒 Safety & Industrial Compliance Principles

1. **Frozen Knowledge Base**: Qdrant collection `mass_qa_multimodal` is permanently frozen (2,079 points, 3072 dims).
2. **Prohibition of Plant Actuation**: Autonomous physical equipment commands are blocked by hardcoded safety interlocks.
3. **Live State Authoritativeness**: Operational Shift Handover and LOTO records are strictly excluded from caching.
4. **Separation of Duties**: Mandatory human authorization gates prevent self-approvals on high-risk workflows.

---

## 📄 License
Enterprise Proprietary — All Rights Reserved.
