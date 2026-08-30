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
  const [loginId, setLoginId] = useState('op_console_1');
  const [password, setPassword] = useState('pass123');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!loginId.trim() || !password.trim()) return;

    setLoading(true);
    setError('');

    try {
      const res = await fetch(`${backendUrl}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          login_id: loginId,
          password: password
        })
      });

      if (res.ok) {
        const data = await res.json();
        const verifiedUser = data.user || {};
        onLogin({
          token: data.access_token,
          user_id: verifiedUser.user_id || loginId,
          role: verifiedUser.role || 'CONSOLE_OPERATOR'
        });
      } else {
        setError('Authentication failed: Invalid login_id or password.');
      }
    } catch (err) {
      setError(`Backend connection error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const setPresetUser = (usr, pwd) => {
    setLoginId(usr);
    setPassword(pwd);
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
        <div style={{ textAlign: 'center', marginBottom: '20px' }}>
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
            Oil & Gas Refinery Database Login & RBAC Control
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

        {/* Demo Accounts Preset Buttons */}
        <div style={{ marginBottom: '16px', padding: '10px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 6 }}>
            🔑 Select Demo Account Credentials:
          </div>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            <button type="button" onClick={() => setPresetUser('op_console_1', 'pass123')} className="btn-secondary" style={{ fontSize: '0.72rem', padding: '4px 8px' }}>
              op_console_1 (Operator)
            </button>
            <button type="button" onClick={() => setPresetUser('sup_shift_1', 'pass123')} className="btn-secondary" style={{ fontSize: '0.72rem', padding: '4px 8px' }}>
              sup_shift_1 (Supervisor)
            </button>
            <button type="button" onClick={() => setPresetUser('mgr_plant_1', 'pass123')} className="btn-secondary" style={{ fontSize: '0.72rem', padding: '4px 8px' }}>
              mgr_plant_1 (Manager)
            </button>
          </div>
        </div>

        {/* Login Form */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
              LOGIN ID
            </label>
            <div style={{ position: 'relative' }}>
              <User style={{ position: 'absolute', left: '12px', top: '12px', width: '16px', height: '16px', color: 'var(--text-muted)' }} />
              <input
                type="text"
                value={loginId}
                onChange={(e) => setLoginId(e.target.value)}
                placeholder="Enter login_id (e.g. op_console_1)"
                style={{ paddingLeft: '38px' }}
                required
              />
            </div>
          </div>

          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px' }}>
              PASSWORD
            </label>
            <div style={{ position: 'relative' }}>
              <Lock style={{ position: 'absolute', left: '12px', top: '12px', width: '16px', height: '16px', color: 'var(--text-muted)' }} />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password (e.g. pass123)"
                style={{ paddingLeft: '38px' }}
                required
              />
            </div>
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
                <span>Verify Credentials & Authenticate</span>
              </>
            )}
          </button>
        </form>

        <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border-color)', textAlign: 'center' }}>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            🛡️ Role-Based Access Control (RBAC) retrieved directly from PostgreSQL credentials
          </p>
        </div>
      </div>
    </div>
  );
}

