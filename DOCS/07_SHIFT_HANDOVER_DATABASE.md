# 07. PostgreSQL Persistence Layer & Shift Database Design

## 1. Purpose & Scope

This document details the **PostgreSQL 18 relational persistence layer** implemented in Step 6. It documents the entity relationship schema, SQLAlchemy 2.0 ORM models, Alembic migrations, optimistic concurrency control (`version` locking), JSONB operational structures, and immutable audit logging.

---

## 2. Relational Schema & Entity Relationships

```mermaid
erDiagram
    USERS ||--o{ SHIFT_HANDOVERS : "initiates / supervises"
    SHIFT_HANDOVERS ||--o{ SAFETY_CRITICAL_ITEMS : "contains (1:N)"
    SHIFT_HANDOVERS ||--o{ SHIFT_HANDOVER_AUDITS : "records history (1:N)"
    SHIFT_HANDOVERS ||--o{ HITL_APPROVAL_REQUESTS : "governs (1:N)"

    SHIFT_HANDOVERS {
        varchar(36) id PK
        varchar(32) workflow_version
        varchar(32) state
        varchar(64) unit_id
        varchar(128) unit_name
        varchar(16) shift_type
        varchar(32) shift_date
        varchar(64) outgoing_operator_id
        varchar(64) incoming_operator_id
        varchar(64) supervisor_id
        text operational_summary
        jsonb equipment_abnormalities
        jsonb open_permits
        jsonb loto_isolations
        jsonb carry_forward_actions
        boolean all_safety_items_acknowledged
        integer version
        timestamptz created_at
        timestamptz updated_at
        timestamptz submitted_at
        timestamptz completed_at
    }

    SAFETY_CRITICAL_ITEMS {
        varchar(36) id PK
        varchar(36) handover_id FK
        varchar(32) category
        varchar(64) equipment_tag
        text description
        boolean active
        boolean acknowledged_by_incoming
        timestamptz created_at
        timestamptz acknowledged_at
    }

    SHIFT_HANDOVER_AUDITS {
        varchar(36) id PK
        varchar(36) handover_id FK
        varchar(32) action
        varchar(32) from_state
        varchar(32) to_state
        varchar(64) actor_id
        varchar(64) actor_role
        text reason
        jsonb payload_diff
        varchar(64) request_id
        timestamptz timestamp
    }

    HITL_APPROVAL_REQUESTS {
        varchar(64) id PK
        varchar(64) request_id
        varchar(64) session_id
        varchar(64) handover_id FK
        varchar(64) action
        varchar(32) risk_level
        varchar(32) status
        varchar(64) requested_by
        varchar(64) required_role
        text decision_reason
        timestamptz expires_at
        timestamptz consumed_at
        integer expected_handover_version
    }
```

---

## 3. Database Models & Schema Definitions

### 3.1 `shift_handovers` Table (`app/db/models/shift_handover.py`)
- **Aggregate Root**: Encapsulates the complete shift turnover record.
- **Optimistic Concurrency**: Uses an integer column `version` incremented on each mutation.
- **Indexes**:
  - `ix_shift_handovers_unit_date`: Compound index on `(unit_id, shift_date)`.
  - `ix_shift_handovers_state`: Index on `state` for supervisor review queues.
  - `ix_shift_handovers_outgoing`: Index on `outgoing_operator_id`.

### 3.2 `shift_safety_critical_items` Table
- **Purpose**: Discrete, relational tracking of active Lockout/Tagout (LOTO) isolations, Emergency Shutdown (ESD) overrides, and Standing Alarms.
- **Foreign Key**: `handover_id` $\to$ `shift_handovers.id` with `ON DELETE CASCADE`.

### 3.3 `shift_handover_audits` Table
- **Purpose**: Append-only, immutable historical ledger recording every state change, actor ID, operational role, request correlation ID, and state transition payload.
- **Security**: Updates and deletes are prohibited at the application layer.

### 3.4 `hitl_approval_requests` Table (`app/db/models/hitl_approval.py`)
- **Purpose**: Persists pending and decided Human-In-The-Loop approval gates, expiration windows, decider signatures, and concurrency versions.

---

## 4. Optimistic Concurrency Control (`version` column)

To prevent the "lost update" problem when multiple operators or engineers view and edit a draft simultaneously, the repository enforces optimistic locking:

```python
# In ShiftHandoverRepository.update_handover():
current_version = handover.version
stmt = (
    update(ShiftHandoverModel)
    .where(ShiftHandoverModel.id == handover_id)
    .where(ShiftHandoverModel.version == current_version)
    .values(**updated_fields, version=current_version + 1)
)
result = session.execute(stmt)
if result.rowcount == 0:
    session.rollback()
    raise ConcurrencyConflictError(
        f"Handover {handover_id} was modified by another user. Version mismatch (expected v{current_version})."
    )
```

If a concurrent update occurred, `ConcurrencyConflictError` is raised, mapped by FastAPI to `HTTP 409 CONFLICT` with client message *"Another user modified this handover. Please refresh and try again."*

---

## 5. Persistence Service & Repository Flow

```mermaid
sequenceDiagram
    autonumber
    participant Agent as ShiftHandoverAgent
    participant Service as ShiftHandoverService
    participant Engine as WorkflowEngine
    participant Repo as ShiftHandoverRepository
    participant DB as PostgreSQL 18

    Agent->>Service: submit_handover(db, handover_id, actor_id, actor_role)
    Service->>Repo: get_by_id(handover_id)
    Repo->>DB: SELECT * FROM shift_handovers WHERE id = ...
    DB-->>Repo: ShiftHandoverModel
    Repo-->>Service: ShiftHandover domain object (v1, State: DRAFT)
    
    Service->>Engine: execute_transition(DRAFT, SUBMIT, actor_role)
    Engine-->>Service: Validated (State: SUBMITTED)
    
    Service->>Repo: update_state_and_audit(handover_id, from_state=DRAFT, to_state=SUBMITTED, expected_version=1)
    Repo->>DB: UPDATE shift_handovers SET state='SUBMITTED', version=2 WHERE id=... AND version=1
    Repo->>DB: INSERT INTO shift_handover_audits (action, from_state, to_state, actor_id, ...)
    DB-->>Repo: 1 Row Updated
    Repo-->>Service: Success
    Service-->>Agent: Updated Model
```

---

## 6. Verification & Testing

- **Test Suite**: [`tests/test_shift_handover_persistence.py`](file:///d:/Chatboat/tests/test_shift_handover_persistence.py)
- **Verified Baseline**: **20 / 20 tests PASSED**.
- **Coverage**:
  - Full CRUD operations and relational mapping.
  - Optimistic concurrency conflict rejection (concurrent write simulation).
  - Transaction rollback on mid-operation validation failure.
  - Immutable audit trail recording and historical diff queries.

---

## 7. Related Documentation

- [06_SHIFT_HANDOVER_WORKFLOW.md](file:///d:/Chatboat/DOCS/06_SHIFT_HANDOVER_WORKFLOW.md) — Workflow state machine rules.
- [08_SHIFT_HANDOVER_AGENT.md](file:///d:/Chatboat/DOCS/08_SHIFT_HANDOVER_AGENT.md) — Shift Handover agent calling this persistence layer.
- [11_HITL_HUMAN_IN_THE_LOOP.md](file:///d:/Chatboat/DOCS/11_HITL_HUMAN_IN_THE_LOOP.md) — HITL approval table and staleness checks.
