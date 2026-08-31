# 14. Testing Strategy, Deployment & Operational Runbook

## 1. Purpose & Scope

This document details the **Testing Strategy**, **Verified Test Baselines**, **Deployment Architecture (Docker/Compose)**, **Database Migration Workflows (Alembic)**, and **Operational Runbooks** for production reliability.

---

## 2. Cost-Conscious Incremental Testing Strategy

```
================================================================================
CRITICAL TESTING DIRECTIVE
================================================================================
DO NOT RERUN THE ENTIRE HISTORICAL TEST SUITE ON EVERY CODE CHANGE.
Historical test suites represent already-verified baselines.
Future development must execute:
1. Focused tests for the newly created or modified component.
2. Targeted regression tests ONLY if shared interfaces were altered.
3. Full suite execution is reserved strictly for Release Candidates.
================================================================================
```

### Verified Baseline Test Registry (291 Total Scenarios):
| Step / Component | Test Suite Path | Scenarios | Status |
| :--- | :--- | :--- | :--- |
| **Step 3**: Orchestrator & Router | `tests/test_agent_orchestrator.py` | 64 / 64 | ✅ VERIFIED |
| **Step 4**: QA Agent Adapter | `tests/test_qa_agent.py` | 10 / 10 | ✅ VERIFIED |
| **Step 4**: Targeted Regressions | `tests/test_orchestrator_regression.py` | 11 / 11 | ✅ VERIFIED |
| **Step 5**: Shift Workflow Engine | `tests/test_shift_handover_workflow.py` | 14 / 14 | ✅ VERIFIED |
| **Step 6**: PostgreSQL Persistence | `tests/test_shift_handover_persistence.py` | 20 / 20 | ✅ VERIFIED |
| **Step 7**: Shift Handover Agent | `tests/test_shift_agent.py` | 25 / 25 | ✅ VERIFIED |
| **Step 8**: Production API Gateway | `tests/test_production_api.py` | 25 / 25 | ✅ VERIFIED |
| **Step 9**: API Mesh & Gateway | `tests/test_api_mesh.py` | 24 / 24 | ✅ VERIFIED |
| **Step 9**: Loop Engineering Agent | `tests/test_loop_engineering_agent.py` | 16 / 16 | ✅ VERIFIED |
| **Step 10**: AI Harness Governance | `tests/test_harness.py` | 28 / 28 | ✅ VERIFIED |
| **Step 10**: HITL Risk Governance | `tests/test_hitl_governance.py` | 20 / 20 | ✅ VERIFIED |
| **TOTAL VERIFIED SUITE** | — | **291 / 291** | **✅ 100% PASSING** |

---

## 3. Production Deployment Architecture

```mermaid
flowchart TD
    subgraph Host["Production Node / Kubernetes Cluster"]
        FASTAPI["FastAPI App Container (:8000)<br/>(Uvicorn Multi-Worker)"]
        STREAMLIT["Streamlit UI Container (:8501)"]
        POSTGRES[("PostgreSQL 18 Container (:5432)<br/>(Persistent Volume)")]
        REDIS[("Redis Container (:6379)<br/>(Query Cache)")]
        QDRANT[("Qdrant Container (:6333)<br/>(mass_qa_multimodal Volume)")]
    end

    STREAMLIT --> FASTAPI
    FASTAPI --> POSTGRES
    FASTAPI --> REDIS
    FASTAPI --> QDRANT
```

### 3.1 Environment Configuration (`.env`)
```bash
# Database & Cache
DATABASE_URL=postgresql://mass_user:secret_password@localhost:5432/mass_db
REDIS_URL=redis://localhost:6379/0

# Qdrant Vector Store (Frozen)
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=mass_qa_multimodal

# LLM Providers
GEMINI_API_KEY=AIzaSy...
GROQ_API_KEY=gsk_...

# Security & Tokens
JWT_SECRET_KEY=super-secret-cryptographic-key-32-chars-min
ACCESS_TOKEN_EXPIRE_MINUTES=480
CORS_ALLOWED_ORIGINS=["http://localhost:8501", "https://refinery-ops.corp"]

# Observability
LOGFIRE_TOKEN=your-logfire-token
```

### 3.2 Database Migration Runbook (Alembic)
```bash
# Check current database revision
alembic current

# Run pending database migrations
alembic upgrade head

# Rollback single migration
alembic downgrade -1
```

---

## 4. Operational Health & Probes

### 4.1 Liveness Probe (`GET /health`)
Returns HTTP 200 with status of core dependencies:
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "qdrant": "connected (2079 points)",
  "version": "3.2.0"
}
```

### 4.2 Readiness Probe (`GET /ready`)
Verifies that database connection pool is active and LLM gateway credentials are initialized before accepting ingress traffic.

---

## 5. Operational Troubleshooting Runbook

| Alert / Issue | Diagnostic Command | Immediate Remediation |
| :--- | :--- | :--- |
| **Database Concurrency Conflicts (HTTP 409)** | Inspect logs for `version` column collisions | Normal operational behavior when two users edit draft simultaneously; notify user to refresh. |
| **Qdrant Vector DB Unavailable** | `curl http://localhost:6333/collections/mass_qa_multimodal` | Ensure Qdrant storage volume is mounted read-only; restart Qdrant container. |
| **Upstream LLM Rate Limits** | Check `app/gateway/client.py` log events | Automatic fallback to Groq handles transient spikes; verify API quotas. |
| **Redis Cache Outage** | Inspect `app/services/cache/` warnings | `CacheService` automatically fails over to in-memory dictionary; zero downtime. |

---

## 6. Related Documentation

- [01_SYSTEM_ARCHITECTURE.md](file:///d:/Chatboat/DOCS/01_SYSTEM_ARCHITECTURE.md) — System layer architecture.
- [07_SHIFT_HANDOVER_DATABASE.md](file:///d:/Chatboat/DOCS/07_SHIFT_HANDOVER_DATABASE.md) — PostgreSQL persistence models.
- [12_SECURITY_OBSERVABILITY_CACHING.md](file:///d:/Chatboat/DOCS/12_SECURITY_OBSERVABILITY_CACHING.md) — Observability setup.
