import { useState } from 'react'
import { Lock, LogIn } from 'lucide-react'
import { adminLogin } from '../lib/api'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onAuthenticated: () => void
  onNavigate?: (s: Screen) => void
}

export default function AdminLogin({ dark, onAuthenticated }: Props) {
  const [secret, setSecret] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!secret.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await adminLogin(secret.trim())
      onAuthenticated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-5" style={{ background: 'var(--background)' }}>
      <div className="w-full max-w-md rounded-2xl p-7" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center mb-5"
          style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--primary)' }}
        >
          <Lock size={18} />
        </div>
        <h1 className="text-xl font-semibold mb-1" style={{ color: 'var(--foreground)' }}>Admin sign-in</h1>
        <p className="text-sm mb-6" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
          Enter the application shared secret to manage integrations, enterprise standards, AI settings, and assessments.
        </p>
        <form onSubmit={e => void handleSubmit(e)} className="space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>
              Admin secret
            </label>
            <input
              type="password"
              autoComplete="current-password"
              value={secret}
              onChange={e => setSecret(e.target.value)}
              placeholder="APP_SECRET_KEY"
              className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
              style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}`, color: 'var(--foreground)' }}
            />
            <p className="text-xs mt-1.5" style={{ color: 'var(--muted-foreground)' }}>
              Use the same value as <span className="font-mono">APP_SECRET_KEY</span>, or the configured admin password.
            </p>
          </div>
          {error && (
            <div className="text-sm rounded-lg px-3 py-2" style={{ background: dark ? '#3f1d1d' : '#fef2f2', color: dark ? '#fca5a5' : '#991b1b' }}>
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={submitting || !secret.trim()}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--primary)', color: '#fff', opacity: submitting || !secret.trim() ? 0.65 : 1 }}
          >
            <LogIn size={14} />
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
