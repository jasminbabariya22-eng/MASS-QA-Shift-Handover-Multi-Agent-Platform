# 10. AI Harness Engineering & Execution Governance

## 1. Purpose & Scope

This document details the **Production AI Harness (`AIHarness`)** implemented in `app/harness/`. It explains the governance framework wrapping agent execution, resource budgeting, recursive agent loop detection, credential sanitization, and output grounding validation.

---

## 2. The Core AI Harness Philosophy

In enterprise industrial software, **unconstrained autonomous agents are dangerous**. Probabilistic language models can hallucinate, enter recursive execution loops, or emit invalid data structures.

The AI Harness establishes a deterministic execution container around the multi-agent system:

$$\begin{aligned}
\mathbf{LLM} &\implies \text{Natural Language Interpretation \& Synthesis (Assistance)} \\
\mathbf{Deterministic\ Code} &\implies \text{Business Rules, Workflow Transitions, Authorization \& Validation} \\
\mathbf{PostgreSQL\ Database} &\implies \text{Authoritative Source of Truth}
\end{aligned}$$

```mermaid
flowchart TD
    CLIENT["Incoming User Request"] --> HARNESS["AI Harness Container Boundary"]
    
    subgraph Pre_Execution_Gates["Pre-Execution Governance"]
        HARNESS --> AUTH_GATE["1. Authentication & Context Gate"]
        AUTH_GATE --> RBAC_GATE["2. RBAC & Tool Permission Check"]
        RBAC_GATE --> SAFETY_GATE["3. Safety Interlock Gate<br/>(Physical Control Check)"]
        SAFETY_GATE --> BUDGET_GATE["4. Execution Budget & Depth Tracker"]
    end

    BUDGET_GATE --> ORCH["Agent Orchestrator Execution<br/>(Bounded Transient Retries)"]

    subgraph Post_Execution_Gates["Post-Execution Governance"]
        ORCH --> GROUND_VAL["5. Grounding & Citation Validator"]
        GROUND_VAL --> CONFLICT_VAL["6. ISA Engineering Conflict Check"]
        CONFLICT_VAL --> SECRET_MASK["7. Secret & Stack Trace Sanitizer"]
        SECRET_MASK --> AUDIT_LOG["8. Audit & Telemetry Recorder"]
    end

    AUDIT_LOG --> RESP["Validated Safe Response to Client"]
```

---

## 3. Subsystem Governance Modules (`app/harness/`)

### 3.1 Tool Permission Whitelist (`app/harness/permissions.py`)
Agents are strictly restricted to whitelisted capabilities:
- `ToolPermission.READ_KNOWLEDGE_BASE`: Permitted for `QAAgentAdapter`, `LoopEngineeringAgent`.
- `ToolPermission.WRITE_SHIFT_HANDOVER`: Permitted for `ShiftHandoverAgent` (when user has Operator role).
- `ToolPermission.APPROVE_SHIFT_HANDOVER`: Permitted ONLY for `SHIFT_SUPERVISOR`.
- `ToolPermission.REMOTE_EQUIPMENT_CONTROL`: **PERMANENTLY DENIED TO ALL ROLES AND AGENTS.**

### 3.2 Pre-Execution Safety Interlock (`app/harness/safety.py`)
Scans prompts for physical plant commands (`trip`, `shut down`, `open valve`, `close valve`, `bypass ESD`, `override alarm`). Intercepts immediately with `HarnessPolicyDecision.DENY` and reason `PHYSICAL_CONTROL_PROHIBITED`.

### 3.3 Execution Budget & Loop Detection (`app/harness/budget.py`)
- **Wall-clock Timeout**: Default 30.0s execution limit.
- **Maximum Depth**: Disallows nested agent dispatches beyond depth 3 (`AgentDepthExceededError`).
- **Cyclic Loop Detection**: Tracks the execution trace. If an alternating sequence (e.g. `[A, B, A, B]`) or duplicate cascade (`[A, A, A]`) occurs, execution is immediately halted with `AgentLoopDetectedError`.

### 3.4 Bounded Retry Policy
- **Transient Failures (Retried)**: Network connection reset, HTTP 503, database deadlock, embedding timeout (max 2 retries with exponential backoff).
- **Permanent Failures (Never Retried)**: Safety refusals, authorization denials, validation errors, terminal state rejections.

### 3.5 Secret Sanitization & Error Shielding (`app/harness/validator.py`)
Before any response is delivered to the client, the validator executes regex sanitization:
- Masks database connection strings: `postgresql://user:pass@host/db` $\to$ `[REDACTED_DATABASE_URI]`.
- Masks API keys: `sk-proj-...`, `AIzaSy...` $\to$ `[REDACTED_API_KEY]`.
- Masks internal IP addresses: `10.x.x.x`, `192.168.x.x` $\to$ `[REDACTED_IP]`.
- Shields raw Python tracebacks behind user-friendly error codes.

---

## 4. Verification & Testing

- **Test Suite**: [`tests/test_harness.py`](file:///d:/Chatboat/tests/test_harness.py)
- **Verified Baseline**: **28 / 28 tests PASSED**.
- **Coverage**:
  - Authentication propagation and RBAC enforcement.
  - Hard safety refusal on physical plant actuation commands.
  - Cyclic agent loop detection and depth truncation.
  - Output citation validation and secret redaction.
  - Transient retry execution and permanent error bypass.

---

## 5. Related Documentation

- [01_SYSTEM_ARCHITECTURE.md](file:///d:/Chatboat/DOCS/01_SYSTEM_ARCHITECTURE.md) — System layer architecture.
- [04_AGENT_ORCHESTRATOR_ROUTER.md](file:///d:/Chatboat/DOCS/04_AGENT_ORCHESTRATOR_ROUTER.md) — Orchestrator mechanics.
- [11_HITL_HUMAN_IN_THE_LOOP.md](file:///d:/Chatboat/DOCS/11_HITL_HUMAN_IN_THE_LOOP.md) — Human-In-The-Loop approval gates.
