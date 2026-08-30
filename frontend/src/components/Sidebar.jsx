import React from 'react';
import { Bot, Database, Cpu, ShieldCheck, Plus, Trash2, Layers, RefreshCw } from 'lucide-react';

export default function Sidebar({ sessionId, onNewSession, onClearMemory }) {
  return (
    <aside style={{
      width: '280px',
      background: 'var(--bg-sidebar)',
      borderRight: '1px solid var(--border-color)',
      padding: '20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '20px',
      height: 'calc(100vh - 61px)',
      overflowY: 'auto'
    }}>
      {/* Active Multi-Agent Mesh Card */}
      <div className="glass-card" style={{ padding: '16px' }}>
        <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px', color: '#818CF8' }}>
          <Bot style={{ width: 16, height: 16 }} />
          Active Agent Mesh
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ padding: '10px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>QA Technical Agent</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>SOPs, P&IDs (Qdrant 3072d)</div>
          </div>

          <div style={{ padding: '10px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>Shift Handover Agent</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>FSM, PostgreSQL, Voice, Quality Gate</div>
          </div>

          <div style={{ padding: '10px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>AI Harness & HITL Gate</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>Safety Interlock & Authorization</div>
          </div>
        </div>
      </div>

      {/* Model Mesh Gateway Info */}
      <div className="glass-card" style={{ padding: '16px' }}>
        <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px', color: '#34D399' }}>
          <Cpu style={{ width: 16, height: 16 }} />
          Open-Source Model Mesh
        </h3>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div>⚡ <strong>Planner</strong>: <code>llama-3.1-8b-instant</code></div>
          <div>⚖️ <strong>Conversational</strong>: <code>mixtral-8x7b-32768</code></div>
          <div>🧠 <strong>Heavy RAG</strong>: <code>llama-3.3-70b-versatile</code></div>
        </div>
      </div>

      {/* Session Controls */}
      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center' }}>
          Session ID: <code>{sessionId ? `${sessionId.substring(0, 10)}...` : 'N/A'}</code>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
          <button onClick={onNewSession} className="btn-secondary" style={{ fontSize: '0.78rem', padding: '8px', justifyContent: 'center' }}>
            <Plus style={{ width: 14, height: 14 }} /> New
          </button>
          <button onClick={onClearMemory} className="btn-secondary" style={{ fontSize: '0.78rem', padding: '8px', justifyContent: 'center' }}>
            <Trash2 style={{ width: 14, height: 14 }} /> Clear
          </button>
        </div>
      </div>
    </aside>
  );
}
