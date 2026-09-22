import { useState, useRef, useEffect } from 'react'
import MessageBubble, { TypingIndicator } from './MessageBubble'
import SwarmViz from './SwarmViz'
import SkillsMenu from './SkillsMenu'
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
  swarm,
  skills,
  onOpenArtifact,
  onOpenSwarmNode,
}) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, swarm])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || loading) return
    onSend(input.trim())
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
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

  const empty = messages.length === 0

  const composer = (
    <div className="input-area">
      {(swarm?.active || swarm?.nodes?.length > 0) && (
        <SwarmViz swarm={swarm} onOpenNode={onOpenSwarmNode} />
      )}
      <div className="composer">
        <div className="feature-bar">
          <button type="button" className="feature-btn" onClick={() => fileInputRef.current?.click()} disabled={loading}>
            +
          </button>
          <label className={`chip-toggle ${useSwarm ? 'on' : ''}`}>
            <input type="checkbox" checked={useSwarm} onChange={(e) => onSwarmChange(e.target.checked)} />
            Swarm
          </label>
          <SkillsMenu
            skills={skills}
            onPick={(s) => setInput((prev) => (prev ? `${prev} ` : '') + `Use the ${s.name} skill: `)}
          />
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".txt,.md,.json,.csv,.py,.js,.ts,.html,.xml,.yaml,.yml"
            hidden
            onChange={handleFileChange}
          />
          {attachments.length > 0 && <span className="attachment-count">{attachments.length} attached</span>}
          {uploadStatus && <span className="upload-status">{uploadStatus}</span>}
        </div>
        <form onSubmit={handleSubmit} className="input-form">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={empty ? 'How can I help you today?' : 'Reply…'}
            rows={1}
            disabled={loading}
          />
          <button type="submit" className="send-btn" disabled={!input.trim() || loading} aria-label="Send">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 4l8 8h-5v8h-6v-8H4z" />
            </svg>
          </button>
        </form>
      </div>
      <p className="input-hint">Claude can make mistakes. Open Preview or Source on generated files.</p>
    </div>
  )

  return (
    <main className={`chat-area ${empty ? 'is-empty' : ''}`}>
      {empty ? (
        <div className="welcome-wrap">
          <div className="welcome">
            <h2>How can I help you today?</h2>
          </div>
          {composer}
        </div>
      ) : (
        <>
          <div className="messages-container">
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
                onOpenArtifact={onOpenArtifact}
              />
            ))}
            {loading && messages.every((m) => !m.streaming) && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>
          {composer}
        </>
      )}
    </main>
  )
}
