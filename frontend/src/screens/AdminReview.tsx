import { useEffect, useState } from 'react'
import { CheckCircle2, AlertTriangle, ChevronDown, ChevronUp, Edit3, RefreshCw, Check, Eye } from 'lucide-react'
import { RadarChart, HeatmapChart } from '../components/Charts'
import {
  addReviewObservation,
  approveReview,
  editRecommendation,
  getReview,
  markEvidenceUnreliable,
  publishAssessment,
  reopenReviewTopic,
  setReviewScore,
  startReview,
  type ReviewPackage,
  type ReviewPractice,
} from '../lib/api'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
  assessmentId?: string | null
}

const ADMIN_NAV = ['Overview', 'Evidence', 'Interview transcript', 'Practice coverage', 'Candidate scores', 'Improvement plan', 'Publication']

export default function AdminReview({ dark, onNavigate, assessmentId }: Props) {
  const [navItem, setNavItem] = useState('Practice coverage')
  const [expandedPractice, setExpandedPractice] = useState<string | null>(null)
  const [pkg, setPkg] = useState<ReviewPackage | null>(null)
  const [editingScore, setEditingScore] = useState<string | null>(null)
  const [draftScore, setDraftScore] = useState(3)
  const [draftRationale, setDraftRationale] = useState('')
  const [observationDraft, setObservationDraft] = useState('')
  const [recommendationDraft, setRecommendationDraft] = useState('')
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'
  const scoreColors = ['', '#dc2626', '#f59e0b', '#3b7dd8', '#10b981', '#059669']

  useEffect(() => {
    if (!assessmentId) {
      setError('No assessment selected. Complete a workshop first.')
      setLoading(false)
      return
    }
    setLoading(true)
    getReview(assessmentId)
      .catch(() => startReview(assessmentId))
      .then(setPkg)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load review'))
      .finally(() => setLoading(false))
  }, [assessmentId])

  async function refresh(next: Promise<ReviewPackage>) {
    try {
      setPkg(await next)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed')
    }
  }

  async function handlePublish() {
    if (!assessmentId || !pkg) return
    setPublishing(true)
    try {
      if (!pkg.ready_to_publish) await approveReview(assessmentId)
      await publishAssessment(assessmentId)
      onNavigate('results')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Publish failed')
      setPublishing(false)
    }
  }

  function scoreTone(score: number | null | undefined) {
    if (!score) return scoreColors[0]
    return scoreColors[Math.min(5, Math.max(1, Math.round(score)))]
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--background)', color: 'var(--muted-foreground)' }}>
        Preparing admin review…
      </div>
    )
  }

  const practices = pkg?.practices || []
  const covered = practices.filter(p => p.coverage_state !== 'not_discussed').length

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      <div className="max-w-6xl mx-auto px-5 py-8">
        <div className="mb-6">
          <div className="flex items-center gap-2 text-xs font-medium mb-3" style={{ color: 'var(--muted-foreground)' }}>
            <button onClick={() => onNavigate('welcome')} className="hover:underline">Admin</button>
            <span>/</span>
            <span>Review</span>
          </div>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-2xl font-semibold mb-1" style={{ color: 'var(--foreground)' }}>Admin review</h1>
              <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>
                {pkg?.team_name || 'Assessment'} · {pkg?.product_service_name || 'DevOps Maturity'} · Awaiting review
              </p>
            </div>
            {navItem === 'Publication' && (
              <button
                onClick={() => void handlePublish()}
                disabled={publishing}
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-base"
                style={{ background: publishing ? '#10b981' : 'var(--primary)', color: '#fff' }}
              >
                {publishing ? <><Check size={14} /> Published</> : <><Eye size={14} /> Approve and publish</>}
              </button>
            )}
          </div>
          {error && (
            <div className="mt-3 text-sm rounded-lg px-3 py-2" style={{ background: dark ? '#3f1d1d' : '#fef2f2', color: dark ? '#fca5a5' : '#991b1b' }}>
              {error}
            </div>
          )}
        </div>

        <div className="flex gap-5 flex-col md:flex-row">
          <div className="w-full md:w-44 shrink-0">
            <nav className="space-y-0.5 flex md:block overflow-x-auto gap-1">
              {ADMIN_NAV.map(item => (
                <button
                  key={item}
                  onClick={() => setNavItem(item)}
                  className="text-left px-3 py-2 rounded-lg text-sm transition-base whitespace-nowrap md:w-full"
                  style={{
                    background: navItem === item ? (dark ? '#0f1d40' : '#eef3fa') : 'transparent',
                    color: navItem === item ? 'var(--primary)' : 'var(--muted-foreground)',
                    fontWeight: navItem === item ? 500 : 400,
                  }}
                >
                  {item}
                </button>
              ))}
            </nav>
          </div>

          <div className="flex-1 min-w-0">
            {navItem === 'Overview' && pkg && (
              <div className="space-y-4 animate-fade-in">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    { label: 'Overall maturity', value: pkg.overall_maturity?.toFixed(1) || '—' },
                    { label: 'Confidence', value: pkg.confidence_summary || '—' },
                    { label: 'Practices covered', value: `${covered} / 16` },
                    { label: 'Evidence quality', value: pkg.evidence_quality || '—' },
                  ].map(m => (
                    <div key={m.label} className="rounded-xl p-4" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                      <div className="text-xs mb-1" style={{ color: 'var(--muted-foreground)' }}>{m.label}</div>
                      <div className="text-xl font-semibold font-mono" style={{ color: 'var(--foreground)' }}>{m.value}</div>
                    </div>
                  ))}
                </div>
                <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                  <h3 className="font-semibold text-sm mb-3" style={{ color: 'var(--foreground)' }}>Unresolved conflicts</h3>
                  {(pkg.maturity_gaps.length ? pkg.maturity_gaps : ['No unresolved conflicts recorded.']).slice(0, 4).map(gap => (
                    <div key={gap} className="rounded-lg p-3 flex items-start gap-3 mb-2" style={{ background: dark ? '#3b2409' : '#fef3c7', border: `1px solid ${dark ? '#78350f' : '#fde68a'}` }}>
                      <AlertTriangle size={14} style={{ color: '#d97706', marginTop: 1, flexShrink: 0 }} />
                      <p className="text-sm" style={{ color: dark ? '#fcd34d' : '#92400e', lineHeight: 1.6 }}>{gap}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(navItem === 'Evidence' || navItem === 'Interview transcript') && (
              <div className="rounded-xl p-5 animate-fade-in" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
                  {navItem === 'Evidence'
                    ? `Evidence influence mode: ${pkg?.evidence_influence_mode}. Limitations: ${(pkg?.evidence_limitations || []).join(' · ') || 'None recorded.'}`
                    : 'Interview answers are retained as interview turns and linked from each practice’s source turns during scoring.'}
                </p>
              </div>
            )}

            {navItem === 'Practice coverage' && (
              <div className="space-y-3 animate-fade-in">
                <p className="text-sm mb-4" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                  Review AI-proposed scores for each practice. Accept as-is or adjust with a required rationale.
                </p>
                {practices.map((practice: ReviewPractice) => {
                  const expanded = expandedPractice === practice.practice_key
                  const finalScore = practice.admin_final_score ?? practice.ai_candidate_score
                  const isEditing = editingScore === practice.practice_key
                  return (
                    <div key={practice.practice_key} className="rounded-xl overflow-hidden" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                      <button
                        className="w-full flex items-center justify-between px-4 py-3.5 text-left"
                        onClick={() => setExpandedPractice(expanded ? null : practice.practice_key)}
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className="w-2 h-2 rounded-sm"
                            style={{
                              background: practice.coverage_state === 'sufficient' ? '#10b981'
                                : practice.coverage_state === 'partial' ? '#f59e0b'
                                : dark ? '#334155' : '#cbd5e1',
                            }}
                          />
                          <span className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>{practice.practice_name}</span>
                          <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: dark ? '#141f35' : '#f1f5f9', color: 'var(--muted-foreground)' }}>
                            {practice.domain_short_name}
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          {practice.ai_candidate_score != null && (
                            <span className="text-xs font-mono font-semibold" style={{ color: scoreTone(practice.ai_candidate_score) }}>
                              AI {practice.ai_candidate_score.toFixed(1)}
                            </span>
                          )}
                          {finalScore != null && (
                            <span className="text-xs font-mono font-semibold" style={{ color: scoreTone(finalScore) }}>
                              Final {Number(finalScore).toFixed(1)}
                            </span>
                          )}
                          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </div>
                      </button>
                      {expanded && assessmentId && (
                        <div className="px-4 pb-4" style={{ borderTop: `1px solid ${cardBorder}` }}>
                          <div className="grid md:grid-cols-2 gap-4 mt-3">
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--muted-foreground)' }}>Human evidence</p>
                              <p className="text-sm" style={{ color: 'var(--foreground)', lineHeight: 1.7 }}>{practice.human_evidence || '—'}</p>
                            </div>
                            <div>
                              <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--muted-foreground)' }}>Tool evidence</p>
                              <p className="text-sm mb-2" style={{ color: 'var(--foreground)', lineHeight: 1.7 }}>
                                Jira: {practice.jira_evidence || '—'}
                              </p>
                              <p className="text-sm" style={{ color: 'var(--foreground)', lineHeight: 1.7 }}>
                                ADO: {practice.ado_evidence || '—'}
                              </p>
                            </div>
                          </div>
                          <p className="text-xs mt-3" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                            {practice.named_maturity_level || 'Unleveled'} · Confidence {practice.confidence != null ? practice.confidence.toFixed(2) : '—'}
                            {practice.scoring_rationale ? ` · ${practice.scoring_rationale}` : ''}
                          </p>
                          <div className="mt-4 flex flex-wrap gap-2">
                            {isEditing ? (
                              <>
                                <div className="flex gap-1.5 w-full">
                                  {[1, 2, 3, 4, 5].map(s => (
                                    <button
                                      key={s}
                                      onClick={() => setDraftScore(s)}
                                      className="w-9 h-9 rounded-lg text-sm font-semibold"
                                      style={{ background: draftScore === s ? scoreColors[s] : 'var(--muted)', color: draftScore === s ? '#fff' : 'var(--muted-foreground)' }}
                                    >
                                      {s}
                                    </button>
                                  ))}
                                </div>
                                <textarea
                                  value={draftRationale}
                                  onChange={e => setDraftRationale(e.target.value)}
                                  placeholder="Required: explain the adjustment…"
                                  className="w-full rounded-lg p-2.5 text-sm outline-none resize-none"
                                  style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)', minHeight: 70 }}
                                />
                                <button
                                  onClick={() => {
                                    void refresh(setReviewScore(assessmentId, practice.practice_key, {
                                      score: draftScore,
                                      rationale: draftRationale,
                                      accept_candidate: false,
                                    })).then(() => setEditingScore(null))
                                  }}
                                  className="text-xs px-3 py-1.5 rounded-lg font-medium"
                                  style={{ background: 'var(--primary)', color: '#fff' }}
                                >
                                  Save adjustment
                                </button>
                                <button onClick={() => setEditingScore(null)} className="text-xs px-3 py-1.5 rounded-lg" style={{ background: 'var(--muted)', color: 'var(--muted-foreground)' }}>
                                  Cancel
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  onClick={() => {
                                    setEditingScore(practice.practice_key)
                                    setDraftScore(Math.round(practice.ai_candidate_score || 3))
                                    setDraftRationale('')
                                  }}
                                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                                  style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
                                >
                                  <Edit3 size={11} /> Adjust score
                                </button>
                                <button
                                  onClick={() => void refresh(setReviewScore(assessmentId, practice.practice_key, { accept_candidate: true }))}
                                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                                  style={{ background: '#d1fae5', color: '#065f46' }}
                                >
                                  <CheckCircle2 size={11} /> Accept AI score
                                </button>
                                <button
                                  onClick={() => void refresh(markEvidenceUnreliable(assessmentId, practice.practice_key, !practice.evidence_unreliable))}
                                  className="text-xs px-3 py-1.5 rounded-lg"
                                  style={{ background: dark ? '#3b2409' : '#fef3c7', color: dark ? '#fcd34d' : '#92400e' }}
                                >
                                  {practice.evidence_unreliable ? 'Evidence marked unreliable' : 'Mark evidence unreliable'}
                                </button>
                                <button
                                  onClick={() => void refresh(reopenReviewTopic(assessmentId, practice.practice_key)).then(() => onNavigate('workshop'))}
                                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                                  style={{ background: dark ? '#3b2409' : '#fef3c7', color: dark ? '#fcd34d' : '#92400e' }}
                                >
                                  <RefreshCw size={11} /> Reopen topic
                                </button>
                              </>
                            )}
                          </div>
                          <div className="mt-3 grid md:grid-cols-2 gap-2">
                            <div>
                              <textarea
                                value={observationDraft}
                                onChange={e => setObservationDraft(e.target.value)}
                                placeholder="Add observation…"
                                className="w-full rounded-lg p-2 text-xs outline-none resize-none"
                                style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)', minHeight: 56 }}
                              />
                              <button
                                onClick={() => {
                                  if (!observationDraft.trim()) return
                                  void refresh(addReviewObservation(assessmentId, practice.practice_key, observationDraft)).then(() => setObservationDraft(''))
                                }}
                                className="mt-1 text-[11px] px-2 py-1 rounded"
                                style={{ background: 'var(--primary)', color: '#fff' }}
                              >
                                Save observation
                              </button>
                            </div>
                            <div>
                              <textarea
                                value={recommendationDraft}
                                onChange={e => setRecommendationDraft(e.target.value)}
                                placeholder={practice.recommendation_text || 'Edit recommendation…'}
                                className="w-full rounded-lg p-2 text-xs outline-none resize-none"
                                style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)', minHeight: 56 }}
                              />
                              <button
                                onClick={() => {
                                  if (!recommendationDraft.trim()) return
                                  void refresh(editRecommendation(assessmentId, practice.practice_key, recommendationDraft)).then(() => setRecommendationDraft(''))
                                }}
                                className="mt-1 text-[11px] px-2 py-1 rounded"
                                style={{ background: 'var(--primary)', color: '#fff' }}
                              >
                                Save recommendation
                              </button>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {navItem === 'Candidate scores' && pkg && (
              <div className="animate-fade-in space-y-6">
                <div className="rounded-xl p-4 flex items-center gap-3" style={{ background: dark ? '#3b2409' : '#fffbeb', border: `1px solid ${dark ? '#78350f' : '#fde68a'}` }}>
                  <AlertTriangle size={15} style={{ color: '#d97706', flexShrink: 0 }} />
                  <p className="text-sm" style={{ color: dark ? '#fcd34d' : '#92400e', lineHeight: 1.6 }}>
                    Candidate scores are confidential and visible only in this admin workspace before publication.
                  </p>
                </div>
                <HeatmapChart dark={dark} adminView cells={pkg.heatmap} summary={pkg.chart_summary} />
                <RadarChart dark={dark} data={pkg.radar} summary={pkg.chart_summary} />
              </div>
            )}

            {navItem === 'Improvement plan' && pkg && (
              <div className="space-y-3 animate-fade-in">
                {pkg.improvement_actions.map(action => (
                  <div key={action.id} className="rounded-xl p-4" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs font-semibold" style={{ color: 'var(--primary)' }}>{action.time_horizon}</span>
                      <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>{action.practice_key}</span>
                    </div>
                    <p className="text-sm font-semibold mb-1" style={{ color: 'var(--foreground)' }}>{action.title}</p>
                    <p className="text-sm mb-2" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>{action.observation}</p>
                    <p className="text-sm" style={{ color: 'var(--foreground)', lineHeight: 1.6 }}>{action.recommended_action}</p>
                    <p className="text-xs mt-2" style={{ color: 'var(--muted-foreground)' }}>KPI: {action.kpi} · Priority {action.priority}</p>
                  </div>
                ))}
              </div>
            )}

            {navItem === 'Publication' && pkg && (
              <div className="animate-fade-in space-y-5">
                <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
                  Review the preview below before publishing. Once published, hosts and contributors see only published results. Admin retains AI-versus-final comparison.
                </p>
                <div className="grid md:grid-cols-2 gap-5">
                  <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                    <RadarChart dark={dark} data={pkg.radar} summary={pkg.chart_summary} />
                  </div>
                  <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                    <HeatmapChart dark={dark} adminView cells={pkg.heatmap} summary={pkg.chart_summary} />
                  </div>
                </div>
                <div className="rounded-xl p-4" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                  <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>{pkg.chart_summary}</p>
                  <p className="text-xs mt-2" style={{ color: 'var(--muted-foreground)' }}>
                    Ready to publish: {pkg.ready_to_publish ? 'Yes' : 'No — approve to finalize remaining candidate scores'}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
