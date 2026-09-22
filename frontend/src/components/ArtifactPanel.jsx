import { htmlPreviewSrc } from '../lib/artifacts'
import './ArtifactPanel.css'

export default function ArtifactPanel({ artifact, tab, onTab, expanded, onExpand, onClose }) {
  if (!artifact) return null

  return (
    <aside className={`artifact-panel ${expanded ? 'expanded' : ''}`}>
      <header className="artifact-bar">
        <div className="artifact-meta">
          <span className="artifact-title">{artifact.title || artifact.lang}</span>
        </div>
        <div className="artifact-tabs">
          {artifact.previewable && (
            <button type="button" className={tab === 'preview' ? 'on' : ''} onClick={() => onTab('preview')}>
              Preview
            </button>
          )}
          <button type="button" className={tab === 'source' ? 'on' : ''} onClick={() => onTab('source')}>
            Source
          </button>
        </div>
        <div className="artifact-actions">
          <button type="button" onClick={onExpand} title={expanded ? 'Collapse' : 'Expand'}>
            {expanded ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 9H4V4M15 9h5V4M9 15H4v5M15 15h5v5" /></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" /></svg>
            )}
          </button>
          <button type="button" onClick={onClose} title="Close">×</button>
        </div>
      </header>
      <div className="artifact-body">
        {tab === 'preview' && artifact.previewable ? (
          <iframe
            title="artifact-preview"
            sandbox="allow-scripts"
            srcDoc={htmlPreviewSrc(artifact.code)}
          />
        ) : (
          <pre className="artifact-source"><code>{artifact.code}</code></pre>
        )}
      </div>
    </aside>
  )
}
