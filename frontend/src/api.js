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

  async request(path, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    }
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`
    }

    const res = await fetch(`${API_BASE}/api/v1${path}`, { ...options, headers })

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

  getSkills() {
    return this.request('/skills')
  }
}

export const api = new ApiClient()
