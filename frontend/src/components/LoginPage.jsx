import React, { useState } from 'react';
import { Shield, Key, User, Lock, Activity, CheckCircle2, AlertTriangle } from 'lucide-react';

const ROLES = [
  { id: 'CONSOLE_OPERATOR', label: 'Console Operator', desc: 'Standard shift logging & SOP search' },
  { id: 'SHIFT_SUPERVISOR', label: 'Shift Supervisor', desc: 'Full shift approval & HITL sign-off' },
  { id: 'PLANT_MANAGER', label: 'Plant Manager', desc: 'Executive oversight & emergency override' },
  { id: 'OPERATIONS_ENGINEER', label: 'Operations Engineer', desc: 'Technical specs & unit diagnostics' },
  { id: 'ADMIN', label: 'System Administrator', desc: 'Full system RBAC administration' }
];

export default function LoginPage({ onLogin, backendUrl }) {
  const [userId, setUserId] = useState('op_console_1');
  const [role, setRole] = useState('CONSOLE_OPERATOR');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!userId.trim()) return;

    setLoading(true);
    setError('');

    try {
      const res = await fetch(`${backendUrl}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          username: userId,
          role: role
        })
      });

      if (res.ok) {
        const data = await res.json();
        onLogin({
          token: data.access_token,
          user_id: userId,
          role: role
        });
      } else {
        const errText = await res.text();
        setError(`Authentication failed: ${errText}`);
      }
    } catch (err) {
      setError(`Backend connection error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'radial-gradient(circle at 50% 30%, #1E1B4B 0%, #0B0F19 70%)',
      padding: '20px'
    }}>
      <div style={{ width: '100%', maxWidth: '440px' }} className="glass-card">
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <div style={{
            display: 'inline-flex',
            padding: '12px',
            borderRadius: '16px',
            background: 'rgba(99, 102, 241, 0.15)',
            border: '1px solid rgba(99, 102, 241, 0.3)',
            marginBottom: '12px'
          }}>
            <Shield style={{ width: '32px', height: '32px', color: '#818CF8' }} />
          </div>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 800, background: 'linear-gradient(90deg, #818CF8 0%, #34D399 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            MASS Operations Portal
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginTop: '4px' }}>
            Oil & Gas Refinery Multi-Agent Intelligence OS
          </p>
        </div>

        {error && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#F87171',
            borderRadius: '8px',
            padding: '10px 14px',
            fontSize: '0.85rem',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            <AlertTriangle style={{ width: '16px', height: '16px', flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
              OPERATOR USER ID
            </label>
            <div style={{ position: 'relative' }}>
              <User style={{ position: 'absolute', left: '12px', top: '12px', width: '16px', height: '16px', color: 'var(--text-muted)' }} />
              <input
                type="text"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="e.g. op_console_1"
                style={{ paddingLeft: '38px' }}
                required
              />
            </div>
          </div>

          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
              SELECT OPERATIONAL ROLE (RBAC)
            </label>
            <div style={{ position: 'relative' }}>
              <Lock style={{ position: 'absolute', left: '12px', top: '12px', width: '16px', height: '16px', color: 'var(--text-muted)' }} />
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                style={{ paddingLeft: '38px' }}
              >
                {ROLES.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label} ({r.id})
                  </option>
                ))}
              </select>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '6px' }}>
              {ROLES.find(r => r.id === role)?.desc}
            </p>
          </div>

          <button
            type="submit"
            className="btn-primary"
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center', padding: '12px' }}
          >
            {loading ? (
              <Activity style={{ animation: 'spin 1s linear infinite', width: '18px', height: '18px' }} />
            ) : (
              <>
                <Key style={{ width: '18px', height: '18px' }} />
                <span>Authenticate & Access Portal</span>
              </>
            )}
          </button>
        </form>

        <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border-color)', textAlign: 'center' }}>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            🛡️ Role-Based Access Control (RBAC) enforced by AI Harness Governance
          </p>
        </div>
      </div>
    </div>
  );
}
