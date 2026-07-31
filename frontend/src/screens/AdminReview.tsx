import { useState } from 'react'
import { CheckCircle2, AlertTriangle, ChevronDown, ChevronUp, Edit3, RefreshCw, Check, Eye } from 'lucide-react'
import { SAMPLE_PRACTICES } from '../data/sampleData'
import { RadarChart, HeatmapChart } from '../components/Charts'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
}

const ADMIN_NAV = ['Overview', 'Evidence', 'Interview transcript', 'Practice coverage', 'Candidate scores', 'Improvement plan', 'Publication']

export default function AdminReview({ dark, onNavigate }: Props) {
  const [navItem, setNavItem] = useState('Practice coverage')
  const [expandedPractice, setExpandedPractice] = useState<string | null>('ci')
  const [scores, setScores] = useState<Record<string, number>>({})
  const [rationales, setRationales] = useState<Record<string, string>>({})
  const [editingScore, setEditingScore] = useState<string | null>(null)
  const [publishing, setPublishing] = useState(false)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  function handlePublish() {
    setPublishing(true)
    setTimeout(() => onNavigate('results'), 1800)
  }

  const scoreColors = ['', '#dc2626', '#f59e0b', '#3b7dd8', '#10b981', '#059669']

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      <div className="max-w-6xl mx-auto px-5 py-8">
        {/* Breadcrumb + title */}
        <div className="mb-6">
          <div className="flex items-center gap-2 text-xs font-medium mb-3" style={{ color: 'var(--muted-foreground)' }}>
            <button onClick={() => onNavigate('welcome')} className="hover:underline">Admin</button>
            <span>/</span>
            <span>Review</span>
          </div>
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-2xl font-semibold mb-1" style={{ color: 'var(--foreground)' }}>Admin review</h1>
              <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>
                Claims Integration · DevOps Maturity Assessment · Awaiting review
              </p>
            </div>
            {navItem === 'Publication' && (
              <button
                onClick={handlePublish}
                disabled={publishing}
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-base"
                style={{ background: publishing ? '#10b981' : 'var(--primary)', color: '#fff' }}
              >
                {publishing ? <><Check size={14} /> Published</> : <><Eye size={14} /> Approve and publish</>}
              </button>
            )}
          </div>
        </div>

        <div className="flex gap-5">
          {/* Left nav */}
          <div className="w-44 shrink-0">
            <nav className="space-y-0.5">
              {ADMIN_NAV.map(item => (
                <button
                  key={item}
                  onClick={() => setNavItem(item)}
                  className="w-full text-left px-3 py-2 rounded-lg text-sm transition-base"
                  style={{
                    background: navItem === item ? (dark ? '#0f1d40' : '#eef3fa') : 'transparent',
                    color: navItem === item ? 'var(--primary)' : 'var(--muted-foreground)',
                    fontWeight: navItem === item ? 500 : 400,
                  }}
                  onMouseEnter={e => { if (navItem !== item) e.currentTarget.style.background = 'var(--muted)' }}
                  onMouseLeave={e => { if (navItem !== item) e.currentTarget.style.background = 'transparent' }}
                >
                  {item}
                </button>
              ))}
            </nav>
          </div>

          {/* Main content */}
          <div className="flex-1 min-w-0">
            {navItem === 'Overview' && (
              <div className="space-y-4 animate-fade-in">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    { label: 'Interview duration', value: '74 min' },
                    { label: 'Participants', value: '4 (2 remote)' },
                    { label: 'Practices covered', value: '11 / 16' },
                    { label: 'Overall confidence', value: 'High' },
                  ].map(m => (
                    <div
                      key={m.label}
                      className="rounded-xl p-4"
                      style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
                    >
                      <div className="text-xs mb-1" style={{ color: 'var(--muted-foreground)' }}>{m.label}</div>
                      <div className="text-xl font-semibold font-mono" style={{ color: 'var(--foreground)' }}>{m.value}</div>
                    </div>
                  ))}
                </div>
                <div
                  className="rounded-xl p-5"
                  style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
                >
                  <h3 className="font-semibold text-sm mb-3" style={{ color: 'var(--foreground)' }}>Unresolved conflicts</h3>
                  <div
                    className="rounded-lg p-3 flex items-start gap-3"
                    style={{ background: dark ? '#3b2409' : '#fef3c7', border: `1px solid ${dark ? '#78350f' : '#fde68a'}` }}
                  >
                    <AlertTriangle size={14} style={{ color: '#d97706', marginTop: 1, flexShrink: 0 }} />
                    <div>
                      <p className="text-sm font-medium mb-1" style={{ color: dark ? '#fcd34d' : '#92400e' }}>
                        Feature toggles — team claim vs. evidence
                      </p>
                      <p className="text-xs" style={{ color: dark ? '#d97706' : '#b45309', lineHeight: 1.6 }}>
                        Team stated "we use feature flags in production", but no evidence of flag-specific branches or deployment patterns was found in Azure DevOps.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {navItem === 'Practice coverage' && (
              <div className="space-y-3 animate-fade-in">
                <p className="text-sm mb-4" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                  Review AI-proposed scores for each practice. Accept as-is or adjust with a required rationale.
                </p>
                {SAMPLE_PRACTICES.map(practice => {
                  const expanded = expandedPractice === practice.id
                  const adminScore = scores[practice.id] ?? practice.adminScore ?? practice.aiScore
                  const isEditing = editingScore === practice.id

                  return (
                    <div
                      key={practice.id}
                      className="rounded-xl overflow-hidden"
                      style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
                    >
                      <button
                        className="w-full flex items-center justify-between px-4 py-3.5 text-left transition-base"
                        onClick={() => setExpandedPractice(expanded ? null : practice.id)}
                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--muted)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className="w-2 h-2 rounded-sm"
                            style={{
                              background: practice.coverage === 'sufficient' ? '#10b981'
                                : practice.coverage === 'partial' ? '#f59e0b'
                                : dark ? '#334155' : '#cbd5e1',
                            }}
                          />
                          <span className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>
                            {practice.name}
                          </span>
                          <span
                            className="text-xs px-1.5 py-0.5 rounded"
                            style={{ background: dark ? '#141f35' : '#f1f5f9', color: 'var(--muted-foreground)' }}
                          >
                            {practice.domain}
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          {practice.aiScore && (
                            <div className="flex items-center gap-2">
                              <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>AI:</span>
                              <span
                                className="text-xs font-mono font-semibold w-5 h-5 rounded flex items-center justify-center"
                                style={{ background: scoreColors[practice.aiScore] + '22', color: scoreColors[practice.aiScore] }}
                              >
                                {practice.aiScore}
                              </span>
                            </div>
                          )}
                          {adminScore && (
                            <div className="flex items-center gap-2">
                              <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>Final:</span>
                              <span
                                className="text-xs font-mono font-semibold w-5 h-5 rounded flex items-center justify-center"
                                style={{ background: scoreColors[adminScore] + '22', color: scoreColors[adminScore] }}
                              >
                                {adminScore}
                              </span>
                            </div>
                          )}
                          {!practice.aiScore && <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>Not scored</span>}
                          {expanded ? <ChevronUp size={14} style={{ color: 'var(--muted-foreground)' }} /> : <ChevronDown size={14} style={{ color: 'var(--muted-foreground)' }} />}
                        </div>
                      </button>

                      {expanded && (
                        <div
                          className="px-4 pb-4 pt-0 animate-fade-in"
                          style={{ borderTop: `1px solid ${cardBorder}` }}
                        >
                          <div className="grid md:grid-cols-2 gap-4 mt-3">
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--muted-foreground)' }}>
                                Human evidence
                              </p>
                              <p className="text-sm" style={{ color: 'var(--foreground)', lineHeight: 1.7 }}>
                                Team described a structured PR process with required approvals and an automatic CI pipeline that blocks merge on failure. Mentioned a 20-minute post-deploy observation window.
                              </p>
                              <p
                                className="mt-2 text-xs italic"
                                style={{ color: 'var(--muted-foreground)' }}
                              >
                                "…the pipeline must pass before anyone can approve it…" — Workshop, Q3
                              </p>
                            </div>
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--muted-foreground)' }}>
                                Tool evidence
                              </p>
                              <p className="text-sm" style={{ color: 'var(--foreground)', lineHeight: 1.7 }}>
                                92 pipeline runs, 84% success rate. 44 completed PRs, 1.9 avg reviews, 1.8-day median. 89% Jira-key linkage.
                              </p>
                            </div>
                          </div>

                          {practice.aiScore && (
                            <div
                              className="mt-4 pt-4 flex items-start gap-4"
                              style={{ borderTop: `1px solid ${cardBorder}` }}
                            >
                              <div className="flex-1">
                                <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--muted-foreground)' }}>
                                  Admin score adjustment
                                </p>
                                {isEditing ? (
                                  <div className="space-y-2">
                                    <div className="flex gap-1.5">
                                      {[1, 2, 3, 4, 5].map(s => (
                                        <button
                                          key={s}
                                          onClick={() => setScores(prev => ({ ...prev, [practice.id]: s }))}
                                          className="w-9 h-9 rounded-lg text-sm font-semibold transition-base"
                                          style={{
                                            background: (scores[practice.id] ?? practice.adminScore ?? practice.aiScore) === s
                                              ? scoreColors[s]
                                              : 'var(--muted)',
                                            color: (scores[practice.id] ?? practice.adminScore ?? practice.aiScore) === s
                                              ? '#fff'
                                              : 'var(--muted-foreground)',
                                          }}
                                        >
                                          {s}
                                        </button>
                                      ))}
                                    </div>
                                    <textarea
                                      value={rationales[practice.id] || ''}
                                      onChange={e => setRationales(prev => ({ ...prev, [practice.id]: e.target.value }))}
                                      placeholder="Required: explain the adjustment…"
                                      className="w-full rounded-lg p-2.5 text-sm outline-none resize-none"
                                      style={{
                                        background: 'var(--muted)',
                                        border: '1px solid var(--border)',
                                        color: 'var(--foreground)',
                                        minHeight: 70,
                                      }}
                                      onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
                                      onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
                                    />
                                    <div className="flex gap-2">
                                      <button
                                        onClick={() => setEditingScore(null)}
                                        className="text-xs px-3 py-1.5 rounded-lg font-medium transition-base"
                                        style={{ background: 'var(--primary)', color: '#fff' }}
                                      >
                                        Save adjustment
                                      </button>
                                      <button
                                        onClick={() => setEditingScore(null)}
                                        className="text-xs px-3 py-1.5 rounded-lg transition-base"
                                        style={{ background: 'var(--muted)', color: 'var(--muted-foreground)', border: `1px solid ${cardBorder}` }}
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="flex items-center gap-3">
                                    <button
                                      onClick={() => setEditingScore(practice.id)}
                                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-base"
                                      style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
                                      onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
                                      onMouseLeave={e => (e.currentTarget.style.borderColor = cardBorder)}
                                    >
                                      <Edit3 size={11} />
                                      Adjust score
                                    </button>
                                    <button
                                      onClick={() => setScores(prev => ({ ...prev, [practice.id]: practice.aiScore! }))}
                                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-base"
                                      style={{ background: '#d1fae5', color: '#065f46' }}
                                    >
                                      <CheckCircle2 size={11} />
                                      Accept AI score
                                    </button>
                                    <button
                                      onClick={() => setEditingScore(practice.id)}
                                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-base"
                                      style={{ background: dark ? '#3b2409' : '#fef3c7', color: dark ? '#fcd34d' : '#92400e' }}
                                    >
                                      <RefreshCw size={11} />
                                      Reopen topic
                                    </button>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {navItem === 'Candidate scores' && (
              <div className="animate-fade-in space-y-6">
                <div
                  className="rounded-xl p-4 flex items-center gap-3"
                  style={{ background: dark ? '#3b2409' : '#fffbeb', border: `1px solid ${dark ? '#78350f' : '#fde68a'}` }}
                >
                  <AlertTriangle size={15} style={{ color: '#d97706', flexShrink: 0 }} />
                  <p className="text-sm" style={{ color: dark ? '#fcd34d' : '#92400e', lineHeight: 1.6 }}>
                    Candidate scores are confidential and visible only in this admin workspace before publication.
                  </p>
                </div>
                <HeatmapChart dark={dark} adminView />
              </div>
            )}

            {navItem === 'Publication' && (
              <div className="animate-fade-in space-y-5">
                <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
                  Review the preview below before publishing. Once published, the results will be visible to anyone with the report link.
                </p>
                <div className="grid md:grid-cols-2 gap-5">
                  <div
                    className="rounded-xl p-5"
                    style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
                  >
                    <p className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: 'var(--muted-foreground)' }}>
                      Domain radar preview
                    </p>
                    <RadarChart dark={dark} />
                  </div>
                  <div
                    className="rounded-xl p-5"
                    style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
                  >
                    <p className="text-xs font-semibold uppercase tracking-widest mb-4" style={{ color: 'var(--muted-foreground)' }}>
                      Practice heatmap preview
                    </p>
                    <HeatmapChart dark={dark} adminView />
                  </div>
                </div>
                <div className="flex items-center justify-end pt-2">
                  <button
                    onClick={handlePublish}
                    disabled={publishing}
                    className="flex items-center gap-2 px-6 py-3 rounded-lg text-sm font-semibold transition-base"
                    style={{ background: publishing ? '#10b981' : 'var(--primary)', color: '#fff' }}
                    onMouseEnter={e => (e.currentTarget.style.opacity = '0.88')}
                    onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
                  >
                    {publishing ? <><Check size={14} /> Publishing…</> : <><Eye size={14} /> Approve and publish</>}
                  </button>
                </div>
              </div>
            )}

            {navItem === 'Evidence' && (
              <div className="animate-fade-in">
                <p className="text-sm mb-4" style={{ color: 'var(--muted-foreground)' }}>Evidence as collected at the start of the assessment.</p>
                <HeatmapChart dark={dark} adminView={false} />
              </div>
            )}

            {navItem === 'Interview transcript' && (
              <div className="animate-fade-in space-y-3">
                <p className="text-sm mb-4" style={{ color: 'var(--muted-foreground)' }}>Full interview transcript as edited by the host.</p>
                {['Q1', 'Q2', 'Q3'].map((q, i) => (
                  <div key={q} className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                    <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--muted-foreground)' }}>
                      Question {i + 1}
                    </p>
                    <p className="text-sm font-serif mb-3" style={{ color: 'var(--foreground)', lineHeight: 1.6 }}>
                      {['Think of a recent representative change…', 'How does the team decide what to build next…', 'Describe what happens between a developer finishing a code change…'][i]}
                    </p>
                    <div className="text-sm whitespace-pre-wrap" style={{ color: 'var(--foreground)', lineHeight: 1.75, fontFamily: 'Inter, sans-serif' }}>
                      Jordan: We usually pick up a card from the backlog once sprint planning is done...
                    </div>
                  </div>
                ))}
              </div>
            )}

            {navItem === 'Improvement plan' && (
              <div className="animate-fade-in">
                <p className="text-sm mb-5" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                  Improvement plan is auto-generated from scores. Edit recommendations before publishing.
                </p>
                <div className="space-y-3">
                  {[
                    { horizon: 'Next sprint', title: 'Require PR build validation', practice: 'Continuous Integration' },
                    { horizon: '90 days', title: 'Automated production smoke tests', practice: 'Production Monitoring' },
                    { horizon: 'Longer term', title: 'Progressive rollout with feature controls', practice: 'Feature Toggles' },
                  ].map(r => (
                    <div
                      key={r.title}
                      className="rounded-xl p-4 flex items-start justify-between gap-4"
                      style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
                    >
                      <div>
                        <div className="flex items-center gap-2 mb-1.5">
                          <span
                            className="text-xs px-2 py-0.5 rounded-full font-medium"
                            style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--primary)' }}
                          >
                            {r.horizon}
                          </span>
                          <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>{r.practice}</span>
                        </div>
                        <p className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>{r.title}</p>
                      </div>
                      <button
                        className="text-xs px-2.5 py-1.5 rounded-lg transition-base shrink-0"
                        style={{ background: 'var(--muted)', color: 'var(--muted-foreground)', border: `1px solid ${cardBorder}` }}
                      >
                        Edit
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
