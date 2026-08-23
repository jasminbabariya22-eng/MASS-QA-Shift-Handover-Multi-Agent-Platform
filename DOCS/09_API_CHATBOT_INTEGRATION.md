# 09. Production API Gateway & Chatbot Integration

## 1. Purpose & Scope

This document details the **FastAPI Production API Gateway** implemented in `app/main.py`, `app/security/middleware.py`, and `app/security/rate_limiter.py`. It documents all REST endpoints, SSE streaming contracts, JWT authentication mechanics, error status code mappings, security headers, and rate limiting controls.

---

## 2. API Endpoint Catalog

| HTTP Method | Route Path | Versioned Alias | Auth Required | Description |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/query` | `/api/v1/query` | Yes (JWT) | Synchronous conversational & operational dispatch. |
| `POST` | `/query/stream` | `/api/v1/query/stream` | Yes (JWT) | Asynchronous Server-Sent Events (SSE) token stream. |
| `POST` | `/api/v1/auth/token` | — | No | Generates access JWT from user credentials. |
| `GET` | `/approvals` | `/api/v1/approvals` | Yes (JWT) | List HITL approval requests. |
| `GET` | `/approvals/{id}` | `/api/v1/approvals/{id}` | Yes (JWT) | Retrieve detailed approval payload. |
| `POST` | `/approvals/{id}/approve` | `/api/v1/approvals/{id}/approve` | Yes (JWT) | Approves request and executes workflow transition. |
| `POST` | `/approvals/{id}/reject` | `/api/v1/approvals/{id}/reject` | Yes (JWT) | Rejects request with mandatory operational reason. |
| `POST` | `/approvals/{id}/return` | `/api/v1/approvals/{id}/return` | Yes (JWT) | Returns request to operator for rework. |
| `GET` | `/health` | `/api/v1/health` | No | Liveness probe (DB, Redis, Qdrant status). |
| `GET` | `/ready` | `/api/v1/ready` | No | Readiness probe for Kubernetes/Docker ingress. |
| `GET` | `/agents` | `/api/v1/agents` | No | Catalog of registered agents and capabilities. |

---

## 3. Request & Response Payloads

### 3.1 `POST /query` Request Body (`ProductionQueryRequest`)
```json
{
  "question": "Show startup procedure for crude charge pump P-101 and check current shift status",
  "session_id": "sess-c489-4822",
  "conversation_id": "conv-9912",
  "top_k": 5,
  "use_cache": true,
  "stream": false
}
```

### 3.2 `POST /query` Success Response (`ProductionQueryResponse`)
```json
{
  "request_id": "req-891a-4281",
  "session_id": "sess-c489-4822",
  "conversation_id": "conv-9912",
  "message_id": "msg-0012",
  "question": "Show startup procedure for crude charge pump P-101...",
  "answer": "According to SOP-CDU-04 (Section 3.1), the startup procedure for P-101 requires...",
  "citations": [
    {
      "document_name": "CDU_Standard_Operating_Procedures.pdf",
      "page_number": 12,
      "section": "Section 3.1: Charge Pump Priming",
      "snippet": "Ensure suction valve is 100% open and seal flush pressure exceeds 2.5 barg...",
      "score": 0.89,
      "bounding_box": null
    }
  ],
  "query_type": "TECHNICAL_QA",
  "confidence": "HIGH",
  "status": "SUCCESS",
  "requires_clarification": false,
  "error": null,
  "metadata": {
    "cached": false,
    "agent_id": "qa_technical_agent",
    "retrieval_count": 5,
    "grounded": true,
    "total_latency_ms": 412.5
  }
}
```

---

## 4. Server-Sent Events (SSE) Streaming (`/query/stream`)

When streaming is requested, the endpoint returns `text/event-stream` with chunk events:

```
event: intent_detected
data: {"intent": "QA", "agent_id": "qa_technical_agent"}

event: token
data: {"token": "According to "}

event: token
data: {"token": "SOP-CDU-04, "}

event: citation
data: {"document_name": "CDU_Standard_Operating_Procedures.pdf", "page_number": 12}

event: done
data: {"status": "completed", "total_latency_ms": 380.2}
```

---

## 5. HTTP Error Code & Exception Mapping

The Gateway catches domain exceptions and normalizes them into structured RFC 7807 JSON error responses:

| Exception Type | HTTP Status Code | Response Code | Description |
| :--- | :--- | :--- | :--- |
| `ConcurrencyConflictError` | `409 Conflict` | `CONCURRENCY_CONFLICT` | Shift handover version mismatch during write. |
| `ApprovalStaleError` | `409 Conflict` | `APPROVAL_STALE` | Handover state changed while approval was pending. |
| `SeparationOfDutiesViolationError`| `403 Forbidden` | `APPROVAL_FORBIDDEN` | Requester attempted self-approval. |
| `UnauthorizedApproverError` | `403 Forbidden` | `APPROVAL_FORBIDDEN` | User role lacks authority for approval. |
| `ShiftHandoverNotFoundError`| `404 Not Found` | `SHIFT_HANDOVER_NOT_FOUND` | Handover ID does not exist. |
| `ApprovalNotFoundError` | `404 Not Found` | `APPROVAL_NOT_FOUND` | Approval request ID does not exist. |
| `ApprovalExpiredError` | `400 Bad Request`| `APPROVAL_INVALID` | Approval request passed TTL expiration. |
| `ApprovalReasonRequiredError` | `400 Bad Request`| `APPROVAL_INVALID` | Rejection/Return submitted without reason. |
| `RequestValidationError` | `422 Unprocessable`| `VALIDATION_ERROR` | Malformed JSON schema or missing required field. |

---

## 6. Gateway Middleware & Security Hardening

- **`GatewayCorrelationMiddleware`**: Ensures every request is stamped with `X-Request-ID` and `X-Session-ID` headers.
- **`SecurityHeadersMiddleware`**: Injects production security headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- **Rate Limiting**: Sliding window rate limiting configured to 60 requests per minute per IP.

---

## 7. Verification & Testing

- **Test Suite**: [`tests/test_production_api.py`](file:///d:/Chatboat/tests/test_production_api.py), [`tests/test_api_mesh.py`](file:///d:/Chatboat/tests/test_api_mesh.py)
- **Verified Baseline**: **49 / 49 tests PASSED**.

---

## 8. Related Documentation

- [01_SYSTEM_ARCHITECTURE.md](file:///d:/Chatboat/DOCS/01_SYSTEM_ARCHITECTURE.md) — Architectural overview.
- [04_AGENT_ORCHESTRATOR_ROUTER.md](file:///d:/Chatboat/DOCS/04_AGENT_ORCHESTRATOR_ROUTER.md) — Request routing logic.
- [12_SECURITY_OBSERVABILITY_CACHING.md](file:///d:/Chatboat/DOCS/12_SECURITY_OBSERVABILITY_CACHING.md) — Security and token management.
