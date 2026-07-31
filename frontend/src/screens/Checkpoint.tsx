import { useEffect, useState } from 'react'
import { CheckCircle2, Circle, AlertCircle, ArrowRight, Save, UserPlus } from 'lucide-react'
import { completeInterview, getInterviewCheckpoint, saveInterview, type CheckpointData } from '../lib/api'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
  assessmentId?: string | null
}

export default function Checkpoint({ dark, onNavigate, assessmentId }: Props) {
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'
  const [data, setData] = useState<CheckpointData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [finishing, setFinishing] = useState(false)

  useEffect(() => {
    if (!assessmentId) return
    getInterviewCheckpoint(assessmentId)
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load checkpoint'))
  }, [assessmentId])

  async function handleSaveLater() {
    if (assessmentId) {
      try {
        await saveInterview(assessmentId, '')
      } catch {
        // ignore
      }
    }
    onNavigate('welcome')
  }

  async function handleFinish() {
    if (!assessmentId || !data?.completion_eligible) return
    setFinishing(true)
    try {
      await completeInterview(assessmentId)
      onNavigate('admin-review')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Cannot finish yet')
    } finally {
      setFinishing(false)
    }
  }

  const remaining = data?.remaining || []
  const covered = data?.covered || []
  const highPriority = remaining.filter(r => r.priority === 'high')

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)' }}
    >
      <div
        className="w-full max-w-2xl rounded-2xl overflow-hidden animate-fade-in"
        style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
      >
        <div
          className="p-6 pb-5"
          style={{ background: dark ? '#0f1d40' : '#eef3fa', borderBottom: `1px solid ${cardBorder}` }}
        >
          <div className="flex items-center gap-2 mb-2">
            <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ background: '#10b981' }}>
              <CheckCircle2 size={16} color="#fff" />
            </div>
            <span className="font-semibold text-sm" style={{ color: 'var(--primary)' }}>
              Good progress checkpoint
            </span>
          </div>
          <h2 className="font-serif text-xl mb-1" style={{ color: 'var(--foreground)' }}>
            {data?.headline || 'Checking coverage…'}
          </h2>
          <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
            {data?.summary || 'Loading coverage summary…'}
          </p>
        </div>

        <div className="p-6">
          {error && <div className="mb-4 text-sm" style={{ color: '#dc2626' }}>{error}</div>}

          <div className="grid md:grid-cols-2 gap-5 mb-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: '#10b981' }}>
                Covered
              </p>
              <div className="space-y-1.5">
                {covered.map(c => (
                  <div key={c.label} className="flex items-center gap-2 text-sm">
                    <CheckCircle2 size={13} style={{ color: '#10b981', flexShrink: 0 }} />
                    <span style={{ color: 'var(--muted-foreground)' }}>{c.label}</span>
                    <span className="text-xs ml-auto" style={{ color: 'var(--muted-foreground)', opacity: 0.6 }}>
                      {c.domain}
                    </span>
                  </div>
                ))}
                {covered.length === 0 && (
                  <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>None sufficiently covered yet.</p>
                )}
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: 'var(--muted-foreground)' }}>
                Remaining topics
              </p>
              <div className="space-y-2">
                {remaining.map(r => (
                  <div
                    key={r.label}
                    className="flex items-center gap-2 p-2.5 rounded-lg"
                    style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}
                  >
                    <Circle size={13} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
                    <span className="text-sm flex-1" style={{ color: 'var(--foreground)' }}>{r.label}</span>
                    <span
                      className="text-xs px-1.5 py-0.5 rounded"
                      style={{
                        background: r.priority === 'high' ? (dark ? '#3b2409' : '#fef3c7') : 'var(--muted)',
                        color: r.priority === 'high' ? '#d97706' : 'var(--muted-foreground)',
                      }}
                    >
                      {r.domain}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div
            className="rounded-xl p-4 mb-5 flex items-start gap-3"
            style={{ background: dark ? '#141f35' : '#fffbeb', border: `1px solid ${dark ? '#78350f' : '#fde68a'}` }}
          >
            <AlertCircle size={14} style={{ color: '#d97706', marginTop: 1, flexShrink: 0 }} />
            <p className="text-sm" style={{ color: dark ? '#fcd34d' : '#92400e', lineHeight: 1.6 }}>
              {highPriority.length > 0
                ? `High-priority remaining topics: ${highPriority.map(r => r.label).slice(0, 3).join(', ')}.`
                : data?.impact_note || 'Continue until server-side completion criteria are met.'}
              {data && !data.completion_eligible && data.completion_blockers.length > 0
                ? ` Blockers: ${data.completion_blockers.join('; ')}`
                : ''}
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => onNavigate('workshop')}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-base"
              style={{ background: 'var(--primary)', color: '#fff' }}
            >
              Continue now
              <ArrowRight size={14} />
            </button>
            {data?.completion_eligible && (
              <button
                onClick={() => void handleFinish()}
                disabled={finishing}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-base"
                style={{ background: '#10b981', color: '#fff' }}
              >
                {finishing ? 'Finishing…' : 'Finish assessment'}
              </button>
            )}
            <button
              onClick={() => onNavigate('remote-contributor')}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-base"
              style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
            >
              <UserPlus size={14} />
              Invite a contributor
            </button>
            <button
              onClick={() => void handleSaveLater()}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-base"
              style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
            >
              <Save size={14} />
              Save and resume later
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
