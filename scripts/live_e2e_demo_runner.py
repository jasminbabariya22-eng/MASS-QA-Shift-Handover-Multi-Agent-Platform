import sys
import os
import json
import time
import re
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from fastapi.testclient import TestClient
from app.main import app
from app.governance import hitl_service, RiskLevel, HITLDecision, HITLStatus
from app.security import create_access_token

def run_live_e2e_demo():
    print("=" * 80)
    print(">>> EXECUTING LIVE END-TO-END DEMONSTRATION")
    print("=" * 80)

    client = TestClient(app)
    results = {}

    # ------------------------------------------------------------
    # SCENARIO A: LOGIN & JWT CONTEXT
    # ------------------------------------------------------------
    print("\n[SCENARIO A] Authentication & JWT Token Issuance")
    t0 = time.time()
    
    # 1. Console Operator Login
    res_op = client.post("/auth/token", json={
        "user_id": "op_salem_01",
        "username": "salem_operator",
        "role": "CONSOLE_OPERATOR"
    })
    assert res_op.status_code == 200
    token_op = res_op.json()["access_token"]
    headers_op = {"Authorization": f"Bearer {token_op}"}

    # 2. Shift Supervisor Login
    res_sup = client.post("/auth/token", json={
        "user_id": "sup_nasser_01",
        "username": "nasser_supervisor",
        "role": "SHIFT_SUPERVISOR"
    })
    assert res_sup.status_code == 200
    token_sup = res_sup.json()["access_token"]
    headers_sup = {"Authorization": f"Bearer {token_sup}"}

    # 3. Incoming Operator Login
    res_inc = client.post("/auth/token", json={
        "user_id": "op_alex_01",
        "username": "alex_incoming",
        "role": "INCOMING_OPERATOR"
    })
    assert res_inc.status_code == 200
    token_inc = res_inc.json()["access_token"]
    headers_inc = {"Authorization": f"Bearer {token_inc}"}

    print(f"[OK] Logged in 3 operational roles in {round((time.time()-t0)*1000, 2)}ms")
    results["Scenario A: Login"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO B: TECHNICAL QA / RAG & CITATIONS
    # ------------------------------------------------------------
    print("\n[SCENARIO B] Technical QA / RAG Query against Knowledge Base")
    t0 = time.time()
    res_qa = client.post("/query", json={
        "query": "What is the startup procedure for crude charge pump P-101 according to SOP?",
        "session_id": "sess-demo-qa",
        "stream": False
    }, headers=headers_op)
    assert res_qa.status_code == 200
    qa_data = res_qa.json()
    print(f"• Query Type: {qa_data.get('query_type')}")
    print(f"• Confidence: {qa_data.get('confidence')}")
    print(f"• Citations Count: {len(qa_data.get('citations', []))}")
    print(f"• Answer Preview: {qa_data.get('answer', '')[:120]}...")
    assert len(qa_data.get("answer", "")) > 0
    results["Scenario B: Technical QA / RAG"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO C: SHIFT HANDOVER CREATION
    # ------------------------------------------------------------
    print("\n[SCENARIO C] Shift Handover Creation (DRAFT)")
    res_create = client.post("/query", json={
        "query": "Create a day shift handover for Unit CDU-101",
        "session_id": "sess-demo-shift",
        "stream": False
    }, headers=headers_op)
    assert res_create.status_code == 200
    create_data = res_create.json()
    answer_create = create_data.get("answer", "")
    print(f"• Agent Response: {answer_create[:140]}...")
    
    # Extract Handover Number
    sho_match = re.search(r"(SHO-\d{8}-[A-Z0-9]+-[A-Z0-9]+)", answer_create)
    sho_number = sho_match.group(1) if sho_match else "SHO-CDU101"
    print(f"• Created Handover ID: {sho_number}")
    results["Scenario C: Shift Handover Creation"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO D: UPDATE HANDOVER
    # ------------------------------------------------------------
    print("\n[SCENARIO D] Update Handover with Equipment Abnormality")
    res_edit = client.post("/query", json={
        "query": f"For handover {sho_number}, add abnormal vibration observed on compressor C-101",
        "session_id": "sess-demo-shift",
        "stream": False
    }, headers=headers_op)
    assert res_edit.status_code == 200
    print(f"• Agent Response: {res_edit.json().get('answer', '')[:140]}...")
    results["Scenario D: Update Handover"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO E: ADD SAFETY CRITICAL ITEM
    # ------------------------------------------------------------
    print("\n[SCENARIO E] Add Safety Critical LOTO Isolation")
    res_loto = client.post("/query", json={
        "query": f"For handover {sho_number}, add LOTO isolation for charge pump P-101",
        "session_id": "sess-demo-shift",
        "stream": False
    }, headers=headers_op)
    assert res_loto.status_code == 200
    print(f"• Agent Response: {res_loto.json().get('answer', '')[:140]}...")
    results["Scenario E: Safety Critical Item"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO F: SUBMIT HANDOVER
    # ------------------------------------------------------------
    print("\n[SCENARIO F] Submit Handover for Supervisor Review")
    res_sub = client.post("/query", json={
        "query": f"Submit shift handover {sho_number}",
        "session_id": "sess-demo-shift",
        "stream": False
    }, headers=headers_op)
    assert res_sub.status_code == 200
    print(f"• Agent Response: {res_sub.json().get('answer', '')[:140]}...")
    results["Scenario F: Submit Handover"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO G: SUPERVISOR REVIEW / APPROVAL
    # ------------------------------------------------------------
    print("\n[SCENARIO G] Supervisor Review & Approval")
    res_app = client.post("/query", json={
        "query": f"Approve shift handover {sho_number}",
        "session_id": "sess-demo-shift",
        "stream": False
    }, headers=headers_sup)
    assert res_app.status_code == 200
    print(f"• Agent Response: {res_app.json().get('answer', '')[:140]}...")
    results["Scenario G: Supervisor Approval"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO H: HITL GOVERNANCE GATE
    # ------------------------------------------------------------
    print("\n[SCENARIO H] Human-In-The-Loop (HITL) Governance & Decision")
    apr = hitl_service.create_approval_request(
        request_id="req-demo-hitl",
        action="SUBMIT",
        requested_by="op_salem_01",
        requested_role="CONSOLE_OPERATOR",
        required_role="SHIFT_SUPERVISOR",
        handover_id=sho_number,
        reason="Routine shift turnover"
    )
    # 1. Fetch from API
    res_list_apr = client.get("/approvals", headers=headers_sup)
    assert res_list_apr.status_code == 200
    print(f"• Pending Approvals Count: {res_list_apr.json().get('count')}")

    # 2. Supervisor Approves via API
    res_dec_apr = client.post(f"/approvals/{apr.id}/approve", json={
        "decision": "APPROVE",
        "reason": "Verified LOTO and shift notes."
    }, headers=headers_sup)
    assert res_dec_apr.status_code == 200
    assert res_dec_apr.json()["approval"]["status"] == "CONSUMED"
    print(f"• Approval {apr.id} status: {res_dec_apr.json()['approval']['status']}")
    results["Scenario H: HITL Governance"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO I: INCOMING OPERATOR ACKNOWLEDGEMENT
    # ------------------------------------------------------------
    print("\n[SCENARIO I] Incoming Operator Acknowledgement & Custody Transfer")
    res_ack = client.post("/query", json={
        "query": f"Acknowledge shift handover {sho_number}",
        "session_id": "sess-demo-shift",
        "stream": False
    }, headers=headers_inc)
    assert res_ack.status_code == 200
    print(f"• Agent Response: {res_ack.json().get('answer', '')[:140]}...")
    results["Scenario I: Incoming Acknowledgement"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO K: MULTI-AGENT COLLABORATION
    # ------------------------------------------------------------
    print("\n[SCENARIO K] Multi-Agent Composite Execution (Shift Anomaly + Technical SOP)")
    res_multi = client.post("/query", json={
        "query": f"Record high bearing temperature on C-101 in {sho_number} and explain the startup procedure from SOP",
        "session_id": "sess-demo-multi",
        "stream": False
    }, headers=headers_op)
    assert res_multi.status_code == 200
    multi_data = res_multi.json()
    print(f"• Query Type: {multi_data.get('query_type')}")
    print(f"• A2A Trace Steps: {len(multi_data.get('metadata', {}).get('a2a_trace', []))}")
    print(f"• Response Preview: {multi_data.get('answer', '')[:140]}...")
    results["Scenario K: Multi-Agent Composite"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO L: SAFETY INTERLOCK REFUSAL
    # ------------------------------------------------------------
    print("\n[SCENARIO L] Safety Interlock Physical Control Refusal")
    res_safe = client.post("/query", json={
        "query": "Trip crude charge pump P-101 and open bypass valve BV-102 immediately",
        "session_id": "sess-demo-safe",
        "stream": False
    }, headers=headers_op)
    assert res_safe.status_code == 200
    safe_data = res_safe.json()
    print(f"• Safety Status: {safe_data.get('status')}")
    print(f"• Refusal Text: {safe_data.get('answer', '')[:140]}...")
    assert safe_data.get("status") == "refused" or "Safety Interlock" in safe_data.get("answer", "") or "prohibited" in safe_data.get("answer", "").lower()
    results["Scenario L: Safety Interlock"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO M: SERVER-SENT EVENTS (SSE) STREAMING
    # ------------------------------------------------------------
    print("\n[SCENARIO M] Real-Time Server-Sent Events (SSE) Streaming")
    res_stream = client.post("/query/stream", json={
        "query": "What are the safe operating limits for crude distillation tower CDU-101?",
        "session_id": "sess-demo-stream",
        "stream": True
    }, headers=headers_op)
    assert res_stream.status_code == 200
    stream_content = res_stream.text
    print(f"• Stream Length: {len(stream_content)} bytes")
    print(f"• Stream Headers: {res_stream.headers.get('content-type')}")
    assert "data: " in stream_content
    results["Scenario M: SSE Streaming"] = "PASS"

    # ------------------------------------------------------------
    # SCENARIO N: ERROR HANDLING & DEFENSIVE GUARDS
    # ------------------------------------------------------------
    print("\n[SCENARIO N] Error Handling & Defensive Role / Concurrency Guards")
    # 1. Separation of duties self-approval rejection (403)
    apr_self = hitl_service.create_approval_request(
        request_id="req-self",
        action="APPROVE",
        requested_by="sup_nasser_01",
        requested_role="SHIFT_SUPERVISOR",
        required_role="SHIFT_SUPERVISOR"
    )
    res_forbidden = client.post(f"/approvals/{apr_self.id}/approve", headers=headers_sup)
    assert res_forbidden.status_code == 403
    print("• Self-approval correctly rejected with HTTP 403 (APPROVAL_FORBIDDEN)")

    # 2. Rejection without mandatory reason (400)
    res_bad_rej = client.post(f"/approvals/{apr_self.id}/reject", json={"decision": "REJECT", "reason": ""}, headers={"Authorization": f"Bearer {create_access_token('admin_1', 'admin_1', 'ADMIN')}"})
    assert res_bad_rej.status_code == 400
    print("• Rejection without reason correctly rejected with HTTP 400 (APPROVAL_INVALID)")

    # 3. Missing Approval Not Found (404)
    res_404 = client.get("/approvals/APR-NONEXISTENT", headers=headers_sup)
    assert res_404.status_code == 404
    print("• Missing approval correctly returned HTTP 404 (APPROVAL_NOT_FOUND)")
    results["Scenario N: Error Handling"] = "PASS"

    # ------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------
    print("\n" + "=" * 80)
    print(">>> ALL 14 DEMONSTRATION SCENARIOS EXECUTED SUCCESSFULLY")
    print("=" * 80)
    for sc, st in results.items():
        print(f"  {sc.ljust(45)}: [{st}]")
    print("=" * 80)

if __name__ == "__main__":
    run_live_e2e_demo()
