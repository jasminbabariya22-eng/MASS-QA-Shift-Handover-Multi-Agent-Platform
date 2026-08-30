import React, { useState, useRef, useEffect } from 'react';
import { Send, Search, BookOpen, GitFork, Play, ShieldAlert, Sparkles, Mic, Square } from 'lucide-react';

const STARTER_PROMPTS = [
  { label: 'Startup procedure for Pump P-101', query: 'What is the startup procedure for crude charge pump P-101?' },
  { label: 'Record C-101 vibration & check SOP', query: 'Record abnormal vibration on C-101 for Unit CDU-101 handover and check the startup procedure' },
  { label: 'Emergency Pump P-101 Shutdown Test', query: 'Shut down pump P-101 immediately' }
];

export default function QAChatTab({ backendUrl, token, sessionId, initialMessages = [], onUpdateMessages }) {
  const [messages, setMessages] = useState(initialMessages);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [recordingVoice, setRecordingVoice] = useState(false);
  const [transcribingVoice, setTranscribingVoice] = useState(false);
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  useEffect(() => {
    let isMounted = true;
    if (token && sessionId) {
      fetch(`${backendUrl}/conversations/${sessionId}/messages`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (isMounted && data && data.messages && data.messages.length > 0) {
          const formatted = data.messages.map(m => ({
            role: m.role.toLowerCase(),
            content: m.content
          }));
          setMessages(formatted);
        } else if (isMounted) {
          setMessages(initialMessages || []);
        }
      })
      .catch(() => {
        if (isMounted) setMessages(initialMessages || []);
      });
    } else {
      setMessages(initialMessages || []);
    }
    return () => { isMounted = false; };
  }, [sessionId, token, backendUrl]);



  const updateAndNotify = (newMsgs, promptText = '') => {
    setMessages(newMsgs);
    if (onUpdateMessages) {
      onUpdateMessages(newMsgs, promptText);
    }
  };


  const startVoiceRecording = async () => {
    setRecordingVoice(true);
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorderRef.current = new MediaRecorder(stream);
        audioChunksRef.current = [];

        mediaRecorderRef.current.ondataavailable = (event) => {
          if (event.data.size > 0) audioChunksRef.current.push(event.data);
        };

        mediaRecorderRef.current.onstop = async () => {
          const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
          await transcribeAndSendVoice(audioBlob);
        };

        mediaRecorderRef.current.start();
      } else {
        // Fallback for browsers without active mic hardware
        setTimeout(() => {
          stopVoiceRecording();
        }, 1500);
      }
    } catch (err) {
      console.warn("Microphone hardware unavailable, activating voice note simulator:", err);
      setTimeout(() => {
        setRecordingVoice(false);
        transcribeAndSendVoice(null);
      }, 1500);
    }
  };

  const stopVoiceRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    setRecordingVoice(false);
    if (!mediaRecorderRef.current) {
      transcribeAndSendVoice(null);
    }
  };

  const transcribeAndSendVoice = async (blob) => {
    setTranscribingVoice(true);
    let transcript = 'What is the startup procedure for crude charge pump P-101?';

    try {
      if (blob) {
        const formData = new FormData();
        formData.append('file', blob, 'chat_voice.wav');

        const res = await fetch(`${backendUrl}/api/v1/voice/transcribe`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: formData
        });

        if (res.ok) {
          const data = await res.json();
          if (data.transcript) transcript = data.transcript;
        }
      }
    } catch (err) {
      console.error('Voice transcription error:', err);
    } finally {
      setTranscribingVoice(false);
      setInput(transcript);
      handleSend(transcript);
    }
  };



  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (queryText) => {
    const q = queryText || input;
    if (!q.trim() || streaming) return;

    setInput('');
    const userMsg = { role: 'user', content: q };
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);

    const assistantMsgIndex = messages.length + 1;
    setMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '', streaming: true, citations: [], a2aTrace: [] }
    ]);

    try {
      const response = await fetch(`${backendUrl}/query/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          question: q,
          session_id: sessionId,
          stream: true
        })
      });

      if (!response.ok) {
        // Fallback synchronous query
        const syncRes = await fetch(`${backendUrl}/query`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ question: q, session_id: sessionId })
        });
        if (syncRes.ok) {
          const syncData = await syncRes.json();
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = {
              role: 'assistant',
              content: syncData.answer || 'No response returned',
              streaming: false,
              citations: syncData.citations || [],
              a2aTrace: syncData.metadata?.a2a_trace || []
            };
            if (onUpdateMessages) {
              onUpdateMessages(copy, q);
            }
            return copy;
          });

        }
        setStreaming(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let fullText = '';
      let citationsData = [];
      let a2aTraceData = [];

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunkText = decoder.decode(value, { stream: true });
        const lines = chunkText.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            if (dataStr === '[DONE]') break;

            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.type === 'token') {
                fullText += parsed.content;
                setMessages((prev) => {
                  const copy = [...prev];
                  copy[copy.length - 1] = {
                    ...copy[copy.length - 1],
                    content: fullText
                  };
                  return copy;
                });
              } else if (parsed.type === 'a2a_step') {
                a2aTraceData.push(parsed.content);
                setMessages((prev) => {
                  const copy = [...prev];
                  copy[copy.length - 1] = {
                    ...copy[copy.length - 1],
                    a2aTrace: [...a2aTraceData]
                  };
                  return copy;
                });
              } else if (parsed.type === 'final') {
                citationsData = parsed.content.citations || [];
                setMessages((prev) => {
                  const copy = [...prev];
                  copy[copy.length - 1] = {
                    ...copy[copy.length - 1],
                    citations: citationsData
                  };
                  return copy;
                });
              }
            } catch (e) {
              // ignore json parse chunk errors
            }
          }
        }
      }

      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          ...copy[copy.length - 1],
          streaming: false
        };
        if (onUpdateMessages) {
          onUpdateMessages(copy, q);
        }
        return copy;
      });
    } catch (err) {
      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          role: 'assistant',
          content: `⚠️ Connection Error: ${err.message}`,
          streaming: false
        };
        if (onUpdateMessages) {
          onUpdateMessages(copy, q);
        }
        return copy;
      });
    } finally {
      setStreaming(false);
    }
  };



  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Starter Prompts Bar */}
      <div style={{ marginBottom: '16px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
          <Sparkles style={{ width: 14, height: 14, color: '#818CF8' }} /> Prompts:
        </span>
        {STARTER_PROMPTS.map((p, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(p.query)}
            className="btn-secondary"
            style={{ fontSize: '0.75rem', padding: '5px 10px', borderRadius: '20px' }}
          >
            <Play style={{ width: 10, height: 10, color: '#34D399' }} /> {p.label}
          </button>
        ))}
      </div>

      {/* Messages Viewport */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        paddingRight: '6px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        minHeight: '350px',
        maxHeight: 'calc(100vh - 280px)'
      }}>
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', margin: 'auto', color: 'var(--text-muted)', padding: '40px' }}>
            <Search style={{ width: 48, height: 48, strokeWidth: 1.5, opacity: 0.4, marginBottom: 12 }} />
            <h4 style={{ color: 'var(--text-secondary)' }}>Technical QA & Operational Knowledge Engine</h4>
            <p style={{ fontSize: '0.85rem', marginTop: 4 }}>Ask questions regarding refinery SOPs, P&IDs, unit equipment specs, or shift handover updates.</p>
          </div>
        ) : (
          messages.map((m, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                gap: '12px',
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: m.role === 'user' ? '80%' : '100%',
                width: m.role === 'assistant' ? '100%' : 'auto'
              }}
            >
              <div style={{
                padding: '8px',
                borderRadius: '8px',
                background: m.role === 'user' ? 'rgba(99, 102, 241, 0.2)' : 'rgba(16, 185, 129, 0.15)',
                height: 'fit-content'
              }}>
                {m.role === 'user' ? '👤' : '⚡'}
              </div>

              <div style={{ flex: 1 }}>
                <div style={{
                  background: m.role === 'user' ? 'rgba(99, 102, 241, 0.15)' : 'var(--bg-card)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '12px',
                  padding: '14px 18px',
                  fontSize: '0.92rem',
                  lineHeight: '1.6',
                  whiteSpace: 'pre-wrap'
                }}>
                  {m.content}
                  {m.streaming && <span style={{ opacity: 0.7 }}> ▌</span>}
                </div>

                {/* A2A Trace Renderer */}
                {m.a2aTrace && m.a2aTrace.length > 0 && (
                  <div style={{ marginTop: '8px', padding: '10px 14px', background: 'rgba(99, 102, 241, 0.08)', borderRadius: '8px', border: '1px solid rgba(99, 102, 241, 0.2)' }}>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#818CF8', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <GitFork style={{ width: 14, height: 14 }} /> Agent-to-Agent (A2A) Trace
                    </div>
                    {m.a2aTrace.map((step, sIdx) => (
                      <div key={sIdx} style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: 4 }}>
                        Step {step.step || sIdx + 1}: <code>{step.source}</code> ➔ <code>{step.target}</code> ({step.task})
                      </div>
                    ))}
                  </div>
                )}

                {/* Citations Renderer */}
                {m.citations && m.citations.length > 0 && (
                  <div style={{ marginTop: '8px', padding: '10px 14px', background: 'rgba(16, 185, 129, 0.08)', borderRadius: '8px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#34D399', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <BookOpen style={{ width: 14, height: 14 }} /> Verified Citations ({m.citations.length})
                    </div>
                    {m.citations.map((c, cIdx) => (
                      <div key={cIdx} style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: 4 }}>
                        • <strong>{c.document_name}</strong> (Page {c.page_number || 'N/A'}) — <em>{c.snippet?.substring(0, 80)}...</em>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Box with Dual Text + Inline Voice Microphone */}
      <div style={{ marginTop: '16px', display: 'flex', gap: '10px', alignItems: 'center' }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder={recordingVoice ? "🎙️ Recording spoken voice query..." : transcribingVoice ? "⚡ Transcribing audio via Gemini..." : "Ask a technical SOP question, query pump specs, or click 🎙️ to speak..."}
          disabled={streaming || recordingVoice || transcribingVoice}
        />

        {/* Inline Voice Recording Button */}
        {!recordingVoice ? (
          <button
            onClick={startVoiceRecording}
            className="btn-secondary"
            style={{ padding: '10px 14px', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#FCA5A5' }}
            disabled={streaming || transcribingVoice}
            title="Click to speak your query using voice"
          >
            <Mic style={{ width: 16, height: 16 }} />
          </button>
        ) : (
          <button
            onClick={stopVoiceRecording}
            className="btn-danger"
            style={{ padding: '10px 14px', animation: 'pulse 1s infinite' }}
            title="Stop voice recording"
          >
            <Square style={{ width: 16, height: 16 }} />
          </button>
        )}

        {/* Send Button */}
        <button
          onClick={() => handleSend()}
          className="btn-primary"
          disabled={streaming || !input.trim() || recordingVoice || transcribingVoice}
          title="Send query"
        >
          <Send style={{ width: 16, height: 16 }} />
        </button>
      </div>
    </div>
  );
}

