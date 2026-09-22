import { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import { api } from './api'
import AuthCallback from './components/AuthCallback'
import AuthPage from './components/AuthPage'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import ArtifactPanel from './components/ArtifactPanel'
import TestDashboard from './components/TestDashboard'
import { extractArtifacts } from './lib/artifacts'
import './styles/App.css'

const CHAT_MODES = [
  { id: 'stream', label: 'Stream' },
  { id: 'sync', label: 'Sync' },
  { id: 'async', label: 'Async' },
]

const emptySwarm = () => ({ active: false, nodes: [] })

function upsertNode(nodes, patch) {
  const i = nodes.findIndex((n) => n.id === patch.id)
  if (i === -1) return [...nodes, patch]
  const next = nodes.slice()
  next[i] = { ...next[i], ...patch }
  return next
}

function ChatApp({ user, onLogout }) {
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const [loading, setLoading] = useState(false)
  const [chatMode, setChatMode] = useState('stream')
  const [useSwarm, setUseSwarm] = useState(false)
  const [attachments, setAttachments] = useState([])
  const [uploadStatus, setUploadStatus] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [swarm, setSwarm] = useState(emptySwarm)
  const [artifact, setArtifact] = useState(null)
  const [artifactTab, setArtifactTab] = useState('preview')
  const [artifactExpanded, setArtifactExpanded] = useState(false)

  useEffect(() => {
    Promise.all([api.getModels(), api.getSessions()])
      .then(([modelList, sessionList]) => {
        setModels(modelList)
        setSessions(sessionList)
        const available = modelList.find((m) => m.available)
        if (available) setSelectedModel(available.id)
        else if (modelList.length > 0) setSelectedModel(modelList[0].id)
        if (sessionList.length > 0) setActiveSessionId(sessionList[0].id)
      })
      .catch(console.error)
  }, [])

  useEffect(() => {
    if (!activeSessionId) {
      setMessages([])
      return
    }
    api.getMessages(activeSessionId).then(setMessages).catch(console.error)
  }, [activeSessionId])

  const handleNewChat = useCallback(async () => {
    try {
      const session = await api.createSession('New chat', selectedModel)
      setSessions((prev) => [session, ...prev])
      setActiveSessionId(session.id)
      setMessages([])
      setSwarm(emptySwarm())
      setArtifact(null)
    } catch (err) {
      console.error(err)
    }
  }, [selectedModel])

  const updateAssistant = (assistantId, patch) => {
    setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, ...patch } : m)))
  }

  const openArtifact = (art) => {
    setArtifact(art)
    setArtifactTab(art.previewable ? 'preview' : 'source')
    setArtifactExpanded(false)
  }

  const maybeOpenArtifacts = (text) => {
    const arts = extractArtifacts(text)
    const html = arts.find((a) => a.previewable)
    if (html) openArtifact(html)
    else if (arts[0]) openArtifact(arts[0])
  }

  const chatOptions = () => ({ useSwarm, attachments })

  const handleSendStream = async (sessionId, text, assistantId) => {
    let fullContent = ''
    let toolCalls = []
    let activeTools = []

    await api.chatStream(sessionId, text, selectedModel, (event, data) => {
      if (event === 'token') {
        fullContent += data.content
        updateAssistant(assistantId, { content: fullContent, activeTools })
      } else if (event === 'tool_start') {
        activeTools = [...activeTools, { name: data.name }]
        updateAssistant(assistantId, { activeTools: [...activeTools] })
      } else if (event === 'tool_result') {
        activeTools = activeTools.filter((t) => t.name !== data.name)
        toolCalls = [...toolCalls, data.name]
        updateAssistant(assistantId, { activeTools: [...activeTools], tool_calls_made: [...toolCalls] })
      } else if (event === 'thinking') {
        updateAssistant(assistantId, { content: fullContent || `Thinking (step ${data.iteration})…` })
      } else if (event === 'validating') {
        updateAssistant(assistantId, { content: fullContent || 'Checking the answer…' })
      } else if (event === 'replace') {
        fullContent = data.content || fullContent
        updateAssistant(assistantId, { content: fullContent })
      } else if (event === 'validation') {
        updateAssistant(assistantId, { validation: data })
      } else if (event === 'warning') {
        updateAssistant(assistantId, { content: fullContent + `\n\n*${data.message}*` })
      } else if (event === 'swarm_start') {
        setSwarm({
          active: true,
          nodes: [{ id: 'planner', agent: 'planner', status: 'pending', task: 'Planning' }],
        })
      } else if (event === 'swarm_plan') {
        const extras = (data.subtasks || []).map((s) => ({
          id: s.id,
          agent: s.agent,
          task: s.task,
          status: 'pending',
        }))
        setSwarm((prev) => ({
          active: true,
          nodes: [
            ...upsertNode(prev.nodes, { id: 'planner', agent: 'planner', status: 'done', preview: data.preview }),
            ...extras,
            { id: 'synthesizer', agent: 'synthesizer', status: 'pending', task: 'Merge results' },
          ],
        }))
      } else if (event === 'swarm_agent_start') {
        setSwarm((prev) => ({
          active: true,
          nodes: upsertNode(prev.nodes, { ...data, status: 'running' }),
        }))
      } else if (event === 'swarm_agent_done') {
        setSwarm((prev) => ({
          active: true,
          nodes: upsertNode(prev.nodes, { ...data, status: 'done' }),
        }))
      } else if (event === 'done') {
        toolCalls = data.tool_calls_made || toolCalls
        fullContent = data.content || fullContent
        updateAssistant(assistantId, {
          agents_used: data.agents_used,
          validation: data.validation,
          content: fullContent,
        })
        setSwarm((prev) => ({ ...prev, active: false }))
        maybeOpenArtifacts(fullContent)
      }
    }, chatOptions())

    updateAssistant(assistantId, {
      content: fullContent,
      tool_calls_made: toolCalls,
      activeTools: [],
      streaming: false,
    })
  }

  const handleSendSync = async (sessionId, text, assistantId) => {
    const result = await api.chat(sessionId, text, selectedModel, chatOptions())
    updateAssistant(assistantId, {
      content: result.response,
      tool_calls_made: result.tool_calls_made,
      agents_used: result.agents_used,
      validation: result.validation,
      streaming: false,
    })
    maybeOpenArtifacts(result.response)
  }

  const handleSendAsync = async (sessionId, text, assistantId) => {
    updateAssistant(assistantId, { content: 'Working in the background…' })
    const { task_id } = await api.chatAsync(sessionId, text, selectedModel, chatOptions())
    let status = 'PENDING'
    for (let i = 0; i < 120 && status === 'PENDING'; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      const result = await api.getAsyncTaskStatus(task_id)
      status = result.status
      if (status === 'SUCCESS') {
        const content = result.result?.content || '(empty response)'
        updateAssistant(assistantId, {
          content,
          tool_calls_made: result.result?.tool_calls_made || [],
          streaming: false,
        })
        maybeOpenArtifacts(content)
        return
      }
      if (status === 'FAILURE') throw new Error(result.error || 'Async task failed')
    }
    throw new Error('Async task timed out')
  }

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
    const assistantId = Date.now() + 1
    setMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '', id: assistantId, streaming: true, activeTools: [] },
    ])

    try {
      if (chatMode === 'async') {
        await handleSendAsync(sessionId, text, assistantId)
      } else if (chatMode === 'sync' && !useSwarm) {
        await handleSendSync(sessionId, text, assistantId)
      } else {
        await handleSendStream(sessionId, text, assistantId)
      }

      setSessions((prev) =>
        prev
          .map((s) => (s.id === sessionId ? { ...s, title: text.slice(0, 80), updated_at: new Date().toISOString() } : s))
          .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
      )
    } catch (err) {
      updateAssistant(assistantId, { content: `Error: ${err.message}`, streaming: false, activeTools: [] })
    } finally {
      setLoading(false)
    }
  }, [activeSessionId, selectedModel, chatMode, useSwarm, attachments])

  const handleUpload = async (files) => {
    setUploadStatus('Uploading…')
    try {
      const result = await api.uploadFiles(files)
      setAttachments((prev) => [...prev, ...result.files])
      const indexed = result.indexed?.filter((i) => !i.error).length || 0
      setUploadStatus(indexed ? `Indexed ${indexed} document(s)` : `Uploaded ${result.count} file(s)`)
      setTimeout(() => setUploadStatus(''), 4000)
    } catch (err) {
      setUploadStatus(`Upload failed: ${err.message}`)
    }
  }

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

  const onOpenSwarmNode = (node) => {
    if (!node?.preview) return
    openArtifact({
      id: node.id,
      lang: 'text',
      code: node.preview,
      title: node.agent,
      previewable: false,
    })
  }

  return (
    <div className={`app-layout ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={setActiveSessionId}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        user={user}
        onLogout={onLogout}
      />
      <div className="workspace">
        <div className="main-content">
          <div className="top-bar">
            <button className="icon-btn" type="button" onClick={() => setSidebarOpen((v) => !v)} aria-label="Toggle sidebar">
              ☰
            </button>
            <div className="top-tools">
              <Link to="/test" className="quiet-link">Tests</Link>
              <select className="mode-select" value={chatMode} onChange={(e) => setChatMode(e.target.value)}>
                {CHAT_MODES.map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
            </div>
          </div>
          <ChatArea
            messages={messages}
            onSend={handleSend}
            loading={loading}
            hasSession={!!activeSessionId}
            useSwarm={useSwarm}
            onSwarmChange={setUseSwarm}
            attachments={attachments}
            onUpload={handleUpload}
            uploadStatus={uploadStatus}
            swarm={swarm}
            onOpenArtifact={openArtifact}
            onOpenSwarmNode={onOpenSwarmNode}
          />
        </div>
        {artifact && (
          <ArtifactPanel
            artifact={artifact}
            tab={artifactTab}
            onTab={setArtifactTab}
            expanded={artifactExpanded}
            onExpand={() => setArtifactExpanded((v) => !v)}
            onClose={() => { setArtifact(null); setArtifactExpanded(false) }}
          />
        )}
      </div>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(null)
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

  const handleLogout = () => {
    api.clearToken()
    setUser(null)
  }

  if (initializing) {
    return <div className="loading-screen">Loading…</div>
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth/callback" element={<AuthCallback onAuth={setUser} />} />
        {!user ? (
          <Route path="*" element={<AuthPage onAuth={setUser} />} />
        ) : (
          <>
            <Route path="/" element={<ChatApp user={user} onLogout={handleLogout} />} />
            <Route path="/test" element={<TestDashboard />} />
          </>
        )}
      </Routes>
    </BrowserRouter>
  )
}
