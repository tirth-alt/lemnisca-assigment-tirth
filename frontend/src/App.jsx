import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'

const API_BASE = ''  // Proxied via Vite in dev

const SUGGESTIONS = [
    'What are the pricing plans for ClearPath?',
    'How do I set up integrations?',
    'Explain the keyboard shortcuts available',
    'What is the SLA for support response times?',
]

// Map evaluator flags to user-friendly warning labels
const FLAG_LABELS = {
    no_context: '⚠️ Low confidence — no supporting documents found. Please verify with support.',
    refusal: '⚠️ This question may not be covered in our documentation.',
    low_grounding: '⚠️ Low confidence — this response may not be fully accurate. Please verify with support.',
}

export default function App() {
    const [conversations, setConversations] = useState([])
    const [activeConvId, setActiveConvId] = useState(null)
    const [messages, setMessages] = useState([])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    const messagesEndRef = useRef(null)
    const textareaRef = useRef(null)

    // Load conversations from backend on mount
    useEffect(() => {
        fetch(`${API_BASE}/conversations`)
            .then(res => res.json())
            .then(data => setConversations(data))
            .catch(() => { })  // silently fail on first load
    }, [])

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages, loading])

    // Auto-resize textarea
    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto'
            textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 150) + 'px'
        }
    }, [input])

    // Clear error after 4s
    useEffect(() => {
        if (error) {
            const t = setTimeout(() => setError(null), 4000)
            return () => clearTimeout(t)
        }
    }, [error])

    const startNewChat = useCallback(() => {
        setActiveConvId(null)
        setMessages([])
        setInput('')
    }, [])

    const loadConversation = useCallback(async (convId) => {
        try {
            const res = await fetch(`${API_BASE}/conversations/${convId}/messages`)
            if (!res.ok) throw new Error('Failed to load conversation')
            const data = await res.json()

            setActiveConvId(convId)
            // Transform backend messages to frontend format
            const frontendMessages = data.messages.map(msg => ({
                role: msg.role,
                content: msg.content,
                sources: msg.sources || undefined,
                metadata: msg.metadata || undefined,
            }))
            setMessages(frontendMessages)
        } catch (err) {
            setError('Failed to load conversation')
        }
    }, [])

    const sendMessage = useCallback(async (text) => {
        const question = (text || input).trim()
        if (!question || loading) return

        setInput('')

        // Add user message
        const userMsg = { role: 'user', content: question }
        setMessages(prev => [...prev, userMsg])
        setLoading(true)

        // Add empty assistant message that will be filled token-by-token
        const streamingMsg = { role: 'assistant', content: '', streaming: true }
        setMessages(prev => [...prev, streamingMsg])

        // Token queue for typing effect
        const tokenQueue = []
        let doneEvent = null
        let streamFinished = false
        let draining = false

        const TYPING_SPEED = 8 // ms per token — adjust for faster/slower

        function drainQueue() {
            if (draining) return
            draining = true

            const interval = setInterval(() => {
                if (tokenQueue.length > 0) {
                    const token = tokenQueue.shift()
                    setMessages(prev => {
                        const updated = [...prev]
                        const last = updated[updated.length - 1]
                        updated[updated.length - 1] = {
                            ...last,
                            content: last.content + token,
                        }
                        return updated
                    })
                } else if (streamFinished) {
                    clearInterval(interval)

                    // All tokens drained — now finalize with metadata
                    if (doneEvent) {
                        setMessages(prev => {
                            const updated = [...prev]
                            const last = updated[updated.length - 1]
                            updated[updated.length - 1] = {
                                ...last,
                                streaming: false,
                                metadata: doneEvent.metadata,
                                sources: doneEvent.sources,
                            }
                            return updated
                        })

                        if (!activeConvId) {
                            setActiveConvId(doneEvent.conversation_id)
                            setConversations(prev => [
                                { id: doneEvent.conversation_id, title: question.slice(0, 40) + (question.length > 40 ? '…' : ''), message_count: 2 },
                                ...prev,
                            ])
                        } else {
                            setConversations(prev =>
                                prev.map(c => c.id === doneEvent.conversation_id
                                    ? { ...c, message_count: (c.message_count || 0) + 2 }
                                    : c
                                )
                            )
                        }
                    }

                    setLoading(false)
                }
            }, TYPING_SPEED)
        }

        try {
            const res = await fetch(`${API_BASE}/query/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question,
                    conversation_id: activeConvId || undefined,
                }),
            })

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}))
                throw new Error(errData.detail || `Server error (${res.status})`)
            }

            const reader = res.body.getReader()
            const decoder = new TextDecoder()
            let buffer = ''

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                buffer += decoder.decode(value, { stream: true })

                const lines = buffer.split('\n')
                buffer = lines.pop()

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue
                    const jsonStr = line.slice(6)
                    if (!jsonStr) continue

                    try {
                        const event = JSON.parse(jsonStr)

                        if (event.type === 'token') {
                            tokenQueue.push(event.content)
                            if (!draining) drainQueue()
                        } else if (event.type === 'done') {
                            doneEvent = event
                        } else if (event.type === 'error') {
                            throw new Error(event.content)
                        }
                    } catch (parseErr) {
                        // Skip malformed SSE lines
                    }
                }
            }

            streamFinished = true
            if (!draining) drainQueue()

        } catch (err) {
            streamFinished = true
            setError(err.message || 'Something went wrong')
            setMessages(prev => {
                const updated = [...prev]
                const last = updated[updated.length - 1]
                if (last && last.streaming) {
                    updated[updated.length - 1] = {
                        role: 'assistant',
                        content: `⚠️ Error: ${err.message}`,
                        isError: true,
                    }
                }
                return updated
            })
            setLoading(false)
        }
    }, [input, loading, activeConvId])

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            sendMessage()
        }
    }

    const [sidebarOpen, setSidebarOpen] = useState(true)

    return (
        <div className="app-container">
            {/* ── Sidebar ──────────────────────────────────── */}
            <aside className={`sidebar ${sidebarOpen ? '' : 'collapsed'}`}>
                <div className="sidebar-header">
                    <div className="sidebar-logo" onClick={startNewChat} style={{ cursor: 'pointer' }}>
                        <div className="sidebar-logo-icon">C</div>
                        <div>
                            <h1>ClearPath</h1>
                            <span>AI Assistant</span>
                        </div>
                    </div>
                    <button className="sidebar-toggle" onClick={() => setSidebarOpen(false)} title="Close sidebar">
                        ✕
                    </button>
                </div>

                <button className="new-chat-btn" onClick={startNewChat}>
                    <span>＋</span> New Chat
                </button>

                <div className="sidebar-conversations">
                    {conversations.map(conv => (
                        <div
                            key={conv.id}
                            className={`conv-item ${conv.id === activeConvId ? 'active' : ''}`}
                            onClick={() => loadConversation(conv.id)}
                        >
                            {conv.title}
                        </div>
                    ))}
                </div>

                <div className="sidebar-footer">
                    Powered by Groq · LLaMA 3
                </div>
            </aside>

            {/* ── Main Chat ────────────────────────────────── */}
            <main className="main-content">
                <header className="chat-header">
                    <div className="chat-header-title">
                        {!sidebarOpen && (
                            <button className="sidebar-open-btn" onClick={() => setSidebarOpen(true)} title="Open sidebar">
                                ☰
                            </button>
                        )}
                        <div className="status-dot" />
                        <h2>ClearPath Assistant</h2>
                    </div>
                    <div className="chat-header-meta">
                        {activeConvId ? `Session: ${activeConvId.slice(0, 12)}…` : 'New session'}
                    </div>
                </header>

                <div className="messages-container">
                    {messages.length === 0 && !loading ? (
                        <WelcomeScreen onSuggestion={sendMessage} />
                    ) : (
                        <div className="messages-list">
                            {messages.map((msg, i) => (
                                <Message key={i} message={msg} />
                            ))}
                            <div ref={messagesEndRef} />
                        </div>
                    )}
                </div>

                <div className="input-area">
                    <div className="input-wrapper">
                        <div className="input-box">
                            <textarea
                                ref={textareaRef}
                                value={input}
                                onChange={e => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="Ask about ClearPath features, pricing, integrations…"
                                rows={1}
                                disabled={loading}
                            />
                            <button
                                className="send-btn"
                                onClick={() => sendMessage()}
                                disabled={!input.trim() || loading}
                                title="Send message"
                            >
                                ↑
                            </button>
                        </div>
                        <div className="input-hint">
                            Press Enter to send · Shift+Enter for new line
                        </div>
                    </div>
                </div>

                {error && <div className="error-toast">{error}</div>}
            </main>
        </div>
    )
}

/* ═══════════════════════════════════════════════════════════════════
   Sub-Components
   ═══════════════════════════════════════════════════════════════════ */

function WelcomeScreen({ onSuggestion }) {
    return (
        <div className="welcome-screen">
            <div className="welcome-icon">✦</div>
            <h2>Welcome to ClearPath Assistant</h2>
            <p>
                I can help you with questions about ClearPath's features, pricing,
                integrations, troubleshooting, and more. Ask me anything!
            </p>
            <div className="suggestion-chips">
                {SUGGESTIONS.map((s, i) => (
                    <button key={i} className="suggestion-chip" onClick={() => onSuggestion(s)}>
                        {s}
                    </button>
                ))}
            </div>
        </div>
    )
}

function Message({ message }) {
    const [sourcesOpen, setSourcesOpen] = useState(false)
    const isUser = message.role === 'user'
    const flags = message.metadata?.evaluator_flags || []

    return (
        <div className={`message ${isUser ? 'user' : 'assistant'}`}>
            <div className="message-header">
                <div className={`message-avatar ${isUser ? 'user' : 'assistant'}`}>
                    {isUser ? 'Y' : 'C'}
                </div>
                <span className="message-sender">{isUser ? 'You' : 'ClearPath'}</span>
            </div>

            <div className="message-body">
                {isUser ? (
                    <p>{message.content}</p>
                ) : message.streaming && !message.content ? (
                    <span className="streaming-cursor">▊</span>
                ) : (
                    <>
                        <ReactMarkdown>{message.content}</ReactMarkdown>
                        {message.streaming && <span className="streaming-cursor">▊</span>}
                    </>
                )}
            </div>

            {/* Evaluator flag warning labels */}
            {!isUser && flags.length > 0 && (
                <div className="flag-warnings">
                    {flags.map((flag, i) => (
                        <div key={i} className="flag-warning">
                            {FLAG_LABELS[flag] || `⚠️ Flag: ${flag} — please verify with support.`}
                        </div>
                    ))}
                </div>
            )}

            {/* Metadata tags */}
            {!isUser && message.metadata && (
                <div className="metadata-bar">
                    <span className="meta-tag model">
                        {message.metadata.model_used.split('/').pop()}
                    </span>
                    <span className="meta-tag classification">
                        {message.metadata.classification === 'complex' ? '🧠' : '⚡'}{' '}
                        {message.metadata.classification}
                    </span>
                    <span className="meta-tag time">
                        ⏱ {message.metadata.latency_ms}ms
                    </span>
                    <span className="meta-tag">
                        {message.metadata.chunks_retrieved} chunks
                    </span>
                </div>
            )}

            {/* Sources panel */}
            {!isUser && message.sources && message.sources.length > 0 && (
                <div className="sources-panel">
                    <button
                        className="sources-toggle"
                        onClick={() => setSourcesOpen(!sourcesOpen)}
                    >
                        <span> {message.sources.length} source{message.sources.length > 1 ? 's' : ''}</span>
                        <span className={`arrow ${sourcesOpen ? 'open' : ''}`}>▼</span>
                    </button>
                    {sourcesOpen && (
                        <div className="sources-list">
                            {message.sources.map((src, i) => (
                                <div key={i} className="source-item">
                                    <div className="source-info">
                                        <span className="source-icon"></span>
                                        <span className="source-name">{src.document}</span>
                                        <span className="source-page">p.{src.page}</span>
                                    </div>
                                    <span className="source-score">
                                        {(src.relevance_score * 100).toFixed(0)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

function LoadingIndicator() {
    return (
        <div className="message assistant">
            <div className="message-header">
                <div className="message-avatar assistant">C</div>
                <span className="message-sender">ClearPath</span>
            </div>
            <div className="loading-indicator">
                <div className="loading-dots">
                    <span /><span /><span />
                </div>
                <span>Thinking…</span>
            </div>
        </div>
    )
}
