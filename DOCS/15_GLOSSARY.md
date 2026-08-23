# 15. Operational & Technical Domain Glossary

| Term | Category | Definition |
| :--- | :--- | :--- |
| **Alembic** | Infrastructure | Database schema migration management tool for SQLAlchemy and PostgreSQL. |
| **Agent Adapter** | Multi-Agent | Design pattern wrapping a specialized subsystem (e.g. frozen RAG) into the standard `BaseAgent` contract. |
| **Agent Orchestrator** | Multi-Agent | Central coordinator responsible for routing, executing single/composite tasks, and synthesizing results. |
| **Audit Trail** | Operations | Append-only, immutable historical record of state transitions, actor IDs, timestamps, and payload diffs. |
| **BM25** | Retrieval | Probabilistic lexical search algorithm scoring exact keyword and tag matches in documents. |
| **Citation** | RAG | Provenance metadata pointing to exact document name, page number, section, and text snippet backing an AI claim. |
| **DCS** | Plant Operations | Distributed Control System; the computerized control interface used by console operators. |
| **EOP** | Operations | Emergency Operating Procedure; formal technical guidelines for mitigating plant upsets. |
| **ESD** | Safety | Emergency Shutdown System; automated safety interlock system designed to safely trip units during major emergencies. |
| **FlashRank** | Retrieval | Ultra-fast CPU cross-encoder reranker rescoring hybrid candidate chunks based on query-passage relevance. |
| **Grounding** | RAG | Verification process ensuring LLM assertions are strictly supported by retrieved reference documentation. |
| **HITL** | Governance | Human-In-The-Loop; workflow governance requiring human confirmation before high-risk state changes occur. |
| **Intent Router** | Multi-Agent | Zero-token deterministic regex engine classifying incoming user prompts into domain intents. |
| **ISA-5.1** | Instrumentation | International standard defining naming conventions and symbols for process measurement and control instrumentation (e.g. `PT-101`). |
| **JWT** | Security | JSON Web Token; cryptographically signed token carrying authenticated user identity and operational roles. |
| **LOTO** | Safety | Lockout/Tagout; physical safety isolation procedure securing hazardous energy sources during maintenance. |
| **MASS QA** | Core Product | Multimodal Automated Semantic Search & Question Answering system for downstream refinery documentation. |
| **Optimistic Locking** | Database | Concurrency control mechanism using an integer `version` field to prevent lost updates during concurrent edits. |
| **P&ID** | Engineering | Piping & Instrumentation Diagram; detailed schematic showing piping, equipment, and instrumentation control loops. |
| **PTW** | Safety | Permit to Work; formal operational authorization required before executing hazardous maintenance tasks. |
| **Qdrant** | Database | High-performance vector database storing 3072-dimensional document embeddings in collection `mass_qa_multimodal`. |
| **RBAC** | Security | Role-Based Access Control; authorization model restricting operational actions based on user roles. |
| **RRF** | Retrieval | Reciprocal Rank Fusion; algorithm combining rank positions from dense (Qdrant) and sparse (BM25) searches. |
| **Safety Interlock** | Governance | Hardcoded pre-execution safety gate permanently blocking physical plant manipulation commands. |
| **Shift Handover** | Operations | Structured procedure and record transferring unit operational custody between outgoing and incoming crews. |
| **SOL / IOW** | Engineering | Safe Operating Limits / Integrity Operating Windows; operational pressure and temperature boundaries. |
| **SOP** | Operations | Standard Operating Procedure; approved step-by-step instructions for performing routine plant tasks. |
| **SSE** | Transport | Server-Sent Events; unidirectional HTTP streaming protocol used for real-time token and event delivery. |
| **State Machine** | Architecture | Mathematical model of computation governing allowed handover lifecycle states and transitions. |
