# MASS QA & Shift Handover Multi-Agent Platform

An enterprise-grade, multi-agent AI intelligence platform for petroleum refining, downstream chemical operations, technical QA RAG search, and automated shift turnover management.

---

## ⚡ Quick Application Run Guide

### 1. Backend Gateway Server (`http://localhost:8000`)
```powershell
# Activate Python environment
.\.venv\Scripts\Activate.ps1

# Launch FastAPI Uvicorn Server on Port 8000
$env:LOGFIRE_IGNORE_NO_CONFIG="1"; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
- 🌐 **Interactive OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- ⚙️ **Readiness Probe**: [http://localhost:8000/ready](http://localhost:8000/ready)

### 2. React Vite Single-Page Application (`http://localhost:5173`)
```powershell
# Navigate to frontend directory
cd frontend

# Install dependencies (if first time)
npm install

# Launch React Vite Dev Server on Port 5173
npm run dev -- --host 0.0.0.0 --port 5173
```
- ⚛️ **React Operations Portal**: [http://localhost:5173](http://localhost:5173)
- 🔑 **Pre-seeded Demo Accounts**:
  - `op_console_1` / `pass123` (Console Operator)
  - `sup_shift_1` / `pass123` (Shift Supervisor)
  - `mgr_plant_1` / `pass123` (Plant Manager)

---

## 📚 Complete Technical Documentation Hub

All 23 detailed subsystem engineering guides are located in the [`docs/`](docs/) directory:

- 📄 [PROJECT OVERVIEW](docs/00_PROJECT_OVERVIEW.md) — System architecture, open-source models, technology stack.
- ⚛️ [REACT SPA FRONTEND](docs/18_REACT_VITE_SPA_FRONTEND.md) — React UI, ChatGPT-style sidebar, inline 🎙️ microphone voice input.
- 🔑 [DATABASE AUTH & RBAC](docs/19_DATABASE_AUTHENTICATION_AND_RBAC.md) — Database authentication & 8 Personnel Job Roles matrix.
- 🤝 [P2P AGENT PROTOCOL](docs/15_P2P_BIDIRECTIONAL_AGENT_COMMUNICATION.md) — True multi-turn bidirectional agent exchange.
- 🎙️ [VOICE INGESTION ENGINE](docs/16_VOICE_TRANSCRIPTION_AND_INGESTION.md) — Gemini 3.6 Flash audio speech-to-text transcriber.
- 📊 [AI QUALITY GATE ENGINE](docs/17_AI_QUALITY_GATE_ENGINE.md) — 0–100% shift handover completeness scoring.
- 🛡️ [HUMAN-IN-THE-LOOP (HITL)](docs/11_HITL_HUMAN_IN_THE_LOOP.md) — Safety interlocks, separation of duty, supervisor approval queue.
- 📑 [DOCUMENTATION INDEX](docs/README.md) — Complete 23-document index.
