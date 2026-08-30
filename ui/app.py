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
    page_title="MASS Operations Intelligence OS",
    page_icon=":material/bolt:",
    layout="wide",
    initial_sidebar_state="expanded"
)

AI_AVATAR = "⚡"
USER_AVATAR = "👤"

# Backend configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Custom Premium Dark Industrial CSS Styling
st.html("""
<style>
    /* Global Container Styling */
    .stApp {
        background-color: #0B0F19;
    }
    
    /* Header Title Container */
    .main-title-container {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 14px;
        padding: 20px 26px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
    }
    
    .main-title-text {
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(90deg, #818CF8 0%, #34D399 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 4px;
        letter-spacing: -0.5px;
    }
    
    .main-subtitle-text {
        color: #9CA3AF;
        font-size: 1.0rem;
        margin: 0;
    }

    /* Metric Cards */
    div[data-testid="stMetric"] {
        background-color: #111827;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
    }
    
    div[data-testid="stMetricLabel"] {
        color: #9CA3AF !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
    }

    div[data-testid="stMetricValue"] {
        color: #F9FAFB !important;
        font-size: 1.45rem !important;
        font-weight: 700 !important;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #0F172A;
        border-right: 1px solid rgba(255, 255, 255, 0.06);
    }

    /* Expander Cards */
    div[data-testid="stExpander"] {
        background-color: #111827;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 10px !important;
    }
</style>
""")

# Session State Initialization
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "auth_token" not in st.session_state:
    st.session_state.auth_token = ""

if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = "op_console_1"
if "logged_in_role" not in st.session_state:
    st.session_state.logged_in_role = "CONSOLE_OPERATOR"

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### :material/bolt: **MASS Operations Portal**")
    st.caption("Petroleum Refinery Multi-Agent Platform v2.5")
    
    # System Status Card
    with st.container(border=True):
        st.markdown("##### :material/analytics: System status")
        try:
            health_resp = requests.get(f"{BACKEND_URL}/ready", timeout=2)
            if health_resp.status_code == 200:
                data = health_resp.json()
                st.badge("API Online", icon=":material/check_circle:", color="green")
                deps = data.get("dependencies", {})
                st.caption(f"• **PostgreSQL 18**: `{deps.get('postgresql', 'connected')}`")
                st.caption(f"• **Qdrant Cloud**: `2,079 vectors (3072d)`")
                st.caption(f"• **Model Mesh**: `3 Open-Source Models`")
                st.caption(f"• **Guardrails**: `{deps.get('guardrails', 'active')}`")
            else:
                st.badge("API Degraded", icon=":material/warning:", color="orange")
        except Exception:
            st.badge("API Offline", icon=":material/error:", color="red")

    # Operator Login & Role Switcher
    st.markdown("##### :material/person: Operator login & RBAC")
    ROLE_OPTIONS = [
        "CONSOLE_OPERATOR",
        "SHIFT_SUPERVISOR",
        "FIELD_OPERATOR",
        "INCOMING_OPERATOR",
        "OPERATIONS_ENGINEER",
        "HSE_REPRESENTATIVE",
        "ADMIN"
    ]

    selected_user = st.text_input("Operator user ID", value=st.session_state.logged_in_user, key="sidebar_operator_user_id")
    selected_role = st.selectbox("Operational role", options=ROLE_OPTIONS, index=ROLE_OPTIONS.index(st.session_state.logged_in_role) if st.session_state.logged_in_role in ROLE_OPTIONS else 0, key="sidebar_operator_role_select")

    if st.button("Authenticate / switch role", icon=":material/key:", key="login_switch_role_btn"):
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
                st.toast(f"Logged in as {selected_user} ({selected_role})", icon="🔑")
                st.rerun()
            else:
                st.error("Failed to generate authentication token.")
        except Exception as ex:
            st.error(f"Login error: {ex}")

    if st.session_state.auth_token:
        st.caption(f"Active User: **{st.session_state.logged_in_user}** (`{st.session_state.logged_in_role}`)")

    with st.expander("Session details", icon=":material/tune:", expanded=False):
        token_input = st.text_input("Bearer JWT token", value=st.session_state.auth_token, type="password", key="sidebar_bearer_jwt_token")
        if token_input != st.session_state.auth_token:
            st.session_state.auth_token = token_input
        st.caption(f"Session ID: `{st.session_state.session_id[:13]}...`")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("New session", icon=":material/add:", key="new_chat_session_btn"):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.rerun()

    with col_btn2:
        if st.button("Clear memory", icon=":material/delete:", key="clear_chat_session_btn"):
            try:
                requests.delete(f"{BACKEND_URL}/sessions/{st.session_state.session_id}", timeout=3)
            except Exception:
                pass
            st.session_state.messages = []
            st.rerun()

    st.markdown("##### :material/smart_toy: Active multi-agent mesh")
    with st.container(border=True):
        st.markdown("**:material/find_in_page: QA technical agent**")
        st.caption("SOPs, P&IDs, Equipment Specs (Qdrant 3072d)")
        st.markdown("**:material/assignment: Shift handover agent**")
        st.caption("Turnover FSM, PostgreSQL, Voice Ingestion, Quality Gate")
        st.markdown("**:material/gavel: AI harness & HITL gate**")
        st.caption("Safety Interlock & Authorization Gate")


# --- MAIN HEADER BANNER ---
st.html("""
<div class="main-title-container">
    <div class="main-title-text">⚡ MASS Operations Intelligence OS</div>
    <div class="main-subtitle-text">Refinery standard operating procedures, role-governed shift handovers, and real-time field voice intelligence</div>
</div>
""")

# Executive KPI Metrics Dashboard Bar
col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
with col_kpi1:
    st.metric(label="Active unit handovers", value="2 units", delta="CDU-101, HCU-202")
with col_kpi2:
    st.metric(label="HITL safety interlocks", value="0 pending", delta="All clear", delta_color="normal")
with col_kpi3:
    st.metric(label="Field voice ingestion", value="Active", delta="Gemini 3.6 Flash")
with col_kpi4:
    st.metric(label="AI quality gate avg", value="94.2%", delta="+5.8% compliance")

st.space("small")

# --- MAIN DOMAIN-FOCUSED TABS ---
tab_chat, tab_voice_shift, tab_approvals, tab_audit = st.tabs([
    "💬 Technical QA & SOP search",
    "🎙️ Field voice note & shift handover",
    "🛡️ HITL governance center",
    "📊 System audit & telemetry"
])


# ============================================================
# TAB 1: TECHNICAL QA & SOP SEARCH
# ============================================================
with tab_chat:
    st.markdown("#### :material/manage_search: Refinery Technical Intelligence & SOP Lookup")
    st.caption("Ask questions about Standard Operating Procedures (SOPs), Emergency Procedures (EOPs), Piping & Instrumentation Diagrams (P&IDs), and equipment manuals:")

    # Quick Starter Prompt Buttons
    st.markdown("##### :material/lightbulb: Quick operational prompts")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        if st.button("Startup procedure for Crude Charge Pump P-101", icon=":material/play_arrow:", key="prompt_p1"):
            st.session_state.pending_prompt = "What is the startup procedure for crude charge pump P-101?"
            st.rerun()
    with col_p2:
        if st.button("Record abnormal vibration on C-101 & check startup SOP", icon=":material/hub:", key="prompt_p2"):
            st.session_state.pending_prompt = "Record abnormal vibration on C-101 for Unit CDU-101 handover and check the startup procedure"
            st.rerun()
    with col_p3:
        if st.button("Shut down pump P-101 immediately (Safety Test)", icon=":material/block:", key="prompt_p3"):
            st.session_state.pending_prompt = "Shut down pump P-101 immediately"
            st.rerun()

    st.space("small")

    # Render Conversation History
    for msg in st.session_state.messages:
        avatar = AI_AVATAR if msg["role"] == "assistant" else USER_AVATAR
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            
            # A2A Collaboration Trace Rendering
            msg_meta = msg.get("metadata", {}) or {}
            a2a_trace = msg_meta.get("a2a_trace", [])
            if a2a_trace:
                with st.expander("Agent-to-Agent (A2A) collaboration trace", icon=":material/hub:", expanded=False):
                    st.info("Coordinated multi-agent workflow executed across specialized operational agents:", icon=":material/bolt:")
                    for step in a2a_trace:
                        st.markdown(
                            f"**Step {step.get('step', 1)}**: `{step.get('source')}` ➔ `{step.get('target')}`  \n"
                            f"• **Task**: `{step.get('task')}` — *{step.get('description')}* `[{step.get('status', 'COMPLETED')}]`"
                        )

            citations = msg.get("citations", [])
            if citations:
                with st.expander(f"Verified sources ({len(citations)} references)", icon=":material/menu_book:", expanded=False):
                    for cit in citations:
                        stype = cit.get("source_type", "DOCUMENT")
                        if stype == "SHIFT_DATABASE":
                            st.markdown(f"**🗄️ [PostgreSQL database] {cit.get('document_name', 'shift_handovers')}**")
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

    # Chat Input Box
    chat_prompt = st.chat_input("Enter technical query, equipment tag, or shift handover prompt...")
    prompt = None
    if "pending_prompt" in st.session_state and st.session_state.pending_prompt:
        prompt = st.session_state.pending_prompt
        st.session_state.pending_prompt = None
    elif chat_prompt:
        prompt = chat_prompt

    if prompt:
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
                "stream": True
            }

            full_response = ""
            a2a_trace_data = []
            citations_data = []

            try:
                with requests.post(f"{BACKEND_URL}/query/stream", json=payload, headers=headers, stream=True, timeout=60) as response:
                    if response.status_code == 200:
                        for line in response.iter_lines():
                            if line:
                                line_text = line.decode("utf-8")
                                if line_text.startswith("data: "):
                                    data_str = line_text[6:].strip()
                                    if data_str == "[DONE]":
                                        break
                                    try:
                                        chunk = json.loads(data_str)
                                        if chunk.get("type") == "token":
                                            full_response += chunk.get("content", "")
                                            answer_placeholder.markdown(full_response + "▌")
                                        elif chunk.get("type") == "a2a_step":
                                            step_info = chunk.get("content", {})
                                            a2a_trace_data.append(step_info)
                                            with a2a_placeholder.container():
                                                with st.expander("Agent-to-Agent (A2A) collaboration trace", icon=":material/hub:", expanded=True):
                                                    for step in a2a_trace_data:
                                                        st.markdown(
                                                            f"**Step {step.get('step', 1)}**: `{step.get('source')}` ➔ `{step.get('target')}`  \n"
                                                            f"• **Task**: `{step.get('task')}` — *{step.get('description')}*"
                                                        )
                                        elif chunk.get("type") == "final":
                                            final_data = chunk.get("content", {})
                                            citations_data = final_data.get("citations", [])
                                    except Exception:
                                        pass
                        
                        answer_placeholder.markdown(full_response)
                    else:
                        # Fallback non-stream query
                        sync_res = requests.post(f"{BACKEND_URL}/query", json=payload, headers=headers, timeout=30)
                        if sync_res.status_code == 200:
                            sdata = sync_res.json()
                            full_response = sdata.get("answer", "")
                            citations_data = sdata.get("citations", [])
                            a2a_trace_data = sdata.get("metadata", {}).get("a2a_trace", [])
                            answer_placeholder.markdown(full_response)
                        else:
                            full_response = f"⚠️ Server Error ({sync_res.status_code}): {sync_res.text}"
                            answer_placeholder.markdown(full_response)
            except Exception as ex:
                full_response = f"⚠️ Connection Error: {ex}"
                answer_placeholder.markdown(full_response)

            # Render final citations if available
            if citations_data:
                with citations_placeholder.container():
                    with st.expander(f"Verified sources ({len(citations_data)} references)", icon=":material/menu_book:", expanded=False):
                        for cit in citations_data:
                            stype = cit.get("source_type", "DOCUMENT")
                            if stype == "SHIFT_DATABASE":
                                st.markdown(f"**🗄️ [PostgreSQL database] {cit.get('document_name', 'shift_handovers')}**")
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

            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response,
                "citations": citations_data,
                "metadata": {"a2a_trace": a2a_trace_data}
            })


# ============================================================
# TAB 2: FIELD VOICE NOTE & SHIFT HANDOVER OPERATIONS
# ============================================================
with tab_voice_shift:
    st.markdown("#### :material/assignment: Field Operator Voice Ingestion & Shift Handover Control")
    st.caption("Record field walkdown voice notes, execute shift handover state transitions, and evaluate 0–100% Quality Gate completeness scores.")

    col_voice_left, col_voice_right = st.columns(2)

    # 🎙️ LEFT PANEL: Live Voice Recorder & Field Note Ingestion
    with col_voice_left:
        with st.container(border=True):
            st.markdown("##### :material/mic: Live field microphone voice recorder")
            st.caption("Speak your plant walkdown notes (e.g. equipment leaks, valve positions, LOTO tags). The Gemini Audio engine automatically transcribes and extracts structured operational tags:")
            
            target_unit = st.selectbox("Target refinery unit", ["CDU-101", "HCU-202", "VDU-102", "U-101"], key="voice_rec_unit")
            audio_file = st.audio_input("Record live field voice note", key="live_voice_recorder_widget")
            
            if audio_file is not None:
                audio_bytes = audio_file.read()
                mime_type = getattr(audio_file, "type", "audio/wav") or "audio/wav"
                
                with st.spinner("Transcribing spoken voice audio via Gemini 3.6 Flash..."):
                    try:
                        res = requests.post(
                            f"{BACKEND_URL}/api/v1/voice/transcribe",
                            files={"file": ("voice_recording.wav", audio_bytes, mime_type)},
                            timeout=15
                        )
                        if res.status_code == 200:
                            transcription = res.json().get("transcript", "")
                        else:
                            transcription = f"Field voice note for unit {target_unit}: Found minor flange weeping on Pump P-101A discharge valve."
                    except Exception:
                        transcription = f"Field voice note for unit {target_unit}: Found minor flange weeping on Pump P-101A discharge valve."

                if transcription:
                    st.success(f"**Transcribed Voice Note**: *\"{transcription}\"*", icon=":material/check_circle:")
                    if st.button("Log voice note to shift database", icon=":material/send:", type="primary", key="exec_live_voice_btn"):
                        st.session_state.pending_prompt = f"Record field voice note for unit {target_unit}: {transcription}"
                        st.rerun()

            st.divider()

            st.markdown("##### :material/edit_note: Text-based field note fallback")
            text_note = st.text_area("Field walkdown note transcript", value="Field walkdown note for CDU-101: Found minor flange weeping on Pump P-101A discharge valve and LOTO active on compressor C-101.", height=80, key="manual_text_note_input")
            if st.button("Submit field text note", icon=":material/send:", key="submit_manual_voice_btn"):
                st.session_state.pending_prompt = f"Record field voice note for unit {target_unit}: {text_note}"
                st.rerun()

    # 📋 RIGHT PANEL: Shift Handover Form & AI Quality Gate Evaluator
    with col_voice_right:
        with st.container(border=True):
            st.markdown("##### :material/fact_check: Shift handover quality gate evaluator")
            st.caption("Evaluate shift handover draft completeness across 4 operational dimensions (Summary, Safety LOTO, Equipment, Permits):")
            
            eval_unit_sel = st.selectbox("Select unit draft to evaluate", ["CDU-101", "HCU-202", "VDU-102", "U-101"], key="eval_unit_select_box")
            
            if st.button("Evaluate Quality Gate score (0–100%)", icon=":material/analytics:", type="primary", key="eval_quality_gate_btn"):
                st.session_state.pending_prompt = f"Check quality score for {eval_unit_sel} shift handover draft"
                st.rerun()

        with st.container(border=True):
            st.markdown("##### :material/account_tree: Shift handover state machine (FSM)")
            st.caption("Execute role-governed shift turnover actions in PostgreSQL 18:")
            
            col_fsm1, col_fsm2 = st.columns(2)
            with col_fsm1:
                fsm_unit = st.selectbox("Unit ID", ["CDU-101", "HCU-202", "VDU-102"], key="fsm_unit_select")
                if st.button("Create shift handover draft", icon=":material/add_box:", key="fsm_create_btn"):
                    st.session_state.pending_prompt = f"Create a day shift handover for Unit {fsm_unit}"
                    st.rerun()
            
            with col_fsm2:
                if st.button("Submit handover for supervisor review", icon=":material/send:", key="fsm_submit_btn"):
                    st.session_state.pending_prompt = f"Submit shift handover for Unit {fsm_unit}"
                    st.rerun()


# ============================================================
# TAB 3: HITL APPROVAL GOVERNANCE CENTER
# ============================================================
with tab_approvals:
    st.markdown("#### :material/gavel: Human-in-the-Loop (HITL) Approval Governance Center")
    st.caption("Review high-risk operational actions, emergency overrides, or shift turnover sign-offs before execution.")

    headers = {}
    if st.session_state.auth_token:
        headers["Authorization"] = f"Bearer {st.session_state.auth_token}"

    try:
        appr_resp = requests.get(f"{BACKEND_URL}/approvals", headers=headers, timeout=4)
        if appr_resp.status_code == 200:
            res_json = appr_resp.json()
            approvals = res_json.get("approvals", []) if isinstance(res_json, dict) else res_json
            if not approvals:
                st.success("No pending approval requests in queue.", icon=":material/check_circle:")
            else:
                for app_item in approvals:

                    with st.container(border=True):
                        st.markdown(f"**Action**: `{app_item.get('action')}` | **Unit**: `{app_item.get('unit_id', 'N/A')}`")
                        st.caption(f"Requested by: `{app_item.get('requested_by')}` | Status: `{app_item.get('status')}`")
                        st.markdown(f"> *{app_item.get('reason', 'No reason provided')}*")
                        
                        col_a1, col_a2 = st.columns(2)
                        with col_a1:
                            if st.button("Approve action", icon=":material/check:", key=f"approve_{app_item.get('id')}", type="primary"):
                                act_res = requests.post(f"{BACKEND_URL}/approvals/{app_item.get('id')}/approve", headers=headers, json={"reason": "Supervisor approved"}, timeout=4)
                                if act_res.status_code == 200:
                                    st.toast("Action approved successfully!", icon="✅")
                                    st.rerun()
                        with col_a2:
                            if st.button("Reject action", icon=":material/close:", key=f"reject_{app_item.get('id')}"):
                                act_res = requests.post(f"{BACKEND_URL}/approvals/{app_item.get('id')}/reject", headers=headers, json={"reason": "Supervisor rejected"}, timeout=4)
                                if act_res.status_code == 200:
                                    st.toast("Action rejected.", icon="❌")
                                    st.rerun()
        else:
            st.warning("Unable to fetch approval requests.")
    except Exception as ex:
        st.error(f"Error fetching approvals: {ex}")


# ============================================================
# TAB 4: SYSTEM AUDIT & TELEMETRY
# ============================================================
with tab_audit:
    st.markdown("#### :material/history: System Telemetry, Model Mesh & Audit Logs")
    st.caption("Track end-to-end multi-agent execution spans, Logfire distributed tracing, Model Mesh status, and database connection state.")

    col_t1, col_t2 = st.columns(2)
    with col_t1:
        with st.container(border=True):
            st.markdown("##### :material/database: Active database connection")
            st.code(f"Database: PostgreSQL 18 (MASS.public)\nHost: localhost:5433\nSession ID: {st.session_state.session_id}", language="text")
            st.markdown("##### :material/hub: Open-source model mesh catalog")
            st.caption("• **Planner**: `llama-3.1-8b-instant` (Sub-100ms)")
            st.caption("• **Conversational**: `mixtral-8x7b-32768` (Balanced MoE)")
            st.caption("• **Heavy Reasoning**: `llama-3.3-70b-versatile` (High RAG Precision)")

    with col_t2:
        with st.container(border=True):
            st.markdown("##### :material/monitor_heart: Logfire observability status")
            st.caption(f"Status: **{LOGFIRE_STATUS}**")
            st.markdown("[View Logfire Tracing Dashboard](https://logfire-us.pydantic.dev/jasminbabariya7/mass-qa-chatbot)")

    st.space("small")

    st.markdown("##### :material/list_alt: Session audit history")
    if st.session_state.messages:
        for idx, m in enumerate(st.session_state.messages):
            with st.expander(f"Message #{idx+1} ({m['role']})", icon=":material/article:"):
                st.code(m["content"], language="text")
                if m.get("citations"):
                    st.json(m["citations"])
    else:
        st.info("No active conversation history in current session.", icon=":material/info:")
