import { useState, useRef, useEffect } from 'react'
import MessageBubble, { TypingIndicator } from './MessageBubble'
import './ChatArea.css'

export default function ChatArea({
  messages,
  onSend,
  loading,
  hasSession,
  useSwarm,
  onSwarmChange,
  attachments,
  onUpload,
  uploadStatus,
}) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || loading) return
    onSend(input.trim())
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const handleInput = (e) => {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px'
  }

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length && onUpload) onUpload(files)
    e.target.value = ''
  }

  return (
    <main className="chat-area">
      <div className="messages-container">
        {!hasSession && messages.length === 0 && (
          <div className="welcome">
            <div className="welcome-icon">
              <svg width="48" height="48" viewBox="0 0 32 32" fill="none">
                <rect width="32" height="32" rx="8" fill="#d97757" />
                <path d="M8 16L14 10L18 14L24 8" stroke="white" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
            <h2>LocalAI Agent</h2>
            <p>Multi-agent system with MLX inference, RAG, memory, MCP tools, and swarm orchestration.</p>
            <div className="welcome-hints">
              <button onClick={() => onSend('What skills do you have available?')}>
                What skills do you have?
              </button>
              <button onClick={() => onSend('Search the web for latest AI agent frameworks')}>
                Web search demo
              </button>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble
            key={msg.id || i}
            role={msg.role}
            content={msg.content}
            toolCalls={msg.tool_calls_made}
            agentsUsed={msg.agents_used}
            validation={msg.validation}
            activeTools={msg.activeTools}
            streaming={msg.streaming}
          />
        ))}

        {loading && messages.every((m) => !m.streaming) && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        <div className="feature-bar">
          <label className="feature-toggle" title="Multi-agent swarm (planner → sub-agents → synthesizer)">
            <input
              type="checkbox"
              checked={useSwarm}
              onChange={(e) => onSwarmChange(e.target.checked)}
            />
            Swarm
          </label>
          <button
            type="button"
            className="feature-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
            title="Upload documents for RAG"
          >
            Attach
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".txt,.md,.json,.csv,.py,.js,.ts,.html,.xml,.yaml,.yml"
            hidden
            onChange={handleFileChange}
          />
          {attachments.length > 0 && (
            <span className="attachment-count">{attachments.length} file(s)</span>
          )}
          {uploadStatus && <span className="upload-status">{uploadStatus}</span>}
        </div>

        <form onSubmit={handleSubmit} className="input-form">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Message LocalAI Agent..."
            rows={1}
            disabled={loading}
          />
          <button type="submit" className="send-btn" disabled={!input.trim() || loading}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        </form>
        <p className="input-hint">LocalAI Agent can make mistakes. Verify important information.</p>
      </div>
    </main>
  )
}
