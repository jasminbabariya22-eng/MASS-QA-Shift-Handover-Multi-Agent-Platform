import React from 'react';
import { Database, Cpu, Activity, ExternalLink, ShieldCheck } from 'lucide-react';

export default function SystemAuditTab({ sessionId, backendUrl }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        {/* Database Connection */}
        <div className="glass-card">
          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px', color: '#818CF8' }}>
            <Database style={{ width: 18, height: 18 }} />
            Active Relational Database Persistence
          </h4>
          <pre style={{ fontSize: '0.8rem', background: '#0F172A', padding: '12px', borderRadius: '8px', overflowX: 'auto', color: '#34D399' }}>
{`Engine: PostgreSQL 18 (MASS.public)
Host: localhost:5433
Connection Pool: 10 Active / 20 Overflow
Optimistic Locking: Enabled (version column)
Active Session ID: ${sessionId}`}
          </pre>
        </div>

        {/* Observability */}
        <div className="glass-card">
          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px', color: '#34D399' }}>
            <Activity style={{ width: 18, height: 18 }} />
            Logfire Observability & Distributed Tracing
          </h4>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '12px' }}>
            OpenTelemetry tracing tracks end-to-end multi-agent execution spans, Qdrant vector retrieval latency, and model gateway timeouts.
          </p>
          <a
            href="https://logfire-us.pydantic.dev/jasminbabariya7/mass-qa-chatbot"
            target="_blank"
            rel="noreferrer"
            className="btn-primary"
            style={{ fontSize: '0.8rem', textDecoration: 'none' }}
          >
            <ExternalLink style={{ width: 14, height: 14 }} /> Open Logfire Dashboard
          </a>
        </div>
      </div>

      {/* Model Mesh Specs */}
      <div className="glass-card">
        <h4 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px', color: '#F59E0B' }}>
          <Cpu style={{ width: 18, height: 18 }} />
          Model Mesh Catalog & Routing Policies
        </h4>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', fontSize: '0.8rem' }}>
          <div style={{ padding: '10px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px' }}>
            <div style={{ fontWeight: 600, color: '#818CF8' }}>⚡ LLaMA-3.1 8B Instant</div>
            <div style={{ color: 'var(--text-muted)', marginTop: 4 }}>Sub-100ms intent classification & planning</div>
          </div>

          <div style={{ padding: '10px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px' }}>
            <div style={{ fontWeight: 600, color: '#34D399' }}>⚖️ Mixtral 8x7B MoE</div>
            <div style={{ color: 'var(--text-muted)', marginTop: 4 }}>Cost-balanced conversational synthesis</div>
          </div>

          <div style={{ padding: '10px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px' }}>
            <div style={{ fontWeight: 600, color: '#F59E0B' }}>🧠 LLaMA-3.3 70B Versatile</div>
            <div style={{ color: 'var(--text-muted)', marginTop: 4 }}>High-capacity technical RAG reasoning</div>
          </div>
        </div>
      </div>
    </div>
  );
}
