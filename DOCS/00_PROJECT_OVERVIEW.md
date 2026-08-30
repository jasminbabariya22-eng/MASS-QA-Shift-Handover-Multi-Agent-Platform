# 00. MASS QA & Shift Handover Platform — Project Overview

## 1. Executive Summary & Purpose

The **MASS QA & Shift Handover Multi-Agent Platform** is an enterprise-grade technical intelligence and operations governance system engineered for downstream Oil & Gas operations, refineries, and complex industrial processing plants.

The platform unifies three core capabilities:
1. **MASS QA (Multimodal Technical Intelligence)**: High-accuracy, grounded question answering over complex refinery documentation—including Standard Operating Procedures (SOPs), Emergency Operating Procedures (EOPs), Piping & Instrumentation Diagrams (P&IDs), Instrument Loop Diagrams, Equipment Manuals, Safety Data Sheets (SDS), and incident records.
2. **Shift Handover & Operations Governance**: A deterministic state-machine and Human-In-The-Loop (HITL) workflow managing unit custody transitions, safety-critical isolations (LOTO), open work permits (PTW), standing alarms, and carry-forward operator actions across 12-hour shift cycles.
3. **Multimodal Audio Voice Ingestion & Quality Gate**: Automated speech-to-text transcription via Gemini 3.6 Flash and a 0-100% Quality Gate Engine to evaluate shift log completeness.

---

## 2. Industrial Problem & Operational Use Case

In petrochemical processing units (such as Crude Distillation Units, Hydrocrackers, Catalytic Reformers, and Gas Separation Plants), operational failures frequently occur at two critical interfaces:
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
        ┌─────────────────────────────┴─────────────────────────────┐
        ▼                                                           ▼
  QA Technical Agent                                       Shift Handover Agent
(MASS QA RAG Adapter)                                    (Deterministic Workflow & Voice)
        │                                                           │
        ▼                                                           ▼
  Frozen RAG Engine                                           Shift Service
(Hybrid Qdrant + BM25)                                   (PostgreSQL Persistence)
        │                                                           │
        ▼                                                           ▼
 Qdrant Vector DB (3072d)                                  PostgreSQL 18 Database
(mass_qa_multimodal)                                     (Audit, Handovers, Users)
```

---

## 4. Multi-Agent Mesh & Peer-to-Peer (P2P) Strategy

The platform deploys two specialized domain agents that communicate via both a **Central Mediator Orchestrator** and a **Bidirectional Multi-Turn P2P Channel**:

| Agent ID | Name | Core Responsibilities | Data Store |
| :--- | :--- | :--- | :--- |
| `qa_technical_agent` | MASS QA Technical Agent | Technical SOP lookup, equipment specs, P&ID diagram verification, grounded engineering answers | Frozen Qdrant Cloud (`mass_qa_multimodal`) |
| `shift_handover_agent` | MASS Shift Handover Agent | Shift turnover FSM, LOTO items, Gemini field voice note ingestion, AI Quality Gate (0-100%) | PostgreSQL 18 Relational DB (`Mass`) |

### Peer-to-Peer (P2P) Communication Protocol ([`app/agents/p2p.py`](file:///d:/Chatboat/app/agents/p2p.py))
When a field voice note or operator query requires both shift log updates and engineering document retrieval, agents establish a **Bidirectional P2P Peer Channel** (`p2p_negotiate`) to exchange shared state dictionaries, ask follow-up questions, and return a unified composite response.

---

## 5. Technology Stack & Model Mesh Catalog

| Layer | Component / Tool | Technology & Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Transport / API** | REST API Gateway | FastAPI 0.115+, Uvicorn, AnyIO | Asynchronous API gateway with OpenAPI docs |
| **Streaming** | SSE (Server-Sent Events) | `sse-starlette` | Token-by-token and progress event streaming |
| **User Interface** | Operations Portal | Streamlit | Responsive UI with live voice recorder & KPI cards |
| **Model Gateway** | Model Mesh Gateway | Portkey / Mesh API (`MESH_API_KEY`) | Dynamic model routing & resilience fallback |
| **Model 1 (Planner)** | LLaMA-3.1 8B Instant | `llama-3.1-8b-instant` | ⚡ Sub-100ms intent classification & planning |
| **Model 2 (Conversational)**| Mixtral 8x7B MoE | `mixtral-8x7b-32768` | ⚖️ Cost-balanced conversational synthesis |
| **Model 3 (Heavy RAG)** | LLaMA-3.3 70B Versatile | `llama-3.3-70b-versatile` | 🧠 High-capacity technical reasoning |
| **Voice Transcriber** | Multimodal Audio Engine | Gemini 3.6 Flash (`gemini-3.6-flash`) | Audio-to-text transcription (.wav, .mp3, .m4a) |
| **Vector DB** | Dense Embeddings Store | Qdrant (`mass_qa_multimodal`) | 2,079 points, 3072 dimensions, Cosine distance |
| **Sparse Index** | Lexical Retrieval | BM25 (`rank-bm25`) | Exact keyword, equipment tag, and SOP code matching |
| **Relational DB** | Operational Persistence | PostgreSQL 18 (SQLAlchemy) | Handovers, audit logs, safety items, user accounts |
