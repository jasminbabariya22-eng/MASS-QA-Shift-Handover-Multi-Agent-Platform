import React from 'react';
import { Plus, MessageSquare, Trash2, Shield, User, Clock, CheckCircle2 } from 'lucide-react';

export default function Sidebar({
  chatSessions = [],
  activeSessionId,
  onNewSession,
  onSelectSession,
  onDeleteSession,
  onClearAllSessions,
  user,
  role
}) {
  return (
    <aside style={{
      width: '280px',
      background: 'var(--bg-sidebar)',
      borderRight: '1px solid var(--border-color)',
      padding: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '16px',
      height: 'calc(100vh - 61px)',
      overflowY: 'auto'
    }}>
      {/* ChatGPT Style + New Chat Button (Sticky Top) */}
      <div style={{ position: 'sticky', top: 0, zIndex: 10, background: 'var(--bg-sidebar)', paddingTop: '4px', paddingBottom: '10px', borderBottom: '1px solid var(--border-color)' }}>
        <button
          onClick={onNewSession}
          className="btn-primary"
          style={{
            width: '100%',
            justifyContent: 'center',
            padding: '12px 16px',
            fontSize: '0.9rem',
            borderRadius: '10px',
            boxShadow: '0 4px 14px rgba(99, 102, 241, 0.4)'
          }}
        >
          <Plus style={{ width: 18, height: 18 }} />
          <span>+ New Chat</span>
        </button>
      </div>


      {/* Chat History Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 4px',
        marginTop: '4px'
      }}>
        <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Clock style={{ width: 14, height: 14, color: '#818CF8' }} />
          Recent Chat History
        </span>
        {chatSessions.length > 0 && (
          <button
            onClick={onClearAllSessions}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '0.75rem' }}
            title="Clear all chat history"
          >
            Clear All
          </button>
        )}
      </div>

      {/* Chat History List */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {chatSessions.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '30px 10px', fontSize: '0.82rem' }}>
            <MessageSquare style={{ width: 28, height: 28, opacity: 0.3, marginBottom: 8 }} />
            <div>No previous chat history</div>
            <div style={{ fontSize: '0.75rem', marginTop: 4 }}>Click '+ New Chat' to start a session.</div>
          </div>
        ) : (
          chatSessions.map((session) => {
            const isActive = session.id === activeSessionId;
            return (
              <div
                key={session.id}
                onClick={() => onSelectSession(session.id)}
                style={{
                  padding: '10px 12px',
                  borderRadius: '8px',
                  background: isActive ? 'rgba(99, 102, 241, 0.18)' : 'rgba(255, 255, 255, 0.03)',
                  border: isActive ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid rgba(255, 255, 255, 0.05)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '8px',
                  transition: 'all 0.15s ease'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
                  <MessageSquare style={{ width: 16, height: 16, flexShrink: 0, color: isActive ? '#818CF8' : 'var(--text-muted)' }} />
                  <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <div style={{ fontSize: '0.83rem', fontWeight: isActive ? 600 : 400, color: isActive ? '#F9FAFB' : 'var(--text-secondary)' }}>
                      {session.title || 'New Conversation'}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      {session.updatedAt || 'Just now'}
                    </div>
                  </div>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(session.id);
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--text-muted)',
                    cursor: 'pointer',
                    padding: '4px',
                    borderRadius: '4px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}
                  title="Delete chat thread"
                >
                  <Trash2 style={{ width: 13, height: 13 }} />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Footer User Info */}
      <div style={{
        marginTop: 'auto',
        paddingTop: '12px',
        borderTop: '1px solid var(--border-color)',
        fontSize: '0.78rem',
        color: 'var(--text-muted)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <User style={{ width: 14, height: 14, color: '#34D399' }} />
          <span>{user || 'Operator'}</span>
        </div>
        <span className="badge badge-info" style={{ fontSize: '0.65rem' }}>{role}</span>
      </div>
    </aside>
  );
}
