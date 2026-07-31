import { useEffect, useState } from 'react'
import { Download, RotateCcw, TrendingUp, ArrowRight } from 'lucide-react'
import { RadarChart, HeatmapChart } from '../components/Charts'
import { exportReportUrl, getPublishedResults, type ImprovementAction, type PublishedResults } from '../lib/api'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
  assessmentId?: string | null
}

function ActionCard({ item, horizon, dark }: { item: ImprovementAction; horizon: string; dark: boolean }) {
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'
  const horizonStyles: Record<string, { bg: string; color: string }> = {
    'Next sprint': { bg: dark ? '#0f1d40' : '#eef3fa', color: 'var(--primary)' },
    '90 days': { bg: dark ? '#092b20' : '#d1fae5', color: '#10b981' },
    'Longer term': { bg: dark ? '#3b2409' : '#fef3c7', color: '#d97706' },
  }
  const hs = horizonStyles[horizon]

  return (
    <div className="rounded-xl p-5 print:break-inside-avoid" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs px-2.5 py-1 rounded-full font-semibold" style={{ background: hs.bg, color: hs.color }}>
          {horizon}
        </span>
        <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>{item.practice_key}</span>
      </div>
      <h3 className="font-semibold text-sm mb-2" style={{ color: 'var(--foreground)' }}>{item.title}</h3>
      <p className="text-sm mb-3" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>{item.observation}</p>
      <div className="rounded-lg p-3 mb-3" style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}>
        <p className="text-xs font-semibold mb-1" style={{ color: 'var(--foreground)' }}>Recommended action</p>
        <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>{item.recommended_action}</p>
      </div>
      <p className="text-xs mb-2" style={{ color: 'var(--muted-foreground)', lineHeight: 1.55 }}>Why it matters: {item.why_it_matters}</p>
      <p className="text-xs mb-2" style={{ color: 'var(--muted-foreground)', lineHeight: 1.55 }}>Evidence: {item.supporting_evidence}</p>
      <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--muted-foreground)' }}>
        <TrendingUp size={12} />
        <span>KPI: {item.kpi}</span>
      </div>
    </div>
  )
}

function horizonLabel(value: string) {
  if (value === 'ninety_days') return '90 days'
  if (value === 'longer_term') return 'Longer term'
  return 'Next sprint'
}

export default function Results({ dark, onNavigate, assessmentId }: Props) {
  const [results, setResults] = useState<PublishedResults | null>(null)
  const [error, setError] = useState<string | null>(null)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  useEffect(() => {
    if (!assessmentId) {
      setError('No published assessment selected.')
      return
    }
    getPublishedResults(assessmentId)
      .then(setResults)
      .catch(err => setError(err instanceof Error ? err.message : 'Unable to load published results'))
  }, [assessmentId])

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center px-5" style={{ background: 'var(--background)', color: 'var(--muted-foreground)' }}>
        {error}
      </div>
    )
  }

  if (!results) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--background)', color: 'var(--muted-foreground)' }}>
        Loading published results…
      </div>
    )
  }

  const nextSprint = results.improvement_actions.filter(a => a.time_horizon === 'next_sprint')
  const ninety = results.improvement_actions.filter(a => a.time_horizon === 'ninety_days')
  const longer = results.improvement_actions.filter(a => a.time_horizon === 'longer_term')
  const kpis = Array.from(new Set(results.improvement_actions.map(a => a.kpi).filter(Boolean)))

  return (
    <div className="min-h-screen print:bg-white" style={{ background: 'var(--background)' }}>
      <div className="max-w-4xl mx-auto px-5 py-10">
        <div
          className="rounded-2xl p-7 mb-8 print:border print:border-slate-300"
          style={{
            background: dark
              ? 'linear-gradient(135deg, #07101f 0%, #0f1d40 100%)'
              : 'linear-gradient(135deg, #1b3a6b 0%, #1e4d8a 100%)',
          }}
        >
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div>
              <div
                className="inline-flex items-center gap-2 text-xs font-medium rounded-full px-3 py-1 mb-4"
                style={{ background: 'rgba(16,185,129,0.25)', color: '#6ee7b7' }}
              >
                Published · v{results.version} · {new Date(results.published_at).toLocaleDateString()}
              </div>
              <h1 className="font-serif text-3xl mb-2" style={{ color: '#fff', lineHeight: 1.2 }}>
                {results.team_name}
              </h1>
              <p style={{ color: 'rgba(255,255,255,0.65)', fontSize: 15, marginBottom: 20 }}>
                SAFe DevOps Maturity Assessment · {results.product_service_name} · {results.lookback_days}-day evidence period
              </p>
              <div className="flex flex-wrap gap-4">
                <div>
                  <div className="text-sm mb-1" style={{ color: 'rgba(255,255,255,0.55)' }}>Overall maturity</div>
                  <div className="text-3xl font-semibold font-mono" style={{ color: '#fff' }}>
                    {results.overall_maturity.toFixed(1)} <span style={{ fontSize: 16, color: 'rgba(255,255,255,0.5)' }}>/ 5.0</span>
                  </div>
                </div>
                <div>
                  <div className="text-sm mb-1" style={{ color: 'rgba(255,255,255,0.55)' }}>Confidence</div>
                  <div className="text-xl font-semibold" style={{ color: '#6ee7b7' }}>{results.confidence_summary}</div>
                </div>
                <div>
                  <div className="text-sm mb-1" style={{ color: 'rgba(255,255,255,0.55)' }}>Practices assessed</div>
                  <div className="text-xl font-semibold font-mono" style={{ color: '#93c5fd' }}>
                    {results.practices_assessed} / {results.practices_total}
                  </div>
                </div>
                <div>
                  <div className="text-sm mb-1" style={{ color: 'rgba(255,255,255,0.55)' }}>Evidence quality</div>
                  <div className="text-xl font-semibold" style={{ color: '#93c5fd' }}>{results.evidence_quality}</div>
                </div>
              </div>
            </div>
            <div className="flex flex-col gap-2 print:hidden">
              <a
                href={exportReportUrl(results.assessment_id, results.version, 'pdf')}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium"
                style={{ background: 'rgba(255,255,255,0.15)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)' }}
              >
                <Download size={14} />
                Download PDF
              </a>
              <a
                href={exportReportUrl(results.assessment_id, results.version, 'json')}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium"
                style={{ background: 'rgba(255,255,255,0.15)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)' }}
              >
                <Download size={14} />
                Export JSON
              </a>
            </div>
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-5 mb-8">
          <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
            <p className="text-xs font-semibold uppercase tracking-widest mb-5" style={{ color: 'var(--muted-foreground)' }}>
              Four-domain radar
            </p>
            <RadarChart dark={dark} data={results.radar} summary={results.chart_summary} />
          </div>
          <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
            <p className="text-xs font-semibold uppercase tracking-widest mb-5" style={{ color: 'var(--muted-foreground)' }}>
              Sixteen-practice heatmap
            </p>
            <HeatmapChart dark={dark} cells={results.heatmap} summary={results.chart_summary} />
          </div>
        </div>

        <section className="mb-8">
          <h2 className="font-semibold text-base mb-4" style={{ color: 'var(--foreground)' }}>Strengths</h2>
          <div className="space-y-2.5">
            {results.strengths.map(s => (
              <div key={s} className="rounded-xl px-4 py-3.5 flex items-start gap-3" style={{ background: dark ? '#092b20' : '#d1fae5', border: `1px solid ${dark ? '#065f46' : '#6ee7b7'}` }}>
                <div className="w-1.5 h-1.5 rounded-full mt-2 shrink-0" style={{ background: '#10b981' }} />
                <p className="text-sm" style={{ color: dark ? '#4ade80' : '#065f46', lineHeight: 1.65 }}>{s}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mb-8">
          <h2 className="font-semibold text-base mb-4" style={{ color: 'var(--foreground)' }}>Highest-value improvement opportunities</h2>
          <div className="space-y-2.5">
            {results.maturity_gaps.map(o => (
              <div key={o} className="rounded-xl px-4 py-3.5 flex items-start gap-3" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                <ArrowRight size={14} style={{ color: '#f59e0b', marginTop: 2, flexShrink: 0 }} />
                <p className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>{o}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mb-8">
          <h2 className="font-semibold text-base mb-4" style={{ color: 'var(--foreground)' }}>Evidence limitations</h2>
          <div className="space-y-2">
            {results.evidence_limitations.map(lim => (
              <p key={lim} className="text-sm rounded-lg px-3 py-2" style={{ background: 'var(--muted)', color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                {lim}
              </p>
            ))}
          </div>
        </section>

        {results.enterprise_standards && (
          <section className="mb-8">
            <h2 className="font-semibold text-base mb-4" style={{ color: 'var(--foreground)' }}>Enterprise Standards</h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
              {[
                { label: 'Applicable', value: results.enterprise_standards.applicable_count },
                { label: 'Aligned', value: results.enterprise_standards.aligned_count },
                { label: 'Partial', value: results.enterprise_standards.partially_aligned_count },
                { label: 'Findings', value: results.enterprise_standards.finding_count },
                { label: 'Insufficient evidence', value: results.enterprise_standards.insufficient_evidence_count },
              ].map(m => (
                <div key={m.label} className="rounded-xl p-3" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                  <div className="text-[11px] mb-1" style={{ color: 'var(--muted-foreground)' }}>{m.label}</div>
                  <div className="text-lg font-semibold font-mono" style={{ color: 'var(--foreground)' }}>{m.value}</div>
                </div>
              ))}
            </div>
            <div className="space-y-3">
              {Object.entries(results.enterprise_standards.findings_by_category || {}).map(([category, cards]) => (
                <div key={category}>
                  <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--muted-foreground)' }}>{category}</p>
                  <div className="space-y-3">
                    {cards.filter(c => c.status === 'finding' || c.status === 'partially_aligned' || c.status === 'insufficient_evidence').map(card => (
                      <div key={card.stable_key} className="rounded-xl p-4" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <p className="text-sm font-semibold" style={{ color: 'var(--foreground)' }}>{card.standard}</p>
                          <span className="text-[11px] px-2 py-0.5 rounded" style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--primary)' }}>{card.requirement_level}</span>
                          <span className="text-[11px] px-2 py-0.5 rounded" style={{ background: 'var(--muted)', color: 'var(--muted-foreground)' }}>{card.status.split('_').join(' ')}</span>
                        </div>
                        <p className="text-sm mb-2" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>{card.observation || '—'}</p>
                        <p className="text-xs mb-2" style={{ color: 'var(--muted-foreground)', lineHeight: 1.55 }}>Evidence: {card.supporting_evidence || '—'}</p>
                        <div className="rounded-lg p-3 mb-2" style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}>
                          <p className="text-xs font-semibold mb-1" style={{ color: 'var(--foreground)' }}>Recommendation</p>
                          <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>{card.recommendation || '—'}</p>
                        </div>
                        <p className="text-xs" style={{ color: 'var(--muted-foreground)' }}>
                          Related SAFe: {(card.related_safe_practices || []).join(', ') || '—'} · Horizon: {horizonLabel(card.suggested_time_horizon || 'next_sprint')}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="mb-8">
          <h2 className="font-semibold text-base mb-4" style={{ color: 'var(--foreground)' }}>Improvement plan</h2>
          <div className="space-y-4">
            {nextSprint.map(item => <ActionCard key={item.id} item={item} horizon={horizonLabel(item.time_horizon)} dark={dark} />)}
            {ninety.map(item => <ActionCard key={item.id} item={item} horizon={horizonLabel(item.time_horizon)} dark={dark} />)}
            {longer.map(item => <ActionCard key={item.id} item={item} horizon={horizonLabel(item.time_horizon)} dark={dark} />)}
          </div>
        </section>

        <section className="mb-8">
          <h2 className="font-semibold text-base mb-4" style={{ color: 'var(--foreground)' }}>KPIs to monitor</h2>
          <div className="flex flex-wrap gap-2">
            {kpis.map(kpi => (
              <span
                key={kpi}
                className="text-xs px-3 py-1.5 rounded-full font-medium"
                style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--primary)', border: `1px solid ${dark ? '#1e3358' : '#b0c7e6'}` }}
              >
                {kpi}
              </span>
            ))}
          </div>
        </section>

        <div className="rounded-xl p-5 flex items-center justify-between flex-wrap gap-3 print:hidden" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
          <div>
            <p className="font-medium text-sm" style={{ color: 'var(--foreground)' }}>Ready to reassess?</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
              Track improvement over time with a follow-up assessment in 60–90 days.
            </p>
          </div>
          <button
            onClick={() => onNavigate('setup')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold"
            style={{ background: 'var(--primary)', color: '#fff' }}
          >
            <RotateCcw size={14} />
            Start reassessment
          </button>
        </div>
      </div>
    </div>
  )
}
