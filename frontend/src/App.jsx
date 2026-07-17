import { useState, useEffect, useCallback } from 'react'
import { api } from './api'
import AuthPage from './components/AuthPage'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import './styles/App.css'

export default function App() {
  const [user, setUser] = useState(null)
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const [loading, setLoading] = useState(false)
  const [initializing, setInitializing] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      api.getMe()
        .then(setUser)
        .catch(() => api.clearToken())
        .finally(() => setInitializing(false))
    } else {
      setInitializing(false)
    }
  }, [])

  useEffect(() => {
    if (!user) return
    Promise.all([api.getModels(), api.getSessions()])
      .then(([modelList, sessionList]) => {
        setModels(modelList)
        setSessions(sessionList)
        if (modelList.length > 0) setSelectedModel(modelList[0].id)
        if (sessionList.length > 0) {
          setActiveSessionId(sessionList[0].id)
        }
      })
      .catch(console.error)
  }, [user])

  useEffect(() => {
    if (!activeSessionId) {
      setMessages([])
      return
    }
    api.getMessages(activeSessionId)
      .then(setMessages)
      .catch(console.error)
  }, [activeSessionId])

  const handleNewChat = useCallback(async () => {
    try {
      const session = await api.createSession('New Chat', selectedModel)
      setSessions((prev) => [session, ...prev])
      setActiveSessionId(session.id)
      setMessages([])
    } catch (err) {
      console.error(err)
    }
  }, [selectedModel])

  const handleSend = useCallback(async (text) => {
    let sessionId = activeSessionId

    if (!sessionId) {
      try {
        const session = await api.createSession(text.slice(0, 80), selectedModel)
        setSessions((prev) => [session, ...prev])
        sessionId = session.id
        setActiveSessionId(sessionId)
      } catch (err) {
        console.error(err)
        return
      }
    }

    const userMsg = { role: 'user', content: text, id: Date.now() }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    try {
      const result = await api.chat(sessionId, text, selectedModel)
      const assistantMsg = {
        role: 'assistant',
        content: result.response,
        tool_calls_made: result.tool_calls_made,
        id: Date.now() + 1,
      }
      setMessages((prev) => [...prev, assistantMsg])

      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId ? { ...s, title: text.slice(0, 80), updated_at: new Date().toISOString() } : s
        ).sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
      )
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${err.message}`, id: Date.now() + 1 },
      ])
    } finally {
      setLoading(false)
    }
  }, [activeSessionId, selectedModel])

  const handleDeleteSession = async (sessionId) => {
    try {
      await api.deleteSession(sessionId)
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
      if (activeSessionId === sessionId) {
        setActiveSessionId(null)
        setMessages([])
      }
    } catch (err) {
      console.error(err)
    }
  }

  const handleLogout = () => {
    api.clearToken()
    setUser(null)
    setSessions([])
    setActiveSessionId(null)
    setMessages([])
  }

  if (initializing) {
    return <div className="loading-screen">Loading...</div>
  }

  if (!user) {
    return <AuthPage onAuth={setUser} />
  }

  return (
    <div className="app-layout">
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={setActiveSessionId}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        models={models}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        user={user}
        onLogout={handleLogout}
      />
      <ChatArea
        messages={messages}
        onSend={handleSend}
        loading={loading}
        hasSession={!!activeSessionId}
      />
    </div>
  )
}
