import React, { useState, useEffect } from 'react';
import LoginPage from './components/LoginPage';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import QAChatTab from './components/QAChatTab';
import FieldVoiceShiftTab from './components/FieldVoiceShiftTab';
import HITLGovernanceTab from './components/HITLGovernanceTab';
import SystemAuditTab from './components/SystemAuditTab';
import { Search, Mic, ShieldCheck, Activity } from 'lucide-react';

const BACKEND_URL = 'http://localhost:8000';

export default function App() {
  const [auth, setAuth] = useState(null);
  const [chatSessions, setChatSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState('');
  const [activeTab, setActiveTab] = useState('qa');
  const [systemOnline, setSystemOnline] = useState(false);

  useEffect(() => {
    const savedAuth = localStorage.getItem('mass_auth_session');
    if (savedAuth) {
      try {
        setAuth(JSON.parse(savedAuth));
      } catch (e) {
        localStorage.removeItem('mass_auth_session');
      }
    }

    const savedSessions = localStorage.getItem('mass_chat_sessions');
    if (savedSessions) {
      try {
        const parsed = JSON.parse(savedSessions);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setChatSessions(parsed);
          setActiveSessionId(parsed[0].id);
        } else {
          createNewChatSession();
        }
      } catch (e) {
        createNewChatSession();
      }
    } else {
      createNewChatSession();
    }

    // Check Backend Health
    fetch(`${BACKEND_URL}/ready`)
      .then(res => res.ok && setSystemOnline(true))
      .catch(() => setSystemOnline(false));
  }, []);

  const saveSessionsToStorage = (sessions) => {
    setChatSessions(sessions);
    localStorage.setItem('mass_chat_sessions', JSON.stringify(sessions));
  };

  const createNewChatSession = () => {
    const newId = crypto.randomUUID();
    const newSession = {
      id: newId,
      title: 'New Conversation',
      updatedAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      messages: []
    };
    setChatSessions(prev => {
      const updated = [newSession, ...prev];
      localStorage.setItem('mass_chat_sessions', JSON.stringify(updated));
      return updated;
    });
    setActiveSessionId(newId);
    return newId;
  };

  const handleSelectSession = (id) => {
    setActiveSessionId(id);
    setActiveTab('qa');
  };

  const handleDeleteSession = async (id) => {
    const updated = chatSessions.filter(s => s.id !== id);
    saveSessionsToStorage(updated);
    try {
      await fetch(`${BACKEND_URL}/sessions/${id}`, { method: 'DELETE' });
    } catch (e) {}

    if (activeSessionId === id) {
      if (updated.length > 0) {
        setActiveSessionId(updated[0].id);
      } else {
        createNewChatSession();
      }
    }
  };

  const handleClearAllSessions = () => {
    saveSessionsToStorage([]);
    createNewChatSession();
  };

  const updateActiveSessionMessages = (newMessages, firstPrompt = '') => {
    setChatSessions(prev => {
      const updated = prev.map(s => {
        if (s.id === activeSessionId) {
          let title = s.title;
          if ((!title || title === 'New Conversation') && firstPrompt) {
            title = firstPrompt.length > 32 ? `${firstPrompt.substring(0, 32)}...` : firstPrompt;
          }
          return {
            ...s,
            title: title,
            updatedAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            messages: newMessages
          };
        }
        return s;
      });
      localStorage.setItem('mass_chat_sessions', JSON.stringify(updated));
      return updated;
    });
  };

  const handleLogin = (userAuth) => {
    setAuth(userAuth);
    localStorage.setItem('mass_auth_session', JSON.stringify(userAuth));
  };

  const handleLogout = () => {
    setAuth(null);
    localStorage.removeItem('mass_auth_session');
  };

  if (!auth || !auth.token) {
    return <LoginPage onLogin={handleLogin} backendUrl={BACKEND_URL} />;
  }


  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-dark)' }}>
      {/* Top Navbar */}
      <Navbar
        user={auth.user_id}
        role={auth.role}
        onLogout={handleLogout}
        systemOnline={systemOnline}
      />

      {/* Main Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* ChatGPT Style Sidebar */}
        <Sidebar
          chatSessions={chatSessions}
          activeSessionId={activeSessionId}
          onNewSession={createNewChatSession}
          onSelectSession={handleSelectSession}
          onDeleteSession={handleDeleteSession}
          onClearAllSessions={handleClearAllSessions}
          user={auth.user_id}
          role={auth.role}
        />

        {/* Content Area */}
        <main style={{ flex: 1, padding: '24px', overflowY: 'auto' }}>
          {/* Executive Dashboard KPI Metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '24px' }}>
            <div className="glass-card" style={{ padding: '14px 18px' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Active Refinery Units</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: 4 }}>2 Units</div>
              <div style={{ fontSize: '0.75rem', color: '#34D399', marginTop: 2 }}>CDU-101, HCU-202</div>
            </div>

            <div className="glass-card" style={{ padding: '14px 18px' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>HITL Safety Interlocks</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#34D399', marginTop: 4 }}>0 Pending</div>
              <div style={{ fontSize: '0.75rem', color: '#34D399', marginTop: 2 }}>All Interlocks Clear</div>
            </div>

            <div className="glass-card" style={{ padding: '14px 18px' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Field Voice Engine</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#818CF8', marginTop: 4 }}>Active</div>
              <div style={{ fontSize: '0.75rem', color: '#818CF8', marginTop: 2 }}>Gemini 3.6 Flash Audio</div>
            </div>

            <div className="glass-card" style={{ padding: '14px 18px' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>AI Quality Gate Avg</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#FBBF24', marginTop: 4 }}>94.2%</div>
              <div style={{ fontSize: '0.75rem', color: '#34D399', marginTop: 2 }}>+5.8% Compliance</div>
            </div>
          </div>

          {/* Navigation Tabs Bar */}
          <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '20px', paddingBottom: '8px' }}>
            <button
              onClick={() => setActiveTab('qa')}
              className={activeTab === 'qa' ? 'btn-primary' : 'btn-secondary'}
              style={{ fontSize: '0.88rem' }}
            >
              <Search style={{ width: 16, height: 16 }} />
              Technical QA & SOP Search
            </button>

            <button
              onClick={() => setActiveTab('voice')}
              className={activeTab === 'voice' ? 'btn-primary' : 'btn-secondary'}
              style={{ fontSize: '0.88rem' }}
            >
              <Mic style={{ width: 16, height: 16 }} />
              Field Voice Note & Shift Handover
            </button>

            <button
              onClick={() => setActiveTab('hitl')}
              className={activeTab === 'hitl' ? 'btn-primary' : 'btn-secondary'}
              style={{ fontSize: '0.88rem' }}
            >
              <ShieldCheck style={{ width: 16, height: 16 }} />
              HITL Governance Center
            </button>

            <button
              onClick={() => setActiveTab('audit')}
              className={activeTab === 'audit' ? 'btn-primary' : 'btn-secondary'}
              style={{ fontSize: '0.88rem' }}
            >
              <Activity style={{ width: 16, height: 16 }} />
              System Telemetry & Audit
            </button>
          </div>

          {/* Tab Content Views */}
          {activeTab === 'qa' && (
            <QAChatTab
              backendUrl={BACKEND_URL}
              token={auth.token}
              sessionId={activeSessionId}
              initialMessages={chatSessions.find(s => s.id === activeSessionId)?.messages || []}
              onUpdateMessages={updateActiveSessionMessages}
            />
          )}

          {activeTab === 'voice' && (
            <FieldVoiceShiftTab
              backendUrl={BACKEND_URL}
              token={auth.token}
              user={auth.user_id}
              role={auth.role}
              onSendPrompt={(prompt) => {
                setActiveTab('qa');
              }}
            />
          )}

          {activeTab === 'hitl' && (
            <HITLGovernanceTab backendUrl={BACKEND_URL} token={auth.token} role={auth.role} />
          )}

          {activeTab === 'audit' && (
            <SystemAuditTab sessionId={activeSessionId} backendUrl={BACKEND_URL} />
          )}
        </main>

      </div>
    </div>
  );
}
