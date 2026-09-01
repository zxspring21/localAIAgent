import * as SecureStore from 'expo-secure-store'
import Constants from 'expo-constants'

const API_URL =
  process.env.EXPO_PUBLIC_API_URL ||
  Constants.expoConfig?.extra?.apiUrl ||
  'http://localhost:8080'

export async function getToken() {
  return SecureStore.getItemAsync('token')
}

export async function setToken(token) {
  if (token) await SecureStore.setItemAsync('token', token)
  else await SecureStore.deleteItemAsync('token')
}

async function request(path, options = {}) {
  const token = await getToken()
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${API_URL}/api/v1${path}`, { ...options, headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

export const api = {
  login: (username, password) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  register: (username, password, email) =>
    request('/auth/register', { method: 'POST', body: JSON.stringify({ username, password, email }) }),
  loginGoogle: (idToken) =>
    request('/auth/oauth/google', { method: 'POST', body: JSON.stringify({ id_token: idToken }) }),
  loginApple: (idToken) =>
    request('/auth/oauth/apple', { method: 'POST', body: JSON.stringify({ id_token: idToken }) }),
  getMe: () => request('/auth/me'),
  getSessions: () => request('/sessions'),
  createSession: (title, modelName) =>
    request('/sessions', { method: 'POST', body: JSON.stringify({ title, model_name: modelName }) }),
  chat: (sessionId, message, modelName) =>
    request('/chat', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, message, model_name: modelName }),
    }),
}
