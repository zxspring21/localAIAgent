import { useMemo } from 'react'
import './Sidebar.css'

function groupModels(models) {
  const groups = {}
  for (const m of models) {
    const key = m.provider || 'Other'
    if (!groups[key]) groups[key] = []
    groups[key].push(m)
  }
  return groups
}

export default function Sidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  models,
  selectedModel,
  onModelChange,
  user,
  onLogout,
}) {
  const grouped = useMemo(() => groupModels(models), [models])
  const selected = models.find((m) => m.id === selectedModel)

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <button className="new-chat-btn" onClick={onNewChat}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 1.5a5.5 5.5 0 110 11 5.5 5.5 0 010-11zM7.25 5v2.25H5v1.5h2.25V11h1.5V8.75H11v-1.5H8.75V5h-1.5z" />
          </svg>
          New Chat
        </button>
      </div>

      <div className="model-selector">
        <label>Model</label>
        <select value={selectedModel} onChange={(e) => onModelChange(e.target.value)}>
          {Object.entries(grouped).map(([provider, items]) => (
            <optgroup key={provider} label={provider}>
              {items.map((m) => (
                <option key={m.id} value={m.id} disabled={!m.available}>
                  {m.name}{m.tier === 'paid' ? ' · paid' : ''}{!m.available ? ' (unavailable)' : ''}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {selected?.description && (
          <p className="model-hint">{selected.description}</p>
        )}
      </div>

      <div className="session-list">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`session-item ${s.id === activeSessionId ? 'active' : ''}`}
            onClick={() => onSelectSession(s.id)}
          >
            <span className="session-title">{s.title || 'New Chat'}</span>
            <button
              className="session-delete"
              onClick={(e) => { e.stopPropagation(); onDeleteSession(s.id) }}
              title="Delete"
            >
              ×
            </button>
          </div>
        ))}
        {sessions.length === 0 && (
          <p className="no-sessions">No conversations yet</p>
        )}
      </div>

      <div className="sidebar-footer">
        <div className="user-info">
          <div className="user-avatar">{user?.username?.[0]?.toUpperCase() || 'U'}</div>
          <span>{user?.username}</span>
        </div>
        <button className="logout-btn" onClick={onLogout} title="Sign out">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
          </svg>
        </button>
      </div>
    </aside>
  )
}
