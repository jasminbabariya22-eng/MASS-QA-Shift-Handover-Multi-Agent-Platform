# 00. MASS QA & Shift Handover Platform — Project Overview

## 1. Executive Summary & Purpose

The **MASS QA & Shift Handover Multi-Agent Platform** is an enterprise-grade technical intelligence and operations governance system engineered for downstream Oil & Gas operations, refineries, and complex industrial plants.

The platform unifies two mission-critical capabilities:
1. **MASS QA (Multimodal Technical Intelligence)**: High-accuracy, grounded question answering over complex refinery documentation—including Standard Operating Procedures (SOPs), Emergency Operating Procedures (EOPs), Piping & Instrumentation Diagrams (P&IDs), Instrument Loop Diagrams, Equipment Manuals, Safety Data Sheets (SDS), and incident records.
2. **Shift Handover & Operations Governance**: A deterministic state-machine and Human-In-The-Loop (HITL) workflow managing unit custody transitions, safety-critical isolations (LOTO), open work permits (PTW), standing alarms, and carry-forward operator actions across 12-hour shift cycles.

---

## 2. The Industrial Problem & Operational Use Case

In petrochemical processing units (such as Crude Distillation Units, Hydrocrackers, Catalytic Reformers, and Gas Separation Plants), operational failures frequently occur at two interfaces:
- **Information Retrieval Latency**: Field and console operators troubleshooting unit upsets (e.g., compressor seal gas pressure drops, pump cavitation, column flooding) must consult hundreds of multi-page technical manuals and P&IDs under tight time constraints.
- **Shift Handover Asymmetry**: Miscommunication of active unit anomalies, temporary safety overrides, or unacknowledged bypasses during physical shift relief is a leading cause of industrial incidents.

The platform addresses both failure modes by combining **deterministic business rules** with **multimodal AI assistance**, ensuring that AI recommendations are grounded in verified documentation and that operations with physical risk require human approval.

---

## 3. Core Architecture & Architectural Philosophy

```
                              OPERATIONAL USERS
                (Console Operators, Field Techs, Shift Supervisors)
                                      │
                                      ▼
                        Streamlit Web UI / REST Clients
                                      │
                                      ▼
                    FastAPI Production Gateway (:8000)
             (JWT Auth, Rate Limiting, Security Headers, CORS)
                                      │
                                      ▼
                            ┌───────────────────┐
                            │    AI HARNESS     │
                            │  Governance Gate  │
                            │ (RBAC, Safety,    │
                            │  HITL Interlock)  │
                            └─────────┬─────────┘
                                      │
                                      ▼
                            ┌───────────────────┐
                            │ Agent Orchestrator│
                            │  & Intent Router  │
                            └─────────┬─────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
  QA Technical Agent            Shift Handover Agent          Loop Engineering Agent
(MASS QA RAG Adapter)         (Deterministic Workflow)       (ISA-5.1 Diagram Tracer)
        │                             │                             │
        ▼                             ▼                             ▼
  Frozen RAG Engine             Shift Service               Loop Service & RAG
(Hybrid Qdrant + BM25)      (PostgreSQL Persistence)     (Signal Path & Consistency)
        │                             │                             │
        ▼                             ▼                             ▼
 Qdrant Vector DB (3072d)     PostgreSQL 18 Database        Qdrant + Graph Relations
(mass_qa_multimodal)          (Audit, Handovers, Users)     (Equipment & Wiring Checks)
```

### Core Design Separation:
- **LLM / Generative AI**: Responsible for natural language comprehension, intent extraction, synthesis, and grounding explanation. **The LLM never directly executes state changes, authorizes actions, or communicates with physical plant controls.**
- **Deterministic Application Layer**: Authoritative state machines (`ShiftHandoverWorkflowEngine`), risk evaluation (`PolicyEngine`), role checks (`HarnessPermissionManager`), and transactional persistence (`PostgreSQL`).
- **PostgreSQL Database**: Single source of truth for all shift records, user permissions, and immutable audit logs.
- **Qdrant Vector Store**: Frozen knowledge base of multimodal technical documents (`mass_qa_multimodal`).

---

## 4. Technology Stack

| Layer | Component / Tool | Technology & Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Transport / API** | REST API Gateway | FastAPI 0.115+, Uvicorn, AnyIO | High-throughput asynchronous API gateway |
| **Streaming** | SSE (Server-Sent Events) | `sse-starlette` | Token-by-token and event-by-event streaming |
| **User Interface** | Operations Portal | Streamlit | Chat interface, handover forms, approval actions |
| **Primary Vector DB** | Dense Embeddings Store | Qdrant (`mass_qa_multimodal`) | 2,079 points, 3072 dimensions, Cosine distance |
| **Sparse Index** | Lexical Retrieval | BM25 (`rank-bm25`) | Exact keyword, equipment tag, and SOP code matching |
| **Reranking** | CPU Cross-Encoder | FlashRank (`ms-marco-TinyBERT-L-2-v2`) | High-speed reranking of candidate chunks |
| **Relational DB** | Operational Persistence | PostgreSQL 18 + SQLAlchemy 2.0 | Shift logs, audit trails, user accounts, approvals |
| **Database Migrations**| Schema Migration Engine | Alembic | Version-controlled database schema evolution |
| **Caching Engine** | Distributed Cache | Redis + In-Memory Fallback | RAG query caching, session management |
| **LLM Gateway** | Inference Engine | Google Gemini 2.5 Flash / Groq Fallback | Grounded reasoning, synthesis, command extraction |
| **Guardrails** | Input/Output Safety | NeMo Guardrails + Deterministic Interlocks | Hallucination prevention, plant control refusal |
| **Observability** | Structured Tracing | Logfire + OpenTelemetry | End-to-end distributed latency and event tracing |
| **Security** | Authentication & RBAC | JWT (RS256/HS256) + Passlib/Bcrypt | Cryptographic tokens and role enforcement |

---

## 5. Major Platform Capabilities

### 5.1 MASS Multimodal QA
- Ingests structured refinery procedures, P&IDs, equipment data sheets, and scanned PDFs.
- Implements hybrid dense-sparse retrieval combining Qdrant cosine similarity with BM25 lexical ranking via Reciprocal Rank Fusion (RRF).
- Reranks top 20 candidates using FlashRank cross-encoder to select top 5 evidence chunks.
- Validates context sufficiency; emits verbatim source citations (`document_name`, `page_number`, `bounding_box`, `similarity_score`).

### 5.2 Shift Handover & Operations Management
- Enforces an 8-state deterministic lifecycle (`DRAFT`, `SUBMITTED`, `PENDING_REVIEW`, `PENDING_ACKNOWLEDGEMENT`, `RETURNED`, `REJECTED`, `COMPLETED`, `CANCELLED`).
- Enforces role separation: Outgoing Operator drafts/submits, Shift Supervisor reviews/approves, Incoming Operator reviews safety checklist and acknowledges custody.
- Prevents concurrent edits via optimistic locking (`version` column checking).
- Tracks high-visibility safety-critical items (active LOTO isolations, SOL/IOW deviations, bypass permits).

### 5.3 Loop Engineering & ISA Instrumentation Intelligence
- Deterministic extraction and validation of ISA-5.1 equipment and instrument tags (`PT-101`, `C-101`, `JB-101`, `CBL-101`).
- Traces complete field signal paths: Field Sensor $\to$ Junction Box $\to$ Marshalling Cabinet $\to$ I/O Card $\to$ DCS Controller $\to$ SCADA.
- Detects discrepancies between P&IDs and Loop Diagrams (`LOOP_CONFIGURATION_CONFLICT`).

### 5.4 AI Harness & Human-In-The-Loop (HITL) Governance
- 4-tier risk classification: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- Hard safety interlock permanently denying physical equipment manipulation commands (`PHYSICAL_CONTROL_PROHIBITED`).
- Enforces human approval gates on `HIGH`-risk state changes with replay protection, timeout expiration, and separation of duties.

---

## 6. Implementation Status & Roadmap

| Step | Milestone | Status | Verification Baseline |
| :--- | :--- | :--- | :--- |
| **Step 1** | Baseline RAG Pipeline & Qdrant Freeze | ✅ COMPLETE | Verified (2,079 points, 3072 dims) |
| **Step 2** | Multi-Agent Contracts & Base Architecture | ✅ COMPLETE | Verified |
| **Step 3** | Agent Orchestrator & Router | ✅ COMPLETE | 64 / 64 tests passed |
| **Step 4** | QA Agent Adapter | ✅ COMPLETE | 10 / 10 tests passed |
| **Step 5** | Shift Handover Workflow Engine | ✅ COMPLETE | 14 / 14 tests passed |
| **Step 6** | PostgreSQL Shift Persistence Layer | ✅ COMPLETE | 20 / 20 tests passed |
| **Step 7** | Production Shift Handover Agent | ✅ COMPLETE | 25 / 25 tests passed |
| **Step 8** | Production API & Chatbot Transport | ✅ COMPLETE | 25 / 25 tests passed |
| **Step 9** | API Mesh Hardening & Loop Engineering Agent | ✅ COMPLETE | 40 / 40 tests passed |
| **Step 10**| AI Harness & HITL Risk-Based Governance | ✅ COMPLETE | 48 / 48 tests passed |
| **TOTAL** | **Enterprise Multi-Agent Platform** | **✅ 100% VERIFIED** | **291 / 291 Total Tests Passed** |

---

## 7. Related Documentation Map

- [01_SYSTEM_ARCHITECTURE.md](file:///d:/Chatboat/DOCS/01_SYSTEM_ARCHITECTURE.md) — Comprehensive technical architecture and subsystem diagrams.
- [02_BASELINE_RAG_QA.md](file:///d:/Chatboat/DOCS/02_BASELINE_RAG_QA.md) — Multimodal RAG pipeline and frozen Qdrant vector database.
- [06_SHIFT_HANDOVER_WORKFLOW.md](file:///d:/Chatboat/DOCS/06_SHIFT_HANDOVER_WORKFLOW.md) — Shift Handover state machine and operational transitions.
- [10_HARNESS_ENGINEERING.md](file:///d:/Chatboat/DOCS/10_HARNESS_ENGINEERING.md) — AI Harness governance, budget tracking, and secret sanitization.
- [11_HITL_HUMAN_IN_THE_LOOP.md](file:///d:/Chatboat/DOCS/11_HITL_HUMAN_IN_THE_LOOP.md) — Human-In-The-Loop authorization gates and risk management.
- [15_GLOSSARY.md](file:///d:/Chatboat/DOCS/15_GLOSSARY.md) — Operational and technical domain terminology.
