import './Sidebar.css'

export default function Sidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  user,
  onLogout,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="brand">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="11" fill="#d97757" />
            <path d="M7 13.5c2.2-3.2 4-4.8 5-4.8s2.8 1.6 5 4.8" stroke="#fff" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          </svg>
          LocalAI
        </div>
        <button className="new-chat-btn" onClick={onNewChat} type="button">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M8 3v10M3 8h10" />
          </svg>
          New chat
        </button>
      </div>

      <div className="session-label">Recents</div>
      <div className="session-list">
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`session-item ${s.id === activeSessionId ? 'active' : ''}`}
            onClick={() => onSelectSession(s.id)}
          >
            <span className="session-title">{s.title || 'New chat'}</span>
            <button
              className="session-delete"
              onClick={(e) => { e.stopPropagation(); onDeleteSession(s.id) }}
              title="Delete"
              type="button"
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
        <button className="logout-btn" onClick={onLogout} title="Sign out" type="button">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
          </svg>
        </button>
      </div>
    </aside>
  )
}
