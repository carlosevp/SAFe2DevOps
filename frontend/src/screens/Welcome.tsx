import { useState } from 'react'
import { ArrowRight, Play, Link2, Search, CheckCircle2, Shield, ChevronRight, X } from 'lucide-react'
import { listAssessments, type AssessmentSummary } from '../lib/api'
import type { Screen } from '../types'

interface WelcomeProps {
  dark: boolean
  onNavigate: (s: Screen) => void
  onResumeAssessment?: (id: string, name: string, next: Screen) => void
}

function resumeScreenForStatus(status: string): Screen {
  if (status === 'published' || status === 'archived') return 'results'
  if (status === 'admin_review' || status === 'interview_complete') return 'admin-review'
  if (status === 'evidence_ready' || status === 'collecting_evidence') return 'evidence'
  if (status === 'setup') return 'setup'
  return 'workshop'
}

export default function Welcome({ dark, onNavigate, onResumeAssessment }: WelcomeProps) {
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'
  const cardBg = dark ? 'var(--card)' : '#fff'
  const mutedBg = dark ? '#141f35' : '#f8fafc'
  const [resumeOpen, setResumeOpen] = useState(false)
  const [resumeLoading, setResumeLoading] = useState(false)
  const [resumeError, setResumeError] = useState<string | null>(null)
  const [assessments, setAssessments] = useState<AssessmentSummary[]>([])

  async function openResume() {
    setResumeOpen(true)
    setResumeLoading(true)
    setResumeError(null)
    try {
      const items = await listAssessments()
      setAssessments(items)
      if (!items.length) {
        setResumeError('No assessments found yet. Start a new assessment first.')
      }
    } catch (err) {
      setResumeError(err instanceof Error ? err.message : 'Could not load assessments')
    } finally {
      setResumeLoading(false)
    }
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      {/* Hero */}
      <div
        className="relative overflow-hidden"
        style={{
          background: dark
            ? 'linear-gradient(135deg, #07101f 0%, #0f1829 60%, #0d1e3a 100%)'
            : 'linear-gradient(135deg, #1b3a6b 0%, #1e4d8a 60%, #1b3a6b 100%)',
          paddingTop: 80,
          paddingBottom: 80,
        }}
      >
        {/* Subtle grid overlay */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.06) 1px, transparent 0)',
            backgroundSize: '32px 32px',
          }}
        />

        <div className="relative max-w-4xl mx-auto px-6 md:px-8">
          <div
            className="inline-flex items-center gap-2 text-xs font-medium uppercase tracking-widest rounded-full px-3 py-1.5 mb-8"
            style={{
              background: 'rgba(15, 139, 141, 0.2)',
              color: '#5de8e0',
              border: '1px solid rgba(15, 139, 141, 0.3)',
              letterSpacing: '0.1em',
            }}
          >
            SAFe DevOps · Adaptive Assessment
          </div>

          <h1
            className="font-serif mb-6"
            style={{
              fontSize: 'clamp(2rem, 4vw, 3.25rem)',
              lineHeight: 1.15,
              color: '#fff',
              fontWeight: 400,
              maxWidth: 640,
            }}
          >
            Understand how your team delivers — without filling out another maturity form.
          </h1>

          <p
            className="mb-10 max-w-xl"
            style={{ color: 'rgba(255,255,255,0.72)', fontSize: 18, lineHeight: 1.65 }}
          >
            Connect representative delivery evidence and complete a guided team conversation. The assessment adapts based on what your team says and what your tools show.
          </p>

          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => onNavigate('setup')}
              className="flex items-center gap-2 px-5 py-3 rounded-lg font-semibold text-sm transition-base"
              style={{ background: '#fff', color: '#1b3a6b' }}
              onMouseEnter={e => (e.currentTarget.style.background = '#eef3fa')}
              onMouseLeave={e => (e.currentTarget.style.background = '#fff')}
            >
              <Play size={15} />
              Start new assessment
            </button>
            <button
              onClick={() => void openResume()}
              className="flex items-center gap-2 px-5 py-3 rounded-lg font-medium text-sm transition-base"
              style={{ background: 'rgba(255,255,255,0.1)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)' }}
              onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.18)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.1)')}
            >
              Resume an assessment
            </button>
            <button
              onClick={() => onNavigate('remote-contributor')}
              className="flex items-center gap-2 px-5 py-3 rounded-lg font-medium text-sm transition-base"
              style={{ background: 'rgba(255,255,255,0.1)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)' }}
              onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.18)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.1)')}
            >
              <Link2 size={15} />
              Join an assessment
            </button>
          </div>
        </div>
      </div>

      {/* How it works */}
      <div className="max-w-4xl mx-auto px-6 md:px-8 py-16">
        <h2
          className="font-semibold text-sm uppercase tracking-widest mb-10"
          style={{ color: 'var(--muted-foreground)', letterSpacing: '0.1em' }}
        >
          How it works
        </h2>

        <div className="grid md:grid-cols-3 gap-5">
          {[
            {
              step: '01',
              icon: <Search size={20} />,
              title: 'Connect evidence',
              desc: 'Link one representative Jira project and one Azure DevOps repository. The app gathers delivery signals automatically.',
              color: '#3b7dd8',
            },
            {
              step: '02',
              icon: <Play size={20} />,
              title: 'Discuss how the team works',
              desc: 'A facilitator guides a natural team conversation. Voice is transcribed in real time. Remote contributors can join and type.',
              color: '#0f8b8d',
            },
            {
              step: '03',
              icon: <CheckCircle2 size={20} />,
              title: 'Review and publish results',
              desc: 'An admin reviews AI-proposed scores, adjusts if needed, and publishes a radar, heatmap, and improvement plan.',
              color: '#10b981',
            },
          ].map(item => (
            <div
              key={item.step}
              className="rounded-xl p-6 relative"
              style={{ background: cardBg, border: `1px solid ${cardBorder}` }}
            >
              <div
                className="w-9 h-9 rounded-lg flex items-center justify-center mb-4"
                style={{ background: item.color + '18', color: item.color }}
              >
                {item.icon}
              </div>
              <div
                className="absolute top-5 right-5 font-mono text-xs font-medium"
                style={{ color: dark ? '#334155' : '#cbd5e1' }}
              >
                {item.step}
              </div>
              <h3 className="font-semibold mb-2 text-sm" style={{ color: 'var(--foreground)' }}>
                {item.title}
              </h3>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--muted-foreground)' }}>
                {item.desc}
              </p>
            </div>
          ))}
        </div>

        {/* Trust statement */}
        <div
          className="mt-8 rounded-xl px-5 py-4 flex items-start gap-3"
          style={{ background: mutedBg, border: `1px solid ${cardBorder}` }}
        >
          <Shield size={16} style={{ color: 'var(--muted-foreground)', marginTop: 2, flexShrink: 0 }} />
          <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
            <span className="font-medium" style={{ color: 'var(--foreground)' }}>Privacy by default.</span>{' '}
            Tool credentials remain server-side and are never exposed to assessment participants. Audio is discarded after transcription by default. Only corrected transcripts are retained.
          </p>
        </div>

        {resumeOpen && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
            style={{ background: 'rgba(15, 23, 42, 0.55)' }}
            onClick={() => setResumeOpen(false)}
          >
            <div
              className="w-full max-w-lg rounded-xl p-5 shadow-xl"
              style={{ background: cardBg, border: `1px solid ${cardBorder}` }}
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>
                  Resume an assessment
                </h3>
                <button type="button" onClick={() => setResumeOpen(false)} className="p-1 rounded" style={{ color: 'var(--muted-foreground)' }}>
                  <X size={16} />
                </button>
              </div>
              <p className="text-xs mb-4" style={{ color: 'var(--muted-foreground)', lineHeight: 1.5 }}>
                Choose a saved assessment. Requests use <code>/api/assessments/…</code> with that id.
              </p>
              {resumeLoading && (
                <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>Loading assessments…</p>
              )}
              {resumeError && (
                <p className="text-sm mb-3" style={{ color: '#d97706' }}>{resumeError}</p>
              )}
              <div className="space-y-2 max-h-72 overflow-y-auto">
                {assessments.map(item => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      const next = resumeScreenForStatus(item.status)
                      onResumeAssessment?.(item.id, item.team_name, next)
                      setResumeOpen(false)
                    }}
                    className="w-full text-left rounded-lg px-3 py-2.5 transition-base"
                    style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}
                  >
                    <div className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>
                      {item.team_name}
                    </div>
                    <div className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
                      {item.product_service_name} · {item.status.replaceAll('_', ' ')}
                    </div>
                  </button>
                ))}
              </div>
              {!resumeLoading && !assessments.length && !resumeError && (
                <button
                  type="button"
                  onClick={() => {
                    setResumeOpen(false)
                    onNavigate('setup')
                  }}
                  className="mt-3 text-sm font-medium"
                  style={{ color: 'var(--primary)' }}
                >
                  Start a new assessment
                </button>
              )}
            </div>
          </div>
        )}

        {/* Admin links */}
        <div className="mt-10 pt-8" style={{ borderTop: `1px solid ${cardBorder}` }}>
          <p className="text-xs font-medium uppercase tracking-widest mb-4" style={{ color: 'var(--muted-foreground)' }}>
            Administration
          </p>
          <div className="flex flex-wrap gap-3">
            {[
              { label: 'Integrations', screen: 'integrations' as Screen },
              { label: 'Enterprise Standards', screen: 'enterprise-standards' as Screen },
              { label: 'AI & Voice settings', screen: 'ai-settings' as Screen },
              { label: 'Admin review', screen: 'admin-review' as Screen },
              { label: 'View published results', screen: 'results' as Screen },
            ].map(item => (
              <button
                key={item.screen}
                onClick={() => onNavigate(item.screen)}
                className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg transition-base"
                style={{
                  background: 'var(--muted)',
                  color: 'var(--foreground)',
                  border: `1px solid ${cardBorder}`,
                }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--primary)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = cardBorder)}
              >
                {item.label}
                <ChevronRight size={13} style={{ color: 'var(--muted-foreground)' }} />
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
