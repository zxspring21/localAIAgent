import ReactMarkdown from 'react-markdown'
import { extractArtifacts } from '../lib/artifacts'
import './MessageBubble.css'

export default function MessageBubble({
  role,
  content,
  toolCalls,
  agentsUsed,
  validation,
  activeTools,
  streaming,
  onOpenArtifact,
}) {
  const isUser = role === 'user'
  const artifacts = !isUser ? extractArtifacts(content) : []

  return (
    <div className={`message-row ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-content">
        <div className="markdown-body">
          {content ? (
            <ReactMarkdown>{content}</ReactMarkdown>
          ) : streaming ? (
            <span className="streaming-placeholder">Thinking…</span>
          ) : null}
        </div>
        {artifacts.map((art) => (
          <button
            key={art.id}
            type="button"
            className="artifact-chip"
            onClick={() => onOpenArtifact?.(art)}
          >
            {art.previewable ? 'Preview / Source' : 'Source'} · {art.lang}
          </button>
        ))}
        {agentsUsed?.length > 0 && (
          <div className="tool-calls">
            <span className="tool-label">Agents</span>
            {agentsUsed.map((a, i) => (
              <span key={i} className="tool-badge">{a}</span>
            ))}
          </div>
        )}
        {validation?.issues?.length > 0 && (
          <div className="tool-calls">
            <span className="tool-label">Checked</span>
            {(validation.sources_used || []).map((s, i) => (
              <span key={i} className="tool-badge">{s}</span>
            ))}
          </div>
        )}
        {toolCalls?.length > 0 && (
          <div className="tool-calls">
            <span className="tool-label">Tools</span>
            {toolCalls.map((t, i) => (
              <span key={i} className="tool-badge">{typeof t === 'string' ? t : t.name || t}</span>
            ))}
          </div>
        )}
        {activeTools?.length > 0 && (
          <div className="tool-calls">
            <span className="tool-label">Running</span>
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
      <div className="message-content">
        <div className="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
  )
}
