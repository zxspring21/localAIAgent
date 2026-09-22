import './SwarmViz.css'

const LABELS = {
  planner: 'Planner',
  researcher: 'Researcher',
  analyst: 'Analyst',
  executor: 'Executor',
  synthesizer: 'Synthesizer',
}

function layout(nodes) {
  const planner = nodes.filter((n) => n.agent === 'planner')
  const synth = nodes.filter((n) => n.agent === 'synthesizer')
  const mids = nodes.filter((n) => n.agent !== 'planner' && n.agent !== 'synthesizer')
  const w = 560
  const h = 220
  const placed = []
  planner.forEach((n) => placed.push({ ...n, x: w / 2, y: 36 }))
  const gap = mids.length > 1 ? Math.min(140, (w - 80) / (mids.length - 1 || 1)) : 0
  const start = mids.length ? w / 2 - ((mids.length - 1) * gap) / 2 : w / 2
  mids.forEach((n, i) => placed.push({ ...n, x: start + i * gap, y: 118 }))
  synth.forEach((n) => placed.push({ ...n, x: w / 2, y: 196 }))
  return { placed, w, h }
}

export default function SwarmViz({ swarm, onOpenNode }) {
  if (!swarm?.nodes?.length) return null
  const { placed, w, h } = layout(swarm.nodes)
  const planner = placed.find((n) => n.agent === 'planner')
  const synth = placed.find((n) => n.agent === 'synthesizer')
  const mids = placed.filter((n) => n.agent !== 'planner' && n.agent !== 'synthesizer')
  const running = swarm.active

  return (
    <section className="swarm-viz" aria-label="Agent swarm">
      <div className="swarm-head">
        <span className={`swarm-pulse ${running ? 'on' : ''}`} />
        {running ? 'Swarm running' : 'Swarm'}
        <span className="swarm-count">{placed.length} agents</span>
      </div>
      <svg className="swarm-svg" viewBox={`0 0 ${w} ${h}`} role="img">
        {planner && mids.map((n) => (
          <path
            key={`p-${n.id}`}
            className={`swarm-link ${n.status}`}
            d={`M ${planner.x} ${planner.y + 18} C ${planner.x} ${planner.y + 56}, ${n.x} ${n.y - 56}, ${n.x} ${n.y - 22}`}
            fill="none"
          />
        ))}
        {synth && mids.map((n) => (
          <path
            key={`s-${n.id}`}
            className={`swarm-link ${synth.status}`}
            d={`M ${n.x} ${n.y + 22} C ${n.x} ${n.y + 56}, ${synth.x} ${synth.y - 56}, ${synth.x} ${synth.y - 18}`}
            fill="none"
          />
        ))}
        {placed.map((n) => (
          <g key={n.id} className={`swarm-g ${n.status}`} onClick={() => onOpenNode?.(n)} style={{ cursor: n.preview ? 'pointer' : 'default' }}>
            <circle className="swarm-ring" cx={n.x} cy={n.y} r="20" />
            <circle className="swarm-core" cx={n.x} cy={n.y} r="7" />
            <text x={n.x} y={n.y + 36} textAnchor="middle" className="swarm-label">
              {LABELS[n.agent] || n.agent}
            </text>
          </g>
        ))}
      </svg>
      <div className="swarm-tasks">
        {placed.filter((n) => n.task).map((n) => (
          <button key={n.id} type="button" className={`swarm-task-chip ${n.status}`} onClick={() => onOpenNode?.(n)}>
            <strong>{LABELS[n.agent] || n.agent}</strong>
            <span>{n.task}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
