export function extractArtifacts(markdown) {
  if (!markdown) return []
  const artifacts = []
  const re = /```([a-zA-Z0-9_-]+)?\n([\s\S]*?)```/g
  let match
  let i = 0
  while ((match = re.exec(markdown)) !== null) {
    const lang = (match[1] || 'text').toLowerCase()
    const code = match[2].trim()
    if (code.length < 12) continue
    const previewable = ['html', 'htm', 'svg'].includes(lang) || /^\s*<(!doctype|html|svg)/i.test(code)
    artifacts.push({
      id: `art-${i++}`,
      lang,
      code,
      title: previewable ? 'Artifact' : lang.toUpperCase(),
      previewable,
    })
  }
  return artifacts
}

export function htmlPreviewSrc(code) {
  if (/<html/i.test(code) || /<!doctype/i.test(code)) return code
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{font-family:system-ui,sans-serif;margin:16px;}</style></head><body>${code}</body></html>`
}
