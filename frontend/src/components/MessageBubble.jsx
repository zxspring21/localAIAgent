import ReactMarkdown from 'react-markdown'
import './MessageBubble.css'

export default function MessageBubble({ role, content, toolCalls, activeTools, streaming }) {
  const isUser = role === 'user'

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-avatar">
        {isUser ? (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
          </svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 32 32" fill="none">
            <rect width="32" height="32" rx="8" fill="#d97757" />
            <path d="M8 16L14 10L18 14L24 8" stroke="white" strokeWidth="2" strokeLinecap="round" />
          </svg>
        )}
      </div>
      <div className="message-content">
        <div className="message-role">{isUser ? 'You' : 'Assistant'}</div>
        <div className="markdown-body">
          {content ? (
            <ReactMarkdown>{content}</ReactMarkdown>
          ) : streaming ? (
            <span className="streaming-placeholder">Thinking...</span>
          ) : null}
        </div>
        {toolCalls && toolCalls.length > 0 && (
          <div className="tool-calls">
            <span className="tool-label">Tools used:</span>
            {toolCalls.map((t, i) => (
              <span key={i} className="tool-badge">{typeof t === 'string' ? t : t.name || t}</span>
            ))}
          </div>
        )}
        {activeTools && activeTools.length > 0 && (
          <div className="tool-calls active">
            <span className="tool-label">Running:</span>
            {activeTools.map((t, i) => (
              <span key={i} className="tool-badge running">{t.name || t}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function TypingIndicator() {
  return (
    <div className="message-row assistant">
      <div className="message-avatar">
        <svg width="20" height="20" viewBox="0 0 32 32" fill="none">
          <rect width="32" height="32" rx="8" fill="#d97757" />
        </svg>
      </div>
      <div className="message-content">
        <div className="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
  )
}
