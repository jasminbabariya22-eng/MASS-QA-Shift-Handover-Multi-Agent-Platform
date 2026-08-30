import React, { useState, useEffect } from 'react';
import { ShieldCheck, Lock, CheckCircle2, XCircle, AlertTriangle, RefreshCw } from 'lucide-react';

export default function HITLGovernanceTab({ backendUrl, token, role }) {
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const isAuthorized = ['SHIFT_SUPERVISOR', 'PLANT_MANAGER', 'ADMIN'].includes(role);

  const fetchApprovals = async () => {
    if (!token) return;
    setLoading(true);
    setError('');

    try {
      const res = await fetch(`${backendUrl}/approvals`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setApprovals(data.approvals || (Array.isArray(data) ? data : []));
      } else {
        setError('Failed to fetch approval requests.');
      }
    } catch (err) {
      setError(`Connection error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApprovals();
  }, [token]);

  const handleAction = async (approvalId, actionType) => {
    try {
      const res = await fetch(`${backendUrl}/approvals/${approvalId}/${actionType}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ reason: `Supervisor ${actionType}d action` })
      });

      if (res.ok) {
        fetchApprovals();
      } else {
        const errText = await res.text();
        alert(`Action failed: ${errText}`);
      }
    } catch (err) {
      alert(`Action error: ${err.message}`);
    }
  };

  if (!isAuthorized) {
    return (
      <div className="glass-card" style={{ textAlign: 'center', padding: '40px' }}>
        <Lock style={{ width: 48, height: 48, color: '#EF4444', marginBottom: 12 }} />
        <h3 style={{ color: '#F87171' }}>Access Restricted — Role Authorization Required</h3>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: 6, maxWidth: 500, margin: '6px auto 0' }}>
          Your active role (<code>{role}</code>) does not have permission to view or authorize HITL Governance Approvals. Only <strong>SHIFT_SUPERVISOR</strong> or <strong>PLANT_MANAGER</strong> roles can perform sign-offs.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: '#F59E0B', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldCheck style={{ width: 22, height: 22 }} />
            Human-in-the-Loop (HITL) Governance Center
          </h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 2 }}>
            Review high-risk operational requests, safety interlocks, and shift turnover sign-offs before execution.
          </p>
        </div>

        <button onClick={fetchApprovals} className="btn-secondary" style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
          <RefreshCw style={{ width: 14, height: 14 }} /> Refresh Queue
        </button>
      </div>

      {loading ? (
        <div style={{ padding: '20px', color: 'var(--text-muted)' }}>Loading approval queue...</div>
      ) : error ? (
        <div style={{ color: '#F87171', padding: '12px' }}>{error}</div>
      ) : approvals.length === 0 ? (
        <div className="glass-card" style={{ textAlign: 'center', padding: '32px' }}>
          <CheckCircle2 style={{ width: 36, height: 36, color: '#10B981', marginBottom: 8 }} />
          <h4>No Pending Approval Requests</h4>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>All operational actions and shift turnovers are cleared.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {approvals.map((app) => (
            <div key={app.id} className="glass-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div>
                  <span className="badge badge-warning" style={{ marginBottom: 6 }}>
                    Action: {app.action}
                  </span>
                  <div style={{ fontSize: '0.9rem', fontWeight: 700 }}>
                    Unit: {app.unit_id || 'N/A'} (ID: <code>{app.id}</code>)
                  </div>
                </div>
                <span className="badge badge-info">{app.status}</span>
              </div>

              <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: 12 }}>
                Requester: <code>{app.requested_by}</code> | Reason: <em>"{app.reason || 'No reason specified'}"</em>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  onClick={() => handleAction(app.id, 'approve')}
                  className="btn-success"
                >
                  <CheckCircle2 style={{ width: 16, height: 16 }} /> Authorize & Approve Action
                </button>

                <button
                  onClick={() => handleAction(app.id, 'reject')}
                  className="btn-danger"
                >
                  <XCircle style={{ width: 16, height: 16 }} /> Reject Action
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
