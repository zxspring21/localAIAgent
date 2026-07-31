import { useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import './TestDashboard.css'

const INDIVIDUAL_TESTS = [
  { key: 'vllm', label: 'vLLM Connection', module: 'vLLM Backend' },
  { key: 'postgres', label: 'PostgreSQL', module: 'Memory & Auth' },
  { key: 'redis', label: 'Redis ST Memory', module: 'Short-Term Memory' },
  { key: 'qdrant', label: 'Qdrant LT Memory', module: 'Vector DB' },
  { key: 'skills', label: 'Skill Registry', module: 'Agents & Skills' },
  { key: 'web-search', label: 'Web Search API', module: 'Tavily / DuckDuckGo' },
  { key: 'celery', label: 'Celery Async', module: 'Automation' },
  { key: 'auth', label: 'JWT Auth', module: 'Multi-User Auth' },
  { key: 'multi-session', label: 'Multi-Session', module: 'Session Isolation' },
  { key: 'memory-st', label: 'ST Memory R/W', module: 'Redis' },
  { key: 'memory-lt', label: 'LT Memory R/W', module: 'PG + Qdrant' },
  { key: 'automation', label: 'APScheduler', module: 'Automation' },
  { key: 'cot-loop', label: 'CoT Loop', module: 'Brain / Controller' },
]

export default function TestDashboard() {
  const [suite, setSuite] = useState(null)
  const [individual, setIndividual] = useState({})
  const [loading, setLoading] = useState(false)
  const [runningKey, setRunningKey] = useState(null)
  const [sseLog, setSseLog] = useState([])
  const [sseRunning, setSseRunning] = useState(false)
  const [asyncResult, setAsyncResult] = useState(null)

  const runAll = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getTestOverview()
      setSuite(data)
    } catch (err) {
      setSuite({ total: 0, passed: 0, failed: 1, results: [{ name: 'Error', module: 'System', status: 'fail', message: err.message, details: {} }] })
    } finally {
      setLoading(false)
    }
  }, [])

  const runOne = async (key) => {
    setRunningKey(key)
    try {
      const result = await api.runTest(key)
      setIndividual((prev) => ({ ...prev, [key]: result }))
    } catch (err) {
      setIndividual((prev) => ({ ...prev, [key]: { name: key, status: 'fail', message: err.message, module: '', details: {} } }))
    } finally {
      setRunningKey(null)
    }
  }

  const testSSE = async () => {
    setSseRunning(true)
    setSseLog([])
    const log = (msg) => setSseLog((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`])

    try {
      const models = await api.getModels()
      const model = models[0]?.id || ''
      const session = await api.createSession('SSE Test', model)
      log(`Session created: ${session.id}`)

      await api.chatStream(session.id, 'Say hello in one sentence.', model, (event, data) => {
        if (event === 'token') log(`token: "${data.content}"`)
        else if (event === 'tool_start') log(`tool_start: ${data.name}`)
        else if (event === 'tool_result') log(`tool_result: ${data.name}`)
        else if (event === 'thinking') log(`thinking iteration ${data.iteration}`)
        else if (event === 'done') log(`done — tools: ${(data.tool_calls_made || []).join(', ') || 'none'}`)
        else log(`${event}: ${JSON.stringify(data).slice(0, 120)}`)
      })

      log('SSE stream completed successfully')
      await api.deleteSession(session.id)
    } catch (err) {
      log(`SSE ERROR: ${err.message}`)
    } finally {
      setSseRunning(false)
    }
  }

  const testAsync = async () => {
    setAsyncResult(null)
    try {
      const models = await api.getModels()
      const model = models[0]?.id || ''
      const session = await api.createSession('Async Test', model)
      const { task_id } = await api.chatAsync(session.id, 'Reply with the word ASYNC_OK only.', model)

      let status = 'PENDING'
      let attempts = 0
      while (status === 'PENDING' && attempts < 60) {
        await new Promise((r) => setTimeout(r, 2000))
        const result = await api.getAsyncTaskStatus(task_id)
        status = result.status
        if (status === 'SUCCESS' || status === 'FAILURE') {
          setAsyncResult(result)
          break
        }
        attempts++
      }
      await api.deleteSession(session.id)
    } catch (err) {
      setAsyncResult({ status: 'FAILURE', error: err.message })
    }
  }

  const getStatus = (key) => {
    if (individual[key]) return individual[key].status
    if (suite?.results) {
      const match = suite.results.find((r) =>
        INDIVIDUAL_TESTS.find((t) => t.key === key && r.name.toLowerCase().includes(t.label.toLowerCase().split(' ')[0].toLowerCase()))
      )
      return match?.status
    }
    return null
  }

  return (
    <div className="test-dashboard">
      <header className="test-header">
        <div>
          <Link to="/" className="back-link">← Back to Chat</Link>
          <h1>System Test Dashboard</h1>
          <p>Independent functionality tests for each module</p>
        </div>
        <button className="run-all-btn" onClick={runAll} disabled={loading}>
          {loading ? 'Running all tests...' : 'Run All Tests'}
        </button>
      </header>

      {suite?.ports && (
        <div className="ports-info">
          <h3>Service Ports</h3>
          <div className="ports-grid">
            <div className="port-card highlight">
              <strong>Frontend UI</strong>
              <a href={suite.ports.frontend_ui} target="_blank" rel="noreferrer">{suite.ports.frontend_ui}</a>
              <span className="port-note">← Open this for the chat UI</span>
            </div>
            <div className="port-card">
              <strong>Backend API</strong>
              <span>{suite.ports.backend_api}</span>
            </div>
            <div className="port-card warn">
              <strong>vLLM Inference</strong>
              <span>{suite.ports.vllm_inference}</span>
              <span className="port-note">No web UI — LLM API only</span>
            </div>
          </div>
          <p className="ports-note">{suite.ports.note}</p>
        </div>
      )}

      {suite && (
        <div className="suite-summary">
          <span className={`summary-badge ${suite.failed === 0 ? 'all-pass' : ''}`}>
            {suite.passed}/{suite.total} passed
          </span>
          {suite.failed > 0 && <span className="summary-fail">{suite.failed} failed</span>}
        </div>
      )}

      <section className="test-grid">
        {INDIVIDUAL_TESTS.map((test) => {
          const status = getStatus(test.key)
          const result = individual[test.key] || suite?.results?.find((r) =>
            r.name.toLowerCase().includes(test.label.toLowerCase().split(' ')[0])
          )
          return (
            <div key={test.key} className={`test-card ${status || ''}`}>
              <div className="test-card-header">
                <span className={`status-dot ${status || 'unknown'}`} />
                <div>
                  <h3>{test.label}</h3>
                  <span className="test-module">{test.module}</span>
                </div>
              </div>
              {result && (
                <div className="test-result">
                  <p className={result.status}>{result.message}</p>
                  {result.details && Object.keys(result.details).length > 0 && (
                    <details>
                      <summary>Details</summary>
                      <pre>{JSON.stringify(result.details, null, 2)}</pre>
                    </details>
                  )}
                </div>
              )}
              <button
                className="test-run-btn"
                onClick={() => runOne(test.key)}
                disabled={runningKey === test.key}
              >
                {runningKey === test.key ? 'Running...' : 'Run Test'}
              </button>
            </div>
          )
        })}
      </section>

      <section className="integration-tests">
        <h2>Integration Tests</h2>
        <div className="integration-grid">
          <div className="integration-card">
            <h3>SSE Streaming</h3>
            <p>Test /chat/stream endpoint with real-time token events</p>
            <button onClick={testSSE} disabled={sseRunning}>
              {sseRunning ? 'Streaming...' : 'Test SSE Stream'}
            </button>
            {sseLog.length > 0 && (
              <pre className="sse-log">{sseLog.join('\n')}</pre>
            )}
          </div>
          <div className="integration-card">
            <h3>Celery Async Chat</h3>
            <p>Test /chat/async background processing via Celery worker</p>
            <button onClick={testAsync}>Test Async Chat</button>
            {asyncResult && (
              <pre className="async-result">{JSON.stringify(asyncResult, null, 2)}</pre>
            )}
          </div>
          <div className="integration-card">
            <h3>Async Web Search (Celery)</h3>
            <p>Execute web_search skill via Celery worker</p>
            <button onClick={async () => {
              setAsyncResult(null)
              try {
                const { task_id } = await api.executeSkillAsync('web_search', { query: 'LocalAI agent frameworks 2026' })
                let status = 'PENDING'
                for (let i = 0; i < 30 && status === 'PENDING'; i++) {
                  await new Promise((r) => setTimeout(r, 1500))
                  const result = await api.getSkillTaskStatus(task_id)
                  status = result.status
                  if (status === 'SUCCESS' || status === 'FAILURE') {
                    setAsyncResult(result)
                    break
                  }
                }
              } catch (err) {
                setAsyncResult({ status: 'FAILURE', error: err.message })
              }
            }}>Test Async Web Search</button>
          </div>
        </div>
      </section>

      <section className="architecture-map">
        <h2>Architecture Verification</h2>
        <table>
          <thead>
            <tr><th>Feature</th><th>Implementation</th><th>Test</th></tr>
          </thead>
          <tbody>
            <tr><td>vLLM</td><td>CoreController → OpenAI client → localhost:8000/v1</td><td>vLLM Connection</td></tr>
            <tr><td>Claude GitHub Skills</td><td>SKILL_REGISTRY + run_github_code</td><td>Skill Registry</td></tr>
            <tr><td>Multi-Agent / CoT</td><td>CoreController tool call loop</td><td>CoT Loop</td></tr>
            <tr><td>Claude UI</td><td>React frontend (port 3000)</td><td>Manual</td></tr>
            <tr><td>Multi-Models</td><td>/chat model_name param → vLLM</td><td>vLLM Connection</td></tr>
            <tr><td>Multi-Sessions</td><td>Redis + session_id isolation</td><td>Multi-Session</td></tr>
            <tr><td>Auth</td><td>FastAPI JWT get_current_user</td><td>JWT Auth</td></tr>
            <tr><td>LT/ST Memory</td><td>Redis + PG + Qdrant semantic search</td><td>ST/LT Memory</td></tr>
            <tr><td>Multi-Users</td><td>user_id on all data + Auth</td><td>JWT Auth</td></tr>
            <tr><td>Automation</td><td>APScheduler + Celery</td><td>APScheduler / Celery</td></tr>
            <tr><td>SSE Streaming</td><td>/chat/stream Server-Sent Events</td><td>SSE Streaming</td></tr>
            <tr><td>Web Search</td><td>Tavily API / DuckDuckGo fallback</td><td>Web Search API</td></tr>
          </tbody>
        </table>
      </section>
    </div>
  )
}
