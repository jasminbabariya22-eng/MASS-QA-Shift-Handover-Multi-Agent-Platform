import React from 'react';
import { Shield, User, LogOut, CheckCircle2, AlertCircle, Zap, ShieldCheck } from 'lucide-react';

export default function Navbar({ user, role, onLogout, systemOnline }) {
  const getRoleBadge = (r) => {
    switch (r) {
      case 'SHIFT_SUPERVISOR':
      case 'PLANT_MANAGER':
        return <span className="badge badge-warning"><ShieldCheck style={{ width: 12, height: 12 }} /> {r}</span>;
      case 'ADMIN':
        return <span className="badge badge-danger"><Shield style={{ width: 12, height: 12 }} /> ADMIN</span>;
      default:
        return <span className="badge badge-info"><User style={{ width: 12, height: 12 }} /> {r}</span>;
    }
  };

  return (
    <header style={{
      background: '#0F172A',
      borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
      padding: '12px 24px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between'
    }}>
      {/* Brand Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{
          padding: '8px',
          borderRadius: '10px',
          background: 'rgba(99, 102, 241, 0.15)',
          border: '1px solid rgba(99, 102, 241, 0.3)'
        }}>
          <Zap style={{ width: '22px', height: '22px', color: '#818CF8' }} />
        </div>
        <div>
          <h1 style={{ fontSize: '1.2rem', fontWeight: 800, margin: 0, letterSpacing: '-0.3px' }}>
            MASS Operations OS
          </h1>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Petroleum Refinery Multi-Agent Intelligence Platform
          </span>
        </div>
      </div>

      {/* Center Status Indicators */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem' }}>
          {systemOnline ? (
            <span className="badge badge-success">
              <CheckCircle2 style={{ width: 12, height: 12 }} /> API Online (:8000)
            </span>
          ) : (
            <span className="badge badge-danger">
              <AlertCircle style={{ width: 12, height: 12 }} /> API Offline
            </span>
          )}
        </div>
      </div>

      {/* Right User & RBAC Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            {user}
          </div>
          <div style={{ marginTop: '2px' }}>
            {getRoleBadge(role)}
          </div>
        </div>

        <button
          onClick={onLogout}
          className="btn-secondary"
          style={{ padding: '6px 12px', fontSize: '0.8rem' }}
          title="Sign out & clear JWT session"
        >
          <LogOut style={{ width: 14, height: 14 }} />
          <span>Logout</span>
        </button>
      </div>
    </header>
  );
}
