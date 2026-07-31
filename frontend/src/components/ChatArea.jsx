import { useState, useRef, useEffect } from 'react'
import MessageBubble, { TypingIndicator } from './MessageBubble'
import './ChatArea.css'

export default function ChatArea({ messages, onSend, loading, hasSession }) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || loading || !hasSession) return
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

  return (
    <main className="chat-area">
      <div className="messages-container">
        {!hasSession && (
          <div className="welcome">
            <div className="welcome-icon">
              <svg width="48" height="48" viewBox="0 0 32 32" fill="none">
                <rect width="32" height="32" rx="8" fill="#d97757" />
                <path d="M8 16L14 10L18 14L24 8" stroke="white" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
            <h2>LocalAI Agent</h2>
            <p>Multi-Agent system with vLLM inference, Chain-of-Thought reasoning, and skill execution.</p>
            <div className="welcome-hints">
              <button onClick={() => onSend('What skills do you have available?')}>
                What skills do you have?
              </button>
              <button onClick={() => onSend('List the files in the current directory')}>
                List directory files
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
            activeTools={msg.activeTools}
            streaming={msg.streaming}
          />
        ))}

        {loading && messages.every((m) => !m.streaming) && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        <form onSubmit={handleSubmit} className="input-form">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={hasSession ? 'Message LocalAI Agent...' : 'Start a new chat to begin...'}
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
