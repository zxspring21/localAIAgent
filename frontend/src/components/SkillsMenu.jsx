import { useEffect, useRef, useState } from 'react'
import './SkillsMenu.css'

export default function SkillsMenu({ skills, onPick }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  if (!skills?.length) return null

  return (
    <div className="skills-menu" ref={ref}>
      <button type="button" className="feature-btn" onClick={() => setOpen((v) => !v)}>
        Skills
      </button>
      {open && (
        <div className="skills-pop">
          <p className="skills-pop-title">Anthropic skills</p>
          <ul>
            {skills.map((s) => (
              <li key={s.name}>
                <button
                  type="button"
                  onClick={() => {
                    onPick(s)
                    setOpen(false)
                  }}
                >
                  <strong>{s.name}</strong>
                  <span>{s.description}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
