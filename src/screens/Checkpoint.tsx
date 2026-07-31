import { CheckCircle2, Circle, AlertCircle, ArrowRight, Save, UserPlus } from 'lucide-react'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
}

export default function Checkpoint({ dark, onNavigate }: Props) {
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  const remaining = [
    { label: 'Production monitoring', domain: 'CD', priority: 'high' },
    { label: 'Release-value measurement', domain: 'RoD', priority: 'medium' },
    { label: 'Recovery after failed changes', domain: 'CD', priority: 'high' },
    { label: 'Feature toggles', domain: 'RoD', priority: 'medium' },
    { label: 'Lean UX lifecycle', domain: 'RoD', priority: 'low' },
  ]

  const covered = [
    { label: 'Continuous Integration', domain: 'CI' },
    { label: 'Trunk-based development', domain: 'CI' },
    { label: 'Continuous Deployment', domain: 'CD' },
    { label: 'Staging environments', domain: 'CD' },
    { label: 'Continuous Exploration', domain: 'CE' },
    { label: 'Hypothesis-driven development', domain: 'CE' },
    { label: 'Continuous Planning', domain: 'CE' },
    { label: 'Release on Demand', domain: 'RoD' },
    { label: 'Non-functional requirements', domain: 'CI' },
    { label: 'Test-first development', domain: 'CI' },
    { label: 'Continuous Design', domain: 'CE' },
  ]

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)' }}
    >
      <div
        className="w-full max-w-2xl rounded-2xl overflow-hidden animate-fade-in"
        style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
      >
        {/* Header */}
        <div
          className="p-6 pb-5"
          style={{ background: dark ? '#0f1d40' : '#eef3fa', borderBottom: `1px solid ${cardBorder}` }}
        >
          <div className="flex items-center gap-2 mb-2">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center"
              style={{ background: '#10b981' }}
            >
              <CheckCircle2 size={16} color="#fff" />
            </div>
            <span className="font-semibold text-sm" style={{ color: 'var(--primary)' }}>
              Good progress checkpoint
            </span>
          </div>
          <h2 className="font-serif text-xl mb-1" style={{ color: 'var(--foreground)' }}>
            You've covered most of the delivery pipeline.
          </h2>
          <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
            11 of 16 practices sufficiently covered · 0 partially covered · 5 not yet discussed
          </p>
        </div>

        <div className="p-6">
          <div className="grid md:grid-cols-2 gap-5 mb-6">
            {/* Covered */}
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: '#10b981' }}>
                Covered
              </p>
              <div className="space-y-1.5">
                {covered.map(c => (
                  <div key={c.label} className="flex items-center gap-2 text-sm">
                    <CheckCircle2 size={13} style={{ color: '#10b981', flexShrink: 0 }} />
                    <span style={{ color: 'var(--muted-foreground)' }}>{c.label}</span>
                    <span
                      className="text-xs ml-auto"
                      style={{ color: 'var(--muted-foreground)', opacity: 0.6 }}
                    >
                      {c.domain}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Remaining */}
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
              The 3 remaining high-priority topics — production monitoring, release-value measurement, and recovery from failures — have the most impact on the final results.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => onNavigate('workshop')}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-base"
              style={{ background: 'var(--primary)', color: '#fff' }}
              onMouseEnter={e => (e.currentTarget.style.opacity = '0.88')}
              onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
            >
              Continue now
              <ArrowRight size={14} />
            </button>
            <button
              onClick={() => onNavigate('remote-contributor')}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-base"
              style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = cardBorder)}
            >
              <UserPlus size={14} />
              Invite a contributor
            </button>
            <button
              onClick={() => onNavigate('welcome')}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-base"
              style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = cardBorder)}
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
