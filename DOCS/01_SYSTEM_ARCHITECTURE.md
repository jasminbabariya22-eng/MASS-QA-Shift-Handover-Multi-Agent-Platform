# 01. MASS QA & Shift Handover Platform — System Architecture

## 1. Purpose & Scope

This document provides the definitive architectural blueprint for the **MASS QA & Shift Handover Multi-Agent Platform**. It details every subsystem layer, communication interface, failure containment boundary, security boundary, and data boundary across the entire application stack.

---

## 2. End-to-End System Topology

```mermaid
flowchart TD
    subgraph Client_Layer["Client Layer"]
        UI["Streamlit Operations UI (:8501)"]
        REST["REST API Clients / Swagger Docs"]
    end

    subgraph Transport_Layer["API Gateway Layer (:8000)"]
        CORR["GatewayCorrelationMiddleware<br/>(X-Request-ID, X-Session-ID)"]
        SEC["SecurityHeadersMiddleware<br/>(HSTS, CSP, X-Frame-Options)"]
        CORS["CORSMiddleware<br/>(Allowed Origins)"]
        RATE["Rate Limiter<br/>(Token Bucket / IP Sliding Window)"]
        AUTH["JWT Authentication & Claims Extraction<br/>(RS256 / HS256)"]
        FASTAPI["FastAPI App Core<br/>(/query, /query/stream, /approvals, /handovers)"]
    end

    subgraph Governance_Layer["AI Harness & HITL Governance Layer"]
        HARNESS["AI Harness Wrapper<br/>(app/harness/harness.py)"]
        SAFETY["Safety Interlock<br/>(app/harness/safety.py)"]
        PERM["Tool Permission Whitelist<br/>(app/harness/permissions.py)"]
        BUDGET["Execution Budget Tracker<br/>(app/harness/budget.py)"]
        HITL["HITL Governance Gate<br/>(app/governance/hitl.py)"]
        VALIDATOR["Output Validator & Secret Sanitizer<br/>(app/harness/validator.py)"]
    end

    subgraph Agent_Layer["Agent Orchestration Layer"]
        ORCH["Agent Orchestrator<br/>(app/agents/orchestrator.py)"]
        ROUTER["Intent Router<br/>(app/agents/router.py)"]
        REGISTRY["Agent Registry<br/>(app/agents/registry.py)"]
        QA_AGT["QA Technical Agent Adapter<br/>(app/agents/qa_agent.py)"]
        SHIFT_AGT["Shift Handover Agent<br/>(app/agents/shift/agent.py)"]
        LOOP_AGT["Loop Engineering Agent<br/>(app/agents/loop/agent.py)"]
    end

    subgraph Domain_Services["Domain Services Layer"]
        RAG_SRV["Frozen RAG Service<br/>(app/services/generation/)"]
        SHIFT_SRV["Shift Handover Service<br/>(app/services/shift_handover_service.py)"]
        WF_ENG["Deterministic Workflow Engine<br/>(app/agents/shift/workflow.py)"]
        LOOP_SRV["Loop Engineering Service<br/>(app/agents/loop/service.py)"]
        CACHE_SRV["Multi-Level Cache Service<br/>(Redis + Memory)"]
    end

    subgraph Infrastructure_Layer["Storage & LLM Layer"]
        QDRANT[("Qdrant Vector DB<br/>mass_qa_multimodal<br/>2,079 pts, 3072d, FROZEN")]
        BM25[("BM25 Inverted Index<br/>(Local Disk Cache)")]
        POSTGRES[("PostgreSQL 18 Database<br/>(Public Schema Tables)")]
        REDIS[("Redis Cache (:6379)<br/>(Volatile Query Cache)")]
        LLM_POOL["Resilient LLM Gateway Pool<br/>(Google Gemini 2.5 Flash / Groq)"]
    end

    UI --> CORR
    REST --> CORR
    CORR --> SEC --> CORS --> RATE --> AUTH --> FASTAPI
    FASTAPI --> HARNESS
    HARNESS --> SAFETY
    HARNESS --> PERM
    HARNESS --> BUDGET
    HARNESS --> HITL
    HARNESS --> ORCH
    ORCH --> ROUTER --> REGISTRY
    REGISTRY --> QA_AGT & SHIFT_AGT & LOOP_AGT
    QA_AGT --> RAG_SRV
    SHIFT_AGT --> SHIFT_SRV --> WF_ENG
    LOOP_AGT --> LOOP_SRV
    RAG_SRV --> QDRANT & BM25 & LLM_POOL & CACHE_SRV
    SHIFT_SRV --> POSTGRES
    CACHE_SRV --> REDIS
    HARNESS --> VALIDATOR --> FASTAPI
```

---

## 3. Detailed Subsystem Layers

### 3.1 Transport & API Gateway Layer
- **Location**: [`app/main.py`](file:///d:/Chatboat/app/main.py), [`app/security/middleware.py`](file:///d:/Chatboat/app/security/middleware.py)
- **Responsibilities**:
  - Intercepts all incoming HTTP requests and assigns unique `X-Request-ID` and `X-Session-ID` correlation identifiers.
  - Applies strict security response headers (`Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`).
  - Decodes and cryptographically verifies JWT Bearer tokens, injecting user claims (`user_id`, `role`, `session_id`) into `request.state`.
  - Enforces sliding-window IP rate limiting to protect LLM endpoints from abuse.
  - Serves Server-Sent Events (SSE) via `/query/stream` for real-time token streaming.

### 3.2 AI Harness & Governance Layer
- **Location**: [`app/harness/`](file:///d:/Chatboat/app/harness/), [`app/governance/`](file:///d:/Chatboat/app/governance/)
- **Responsibilities**:
  - **Pre-execution Safety Interlock**: Intercepts physical equipment control commands (e.g. `trip compressor`, `open valve`, `bypass ESD`) and raises `PHYSICAL_CONTROL_PROHIBITED`.
  - **Tool Permission Matrix**: Enforces strict capability whitelists per role and agent (`ToolPermission.REMOTE_EQUIPMENT_CONTROL` is permanently disabled).
  - **Execution Budget Tracker**: Enforces maximum execution wall-clock time (default 30.0s), recursion depth (max 3), and cyclic loop detection (`[A, B, A, B]` or `[A, A, A]`).
  - **Output Validator & Sanitizer**: Validates citation grounding, verifies ISA engineering conflict reporting, and sanitizes leaked API keys (`sk-...`, `AIza...`), database credentials (`postgresql://...`), and stack traces.

### 3.3 Agent Orchestration Layer
- **Location**: [`app/agents/orchestrator.py`](file:///d:/Chatboat/app/agents/orchestrator.py), [`app/agents/router.py`](file:///d:/Chatboat/app/agents/router.py), [`app/agents/registry.py`](file:///d:/Chatboat/app/agents/registry.py)
- **Responsibilities**:
  - **Intent Routing**: Analyzes user prompts via zero-token deterministic regexes and keyword matching to identify single or composite agent intents (`QA`, `SHIFT_HANDOVER`, `LOOP_ENGINEERING`, `MULTI_AGENT`).
  - **Agent Registry**: Maintains an extensible catalog of `BaseAgent` instances with capability metadata.
  - **Composite Execution**: For requests requiring multi-agent collaboration (e.g. logging an abnormality in shift handover and retrieving the relevant SOP), dispatches sequential subtasks and aggregates results into a unified payload with full audit traces (`a2a_trace`).

### 3.4 Domain Services Layer
- **Location**: [`app/services/`](file:///d:/Chatboat/app/services/), [`app/agents/shift/workflow.py`](file:///d:/Chatboat/app/agents/shift/workflow.py), [`app/agents/loop/service.py`](file:///d:/Chatboat/app/agents/loop/service.py)
- **Responsibilities**:
  - **Shift Handover Workflow Engine**: Authoritative deterministic state machine enforcing all 8 handover states, transition rules, role permissions, and safety checklist acknowledgements.
  - **Loop Engineering Service**: In-memory and RAG-grounded ISA-5.1 tag resolution, signal path graph traversal, and cross-document discrepancy checking.
  - **RAG Generation Service**: Hybrid candidate retrieval, FlashRank reranking, context assembly, and Gemini LLM prompt synthesis.

### 3.5 Infrastructure & Storage Layer
- **Qdrant Vector Database**: Houses 2,079 multimodal vectors in `mass_qa_multimodal` (3072 dimensions, Cosine distance). This collection is **PERMANENTLY FROZEN**.
- **PostgreSQL 18 Database**: Persists shift handovers (`shift_handovers`), safety items (`shift_safety_critical_items`), audit logs (`shift_handover_audits`), HITL approvals (`hitl_approval_requests`), users, conversations, and query metrics.
- **Redis Cache**: Volatile query caching with fallback to in-memory TTL dictionary.

---

## 4. Subsystem Boundaries & Security Invariants

| Boundary | Enforcement Mechanism | Failure / Violation Behavior |
| :--- | :--- | :--- |
| **Physical Control Boundary** | Regex Interlock in `HarnessSafetyPolicy` & `IntentRouter` | Immediate refusal (`PHYSICAL_CONTROL_PROHIBITED`); zero downstream agent invocation. |
| **State Mutation Boundary** | Authoritative checks in `ShiftHandoverWorkflowEngine` | Role / state mismatch raises `InvalidTransitionError` or `UnauthorizedRoleError` (HTTP 400/403). |
| **Vector DB Boundary** | Permanent read-only constraint on `mass_qa_multimodal` | Code forbids any insert, update, delete, or schema alteration. |
| **Concurrency Boundary** | Optimistic locking via `version` column in PostgreSQL | Concurrent update mismatch raises `ConcurrencyConflictError` (HTTP 409). |
| **Cache Safety Boundary** | Explicit bypass in `CacheService` for all shift handover queries | Shift state is NEVER cached; live database state is always authoritative. |
| **Secret Sanitization Boundary**| Regex scrubber in `HarnessOutputValidator` | Masked with `[REDACTED_API_KEY]`, `[REDACTED_CREDENTIAL]`, `[REDACTED_IP]`. |

---

## 5. Request-to-Response Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor User as Operational User
    participant Gateway as FastAPI Gateway
    participant Harness as AI Harness
    participant Orch as Agent Orchestrator
    participant Agent as Specialized Agent
    participant Service as Domain Service
    participant DB as PostgreSQL / Qdrant
    participant LLM as LLM Inference Gateway

    User->>Gateway: POST /query (Prompt + JWT Token)
    Gateway->>Gateway: Validate JWT & Assign Request-ID
    Gateway->>Harness: execute(HarnessRequest)
    Harness->>Harness: Check Safety Interlock & Tool Permissions
    Harness->>Orch: route_and_execute(AgentRequest)
    Orch->>Orch: IntentRouter.classify_intent()
    Orch->>Agent: agent.execute(AgentContext)
    Agent->>Service: invoke_service_action()
    Service->>DB: Query / Mutate (PostgreSQL / Qdrant)
    DB-->>Service: Record / Vectors
    Service->>LLM: Generate Grounded Synthesis (if RAG)
    LLM-->>Service: Structured Response + Citations
    Service-->>Agent: Domain Result
    Agent-->>Orch: AgentResult
    Orch-->>Harness: Unvalidated Result
    Harness->>Harness: Validate Grounding, Citations & Sanitize Secrets
    Harness->>DB: Record Audit Trail (shift_handover_audits)
    Harness-->>Gateway: HarnessResponse
    Gateway-->>User: ProductionQueryResponse (HTTP 200)
```

---

## 6. Related Documentation

- [00_PROJECT_OVERVIEW.md](file:///d:/Chatboat/DOCS/00_PROJECT_OVERVIEW.md) — High-level project summary and business background.
- [04_AGENT_ORCHESTRATOR_ROUTER.md](file:///d:/Chatboat/DOCS/04_AGENT_ORCHESTRATOR_ROUTER.md) — Orchestrator mechanics and intent routing rules.
- [07_SHIFT_HANDOVER_DATABASE.md](file:///d:/Chatboat/DOCS/07_SHIFT_HANDOVER_DATABASE.md) — PostgreSQL persistence models and schema.
- [12_SECURITY_OBSERVABILITY_CACHING.md](file:///d:/Chatboat/DOCS/12_SECURITY_OBSERVABILITY_CACHING.md) — Security policies, telemetry, and caching invariants.
