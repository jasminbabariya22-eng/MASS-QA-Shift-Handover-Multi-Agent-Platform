import os
import json
import uuid
import time
import requests
import streamlit as st
import logfire
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=env_path)

# Initialize Logfire
try:
    token = os.getenv("LOGFIRE_TOKEN")
    if token:
        logfire.configure(token=token)
        LOGFIRE_STATUS = "Connected & Tracing"
    else:
        LOGFIRE_STATUS = "Standby (No Token)"
except Exception as e:
    LOGFIRE_STATUS = f"Standby ({e})"

# Page Configuration
st.set_page_config(
    page_title="MASS QA & Shift Handover Intelligence Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

AI_AVATAR = "⚡"
USER_AVATAR = "👤"

# Backend configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Session State Initialization
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "auth_token" not in st.session_state:
    st.session_state.auth_token = ""

if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = "op_salem_01"
if "logged_in_role" not in st.session_state:
    st.session_state.logged_in_role = "CONSOLE_OPERATOR"

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚡ MASS QA OS")
    st.caption("Production Multi-Agent Platform v3.2")
    st.markdown("---")

    # Service Status
    st.subheader("System Status")
    try:
        health_resp = requests.get(f"{BACKEND_URL}/ready", timeout=2)
        if health_resp.status_code == 200:
            data = health_resp.json()
            st.success("🟢 API: Online (Ready)")
            deps = data.get("dependencies", {})
            st.caption(f"• PostgreSQL 18: {deps.get('postgresql', 'connected')}")
            st.caption(f"• Qdrant: {deps.get('qdrant', 'ok')} (2,079 vectors)")
            st.caption(f"• Cache: {deps.get('cache', 'active')}")
            st.caption(f"• LLM Gateway: {deps.get('llm_gateway', 'active')}")
        else:
            st.warning("🟡 API: Degraded")
    except Exception:
        st.error("🔴 API: Offline")

    st.markdown("---")

    # Session & Operator Login
    st.subheader("Operator Login & Role")

    ROLE_OPTIONS = [
        "CONSOLE_OPERATOR",
        "SHIFT_SUPERVISOR",
        "FIELD_OPERATOR",
        "INCOMING_OPERATOR",
        "OPERATIONS_ENGINEER",
        "HSE_REPRESENTATIVE",
        "ADMIN"
    ]

    selected_user = st.text_input("User / Operator ID", value=st.session_state.logged_in_user)
    selected_role = st.selectbox("Operational Role", options=ROLE_OPTIONS, index=ROLE_OPTIONS.index(st.session_state.logged_in_role) if st.session_state.logged_in_role in ROLE_OPTIONS else 0)

    if st.button("🔑 Login / Switch Role", use_container_width=True, type="primary"):
        try:
            tok_resp = requests.post(
                f"{BACKEND_URL}/auth/token",
                json={
                    "user_id": selected_user,
                    "username": selected_user,
                    "role": selected_role
                },
                timeout=4
            )
            if tok_resp.status_code == 200:
                tok_data = tok_resp.json()
                st.session_state.auth_token = tok_data.get("access_token", "")
                st.session_state.logged_in_user = selected_user
                st.session_state.logged_in_role = selected_role
                st.success(f"Logged in as `{selected_user}` (`{selected_role}`)")
                st.rerun()
            else:
                st.error("Failed to generate authentication token.")
        except Exception as ex:
            st.error(f"Login error: {ex}")

    if st.session_state.auth_token:
        st.caption(f"👤 Active: **{st.session_state.logged_in_user}** (`{st.session_state.logged_in_role}`)")

    with st.expander("⚙️ Token & Session Details", expanded=False):
        token_input = st.text_input("Bearer JWT Token", value=st.session_state.auth_token, type="password")
        if token_input != st.session_state.auth_token:
            st.session_state.auth_token = token_input
        st.caption(f"Session ID: `{st.session_state.session_id[:13]}...`")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("New Chat", use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.rerun()

    with col_btn2:
        if st.button("Clear Memory", use_container_width=True, type="secondary"):
            try:
                requests.delete(f"{BACKEND_URL}/sessions/{st.session_state.session_id}", timeout=3)
            except Exception:
                pass
            st.session_state.messages = []
            st.rerun()

    st.markdown("---")
    st.subheader("🤖 Multi-Agent Governance")
    with st.expander("Active Agents & Gates", expanded=False):
        st.markdown("**1. QA Technical Agent** (`qa_technical_agent`)")
        st.caption("• SOPs, P&IDs, Equipment Manuals, Frozen Qdrant 3072d")
        st.markdown("**2. Shift Handover Agent** (`shift_handover_agent`)")
        st.caption("• Turnover FSM, PostgreSQL Persistence, LOTO, Audit")
        st.markdown("**3. Loop Engineering Agent** (`loop_engineering_agent`)")
        st.caption("• ISA-5.1 Tag & Signal Path Wiring Validation")
        st.markdown("**4. AI Harness & HITL Gate** (`ai_harness`)")
        st.caption("• Safety Interlock, Role Authorization, Expiration")


# --- MAIN INTERFACE TABS ---
tab_chat, tab_approvals, tab_audit = st.tabs([
    "💬 Operations & QA Chat",
    "🛡️ HITL Approval Governance Center",
    "📜 System & Audit Telemetry"
])

# ============================================================
# TAB 1: OPERATIONS & QA CHAT
# ============================================================
with tab_chat:
    st.title("⚡ MASS QA & Shift Handover Intelligence Assistant")
    st.markdown("Query refinery operating procedures, manage role-governed shift handovers, or execute multi-agent workflows.")

    # Quick Starter Prompts
    with st.expander("💡 Live Demonstration Prompts", expanded=False):
        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1:
            st.caption("📋 **Shift Handover**")
            st.code("Create a day shift handover for Unit CDU-101", language="text")
            st.code("Add abnormal vibration observed on compressor C-101 to draft", language="text")
        with col_q2:
            st.caption("🤖 **A2A Multi-Agent Query**")
            st.code("Record abnormal vibration on C-101 in current handover and show the startup procedure", language="text")
        with col_q3:
            st.caption("📚 **Technical QA / SOP**")
            st.code("What is the startup procedure for crude charge pump P-101?", language="text")
            st.code("Shut down pump P-101 immediately (Safety Refusal Test)", language="text")

    # Render Conversation History
    for msg in st.session_state.messages:
        avatar = AI_AVATAR if msg["role"] == "assistant" else USER_AVATAR
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            
            # A2A Collaboration Trace Rendering
            msg_meta = msg.get("metadata", {}) or {}
            a2a_trace = msg_meta.get("a2a_trace", [])
            if a2a_trace:
                with st.expander("🤖 Agent-to-Agent (A2A) Collaboration Protocol Trace", expanded=False):
                    st.info("⚡ Coordinated multi-agent workflow executed across specialized operational agents:")
                    for step in a2a_trace:
                        st.markdown(
                            f"**Step {step.get('step', 1)}**: `{step.get('source')}` ➔ `{step.get('target')}`  \n"
                            f"• **Task**: `{step.get('task')}` — *{step.get('description')}* `[{step.get('status', 'COMPLETED')}]`"
                        )

            citations = msg.get("citations", [])
            if citations:
                with st.expander(f"📚 Verified Sources ({len(citations)} references)", expanded=False):
                    for cit in citations:
                        stype = cit.get("source_type", "DOCUMENT")
                        if stype == "SHIFT_DATABASE":
                            st.markdown(f"**🗄️ [PostgreSQL Database] {cit.get('document_name', 'shift_handovers')}**")
                            st.caption(f"• Record ID: `{cit.get('record_id')}` | Unit: `{cit.get('unit_id')}` | State: `{cit.get('state')}`")
                        else:
                            doc = cit.get("document_name", "Unknown Document")
                            page = cit.get("page_number")
                            slide = cit.get("slide_number")
                            loc = f"Page {page}" if page else (f"Slide {slide}" if slide else "")
                            ctype = (cit.get("content_type") or "text").upper()
                            preview = cit.get("snippet") or cit.get("preview_text", "")

                            icon = "📊" if ctype == "TABLE" else ("🖼️" if ctype in ["IMAGE", "DIAGRAM", "CHART"] else "📄")
                            st.markdown(f"**[{cit.get('source_number', '#')}] {icon} {doc}** — `{loc}` `[{ctype}]`")
                            if preview:
                                st.caption(f"> {preview[:180]}...")

    # User Input
    if prompt := st.chat_input("Enter technical query, shift command, or A2A task..."):
        # Auto-login if token empty
        if not st.session_state.auth_token:
            try:
                tok_res = requests.post(f"{BACKEND_URL}/auth/token", json={"user_id": st.session_state.logged_in_user, "username": st.session_state.logged_in_user, "role": st.session_state.logged_in_role}, timeout=3)
                if tok_res.status_code == 200:
                    st.session_state.auth_token = tok_res.json().get("access_token", "")
            except Exception:
                pass

        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar=AI_AVATAR):
            answer_placeholder = st.empty()
            a2a_placeholder = st.empty()
            citations_placeholder = st.empty()

            headers = {"Content-Type": "application/json"}
            if st.session_state.auth_token:
                headers["Authorization"] = f"Bearer {st.session_state.auth_token}"

            payload = {
                "question": prompt,
                "session_id": st.session_state.session_id,
                "stream": True,
                "top_k": 5
            }

            full_answer = ""
            received_citations = []
            metadata = {}

            try:
                response = requests.post(
                    f"{BACKEND_URL}/query/stream",
                    json=payload,
                    headers=headers,
                    stream=True,
                    timeout=60
                )

                if response.status_code == 401:
                    st.error("🔒 Authentication required. Please log in using the sidebar role selector.")
                    st.stop()
                elif response.status_code != 200:
                    st.error(f"Error ({response.status_code}): {response.text}")
                    st.stop()

                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        raw_data = line[6:].strip()
                        if not raw_data:
                            continue
                        try:
                            event = json.loads(raw_data)
                            event_type = event.get("type")

                            if event_type == "token":
                                full_answer += event.get("content", "")
                                answer_placeholder.markdown(full_answer + "▌")
                            elif event_type == "citations":
                                received_citations = event.get("citations", [])
                            elif event_type == "done":
                                metadata = event.get("metadata", {})
                        except Exception:
                            pass

                answer_placeholder.markdown(full_answer if full_answer else "*(No response generated)*")

                # Render A2A Trace
                a2a_trace = metadata.get("a2a_trace", [])
                if a2a_trace:
                    with a2a_placeholder.expander("🤖 Agent-to-Agent (A2A) Collaboration Protocol Trace", expanded=True):
                        st.info("⚡ Coordinated multi-agent workflow executed across specialized operational agents:")
                        for step in a2a_trace:
                            st.markdown(
                                f"**Step {step.get('step', 1)}**: `{step.get('source')}` ➔ `{step.get('target')}`  \n"
                                f"• **Task**: `{step.get('task')}` — *{step.get('description')}* `[{step.get('status', 'COMPLETED')}]`"
                            )

                # Render Citations
                if received_citations:
                    with citations_placeholder.expander(f"📚 Verified Sources ({len(received_citations)} references)", expanded=False):
                        for cit in received_citations:
                            stype = cit.get("source_type", "DOCUMENT")
                            if stype == "SHIFT_DATABASE":
                                st.markdown(f"**🗄️ [PostgreSQL Database] {cit.get('document_name', 'shift_handovers')}**")
                                st.caption(f"• Record ID: `{cit.get('record_id')}` | Unit: `{cit.get('unit_id')}` | State: `{cit.get('state')}`")
                            else:
                                doc = cit.get("document_name", "Unknown Document")
                                page = cit.get("page_number")
                                loc = f"Page {page}" if page else ""
                                ctype = (cit.get("content_type") or "text").upper()
                                preview = cit.get("snippet") or cit.get("preview_text", "")
                                st.markdown(f"**📄 {doc}** — `{loc}` `[{ctype}]`")
                                if preview:
                                    st.caption(f"> {preview[:180]}...")

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_answer,
                    "citations": received_citations,
                    "metadata": metadata
                })

            except requests.exceptions.ConnectionError:
                st.error("❌ Connection failed: Backend service is currently unreachable.")
            except Exception as e:
                st.error(f"❌ An error occurred: {str(e)}")


# ============================================================
# TAB 2: HITL APPROVAL GOVERNANCE CENTER
# ============================================================
with tab_approvals:
    st.header("🛡️ Human-In-The-Loop (HITL) Governance Center")
    st.markdown("Review, authorize, reject, or return high-risk operational requests governed by the deterministic state machine.")

    headers = {"Authorization": f"Bearer {st.session_state.auth_token}"} if st.session_state.auth_token else {}
    
    col_ref, col_filter = st.columns([1, 3])
    with col_ref:
        if st.button("🔄 Refresh Approvals Queue", use_container_width=True):
            st.rerun()

    try:
        appr_resp = requests.get(f"{BACKEND_URL}/approvals", headers=headers, timeout=4)
        if appr_resp.status_code == 200:
            appr_data = appr_resp.json()
            approvals = appr_data.get("approvals", [])
            
            if not approvals:
                st.info("ℹ️ No pending HITL approval requests at this time.")
            else:
                for req in approvals:
                    status_badge = "🟡 PENDING" if req["status"] == "PENDING" else ("🟢 APPROVED" if req["status"] == "APPROVED" else ("🔵 CONSUMED" if req["status"] == "CONSUMED" else f"🔴 {req['status']}"))
                    
                    with st.expander(f"**{req['id']}** — Action: `{req['action']}` | State: `{status_badge}` | Risk: `{req['risk_level']}`", expanded=(req["status"] == "PENDING")):
                        col_d1, col_d2 = st.columns(2)
                        with col_d1:
                            st.markdown(f"• **Requested By**: `{req['requested_by']}` (`{req['requested_role']}`)")
                            st.markdown(f"• **Required Role**: `{req['required_role']}`")
                            st.markdown(f"• **Handover Target**: `{req.get('handover_id') or 'N/A'}`")
                        with col_d2:
                            st.markdown(f"• **Created At**: `{req['created_at']}`")
                            st.markdown(f"• **Expires At**: `{req['expires_at']}`")
                            st.markdown(f"• **Reason**: *{req.get('reason') or 'None specified'}*")

                        if req["status"] == "PENDING":
                            st.markdown("---")
                            st.markdown("### Decision Panel")
                            reason_input = st.text_input(f"Decision / Rework Reason for {req['id']}", key=f"reason_{req['id']}")
                            
                            col_a1, col_a2, col_a3 = st.columns(3)
                            with col_a1:
                                if st.button(f"✅ Approve ({req['id']})", key=f"btn_app_{req['id']}", type="primary", use_container_width=True):
                                    dec_res = requests.post(f"{BACKEND_URL}/approvals/{req['id']}/approve", json={"decision": "APPROVE", "reason": reason_input}, headers=headers)
                                    if dec_res.status_code == 200:
                                        st.success(f"Approval {req['id']} APPROVED and executed!")
                                        st.rerun()
                                    else:
                                        st.error(f"Error: {dec_res.text}")
                            with col_a2:
                                if st.button(f"❌ Reject ({req['id']})", key=f"btn_rej_{req['id']}", use_container_width=True):
                                    if not reason_input.strip():
                                        st.warning("⚠️ Operational reason is mandatory when rejecting.")
                                    else:
                                        dec_res = requests.post(f"{BACKEND_URL}/approvals/{req['id']}/reject", json={"decision": "REJECT", "reason": reason_input}, headers=headers)
                                        if dec_res.status_code == 200:
                                            st.success(f"Approval {req['id']} REJECTED.")
                                            st.rerun()
                                        else:
                                            st.error(f"Error: {dec_res.text}")
                            with col_a3:
                                if st.button(f"↩️ Return for Rework ({req['id']})", key=f"btn_ret_{req['id']}", use_container_width=True):
                                    if not reason_input.strip():
                                        st.warning("⚠️ Operational reason is mandatory when returning.")
                                    else:
                                        dec_res = requests.post(f"{BACKEND_URL}/approvals/{req['id']}/return", json={"decision": "RETURN", "reason": reason_input}, headers=headers)
                                        if dec_res.status_code == 200:
                                            st.success(f"Approval {req['id']} RETURNED.")
                                            st.rerun()
                                        else:
                                            st.error(f"Error: {dec_res.text}")
        else:
            st.error(f"Failed to fetch approvals: {appr_resp.text}")
    except Exception as ex:
        st.error(f"Approvals service error: {ex}")


# ============================================================
# TAB 3: AUDIT & TELEMETRY
# ============================================================
with tab_audit:
    st.header("📜 System & Audit Telemetry")
    st.markdown("Immutable PostgreSQL audit trails, Logfire distributed tracing, and execution metrics.")

    st.markdown("""
    ### Verified System Architecture
    - **PostgreSQL 18**: `shift_handovers`, `shift_safety_critical_items`, `shift_handover_audits`, `hitl_approval_requests`
    - **Qdrant Vector DB**: Collection `mass_qa_multimodal` (2,079 points, 3072 dims, Cosine similarity, FROZEN)
    - **FastAPI Gateway**: JWT RBAC authentication, rate limiting, and Server-Sent Events (SSE)
    - **AI Harness**: Execution budget limits, loop detection, secret masking, and safety interlocks
    """)
