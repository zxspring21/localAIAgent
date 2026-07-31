const API_BASE = import.meta.env.VITE_API_URL || ''

class ApiClient {
  constructor() {
    this.token = localStorage.getItem('token') || ''
  }

  setToken(token) {
    this.token = token
    localStorage.setItem('token', token)
  }

  clearToken() {
    this.token = ''
    localStorage.removeItem('token')
  }

  headers(extra = {}) {
    const h = { 'Content-Type': 'application/json', ...extra }
    if (this.token) h['Authorization'] = `Bearer ${this.token}`
    return h
  }

  async request(path, options = {}) {
    const res = await fetch(`${API_BASE}/api/v1${path}`, {
      ...options,
      headers: this.headers(options.headers),
    })

    if (res.status === 401) {
      this.clearToken()
      throw new Error('Unauthorized')
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Request failed: ${res.status}`)
    }

    return res.json()
  }

  register(username, password, email) {
    return this.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password, email }),
    })
  }

  login(username, password) {
    return this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  }

  getMe() {
    return this.request('/auth/me')
  }

  getModels() {
    return this.request('/models')
  }

  getSessions() {
    return this.request('/sessions')
  }

  createSession(title, modelName) {
    return this.request('/sessions', {
      method: 'POST',
      body: JSON.stringify({ title, model_name: modelName }),
    })
  }

  getMessages(sessionId) {
    return this.request(`/sessions/${sessionId}/messages`)
  }

  deleteSession(sessionId) {
    return this.request(`/sessions/${sessionId}`, { method: 'DELETE' })
  }

  chat(sessionId, message, modelName) {
    return this.request('/chat', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, message, model_name: modelName }),
    })
  }

  chatAsync(sessionId, message, modelName) {
    return this.request('/chat/async', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, message, model_name: modelName }),
    })
  }

  getAsyncTaskStatus(taskId) {
    return this.request(`/chat/async/${taskId}`)
  }

  executeSkillAsync(skillName, args = {}) {
    return this.request('/skills/execute-async', {
      method: 'POST',
      body: JSON.stringify({ skill_name: skillName, args }),
    })
  }

  getSkillTaskStatus(taskId) {
    return this.request(`/skills/execute-async/${taskId}`)
  }

  getSkills() {
    return this.request('/skills')
  }

  getTestOverview() {
    return this.request('/tests/overview')
  }

  runTest(name) {
    return this.request(`/tests/${name}`)
  }

  async chatStream(sessionId, message, modelName, onEvent) {
    const res = await fetch(`${API_BASE}/api/v1/chat/stream`, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify({ session_id: sessionId, message, model_name: modelName }),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Stream failed: ${res.status}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finalData = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''

      for (const part of parts) {
        if (!part.trim()) continue
        let event = 'message'
        let data = {}
        for (const line of part.split('\n')) {
          if (line.startsWith('event: ')) event = line.slice(7)
          if (line.startsWith('data: ')) {
            try { data = JSON.parse(line.slice(6)) } catch { data = { raw: line.slice(6) } }
          }
        }
        if (onEvent) onEvent(event, data)
        if (event === 'done') finalData = data
        if (event === 'error') throw new Error(data.message || 'Stream error')
      }
    }

    return finalData
  }
}

export const api = new ApiClient()
