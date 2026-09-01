import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function AuthCallback({ onAuth }) {
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const token = params.get('token')
    if (!token) {
      setError('Missing token from OAuth callback')
      return
    }
    api.setToken(token)
    api.getMe()
      .then((user) => {
        onAuth(user)
        navigate('/', { replace: true })
      })
      .catch((err) => setError(err.message))
  }, [navigate, onAuth])

  if (error) {
    return (
      <div className="loading-screen">
        Sign-in failed: {error}
      </div>
    )
  }
  return <div className="loading-screen">Signing you in…</div>
}
