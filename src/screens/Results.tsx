import { Download, Share2, RotateCcw, TrendingUp, ArrowRight } from 'lucide-react'
import { RadarChart, HeatmapChart } from '../components/Charts'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
}

const STRENGTHS = [
  'Consistent CI pipeline with required PR validation and automated builds on every merge.',
  'Strong Jira-to-code traceability (89%) enabling reliable change tracking.',
  'Regular deployment cadence with well-maintained staging environments.',
]

const OPPORTUNITIES = [
  { title: 'Production monitoring coverage is limited', practice: 'Production Monitoring', domain: 'CD' },
  { title: 'No current feature toggle or progressive rollout capability', practice: 'Feature Toggles', domain: 'RoD' },
  { title: 'Test-first practices applied inconsistently across the team', practice: 'Test-First Development', domain: 'CI' },
]

const NEXT_SPRINT = [
  {
    title: 'Require successful PR build validation',
    observation: 'Builds run on PRs but merge is not currently gated on CI passing.',
    practice: 'Continuous Integration',
    why: 'Ungated merges allow known failures to accumulate in main, increasing integration cost over time.',
    action: 'Require successful pipeline run as a branch protection rule on the claims-api repository.',
    kpi: '% of PRs completing all required checks before merge',
  },
]

const NINETY_DAYS = [
  {
    title: 'Create automated production smoke tests',
    observation: 'Post-deployment validation is currently manual and relies on a 20-minute observation window.',
    practice: 'Production Monitoring',
    why: 'Manual observation cannot scale as deployment frequency increases and introduces recovery latency.',
    action: 'Define a smoke test suite that runs automatically after each production deployment and connects results to change-failure reporting.',
    kpi: 'Change failure rate, mean time to recovery',
  },
]

const LONGER_TERM = [
  {
    title: 'Separate deployment from release using feature controls',
    observation: 'The team ships features directly to all users without progressive rollout.',
    practice: 'Feature Toggles',
    why: 'Decoupling deployment from release allows higher deployment frequency with lower blast radius.',
    action: 'Introduce feature toggle infrastructure and establish a progressive rollout pattern for new capabilities.',
    kpi: 'Deployment frequency, rollback rate, mean time to recover',
  },
]

function ActionCard({ item, horizon, dark }: { item: typeof NEXT_SPRINT[0]; horizon: string; dark: boolean }) {
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'
  const horizonStyles: Record<string, { bg: string; color: string }> = {
    'Next sprint': { bg: dark ? '#0f1d40' : '#eef3fa', color: 'var(--primary)' },
    '90 days': { bg: dark ? '#092b20' : '#d1fae5', color: '#10b981' },
    'Longer term': { bg: dark ? '#3b2409' : '#fef3c7', color: '#d97706' },
  }
  const hs = horizonStyles[horizon]

  return (
    <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
      <div className="flex items-center gap-2 mb-3">
        <span
          className="text-xs px-2.5 py-1 rounded-full font-semibold"
          style={{ background: hs.bg, color: hs.color }}
        >
          {horizon}
        </span>
        <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>{item.practice}</span>
      </div>
      <h3 className="font-semibold text-sm mb-2" style={{ color: 'var(--foreground)' }}>{item.title}</h3>
      <p className="text-sm mb-3" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>{item.observation}</p>
      <div
        className="rounded-lg p-3 mb-3"
        style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}
      >
        <p className="text-xs font-semibold mb-1" style={{ color: 'var(--foreground)' }}>Recommended action</p>
        <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>{item.action}</p>
      </div>
      <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--muted-foreground)' }}>
        <TrendingUp size={12} />
        <span>KPI: {item.kpi}</span>
      </div>
    </div>
  )
}

export default function Results({ dark, onNavigate }: Props) {
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      <div className="max-w-4xl mx-auto px-5 py-10">
        {/* Hero */}
        <div
          className="rounded-2xl p-7 mb-8"
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
                Published · 31 July 2024
              </div>
              <h1 className="font-serif text-3xl mb-2" style={{ color: '#fff', lineHeight: 1.2 }}>
                Claims Integration Team
              </h1>
              <p style={{ color: 'rgba(255,255,255,0.65)', fontSize: 15, marginBottom: 20 }}>
                SAFe DevOps Maturity Assessment · Claims API · 90-day evidence period
              </p>
              <div className="flex flex-wrap gap-4">
                <div>
                  <div className="text-sm mb-1" style={{ color: 'rgba(255,255,255,0.55)' }}>Overall maturity</div>
                  <div className="text-3xl font-semibold font-mono" style={{ color: '#fff' }}>2.7 <span style={{ fontSize: 16, color: 'rgba(255,255,255,0.5)' }}>/ 5.0</span></div>
                </div>
                <div>
                  <div className="text-sm mb-1" style={{ color: 'rgba(255,255,255,0.55)' }}>Confidence</div>
                  <div className="text-xl font-semibold" style={{ color: '#6ee7b7' }}>High</div>
                </div>
                <div>
                  <div className="text-sm mb-1" style={{ color: 'rgba(255,255,255,0.55)' }}>Practices assessed</div>
                  <div className="text-xl font-semibold font-mono" style={{ color: '#93c5fd' }}>11 / 16</div>
                </div>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <button
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-base"
                style={{ background: 'rgba(255,255,255,0.15)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.22)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.15)')}
              >
                <Download size={14} />
                Download PDF
              </button>
              <button
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-base"
                style={{ background: 'rgba(255,255,255,0.15)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.22)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.15)')}
              >
                <Share2 size={14} />
                Share report
              </button>
            </div>
          </div>
        </div>

        {/* Charts */}
        <div className="grid md:grid-cols-2 gap-5 mb-8">
          <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
            <p className="text-xs font-semibold uppercase tracking-widest mb-5" style={{ color: 'var(--muted-foreground)' }}>
              Four-domain radar
            </p>
            <RadarChart dark={dark} />
          </div>
          <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
            <p className="text-xs font-semibold uppercase tracking-widest mb-5" style={{ color: 'var(--muted-foreground)' }}>
              Sixteen-practice heatmap
            </p>
            <HeatmapChart dark={dark} adminView />
          </div>
        </div>

        {/* Strengths */}
        <section className="mb-8">
          <h2 className="font-semibold text-base mb-4" style={{ color: 'var(--foreground)' }}>Strengths</h2>
          <div className="space-y-2.5">
            {STRENGTHS.map((s, i) => (
              <div
                key={i}
                className="rounded-xl px-4 py-3.5 flex items-start gap-3"
                style={{ background: dark ? '#092b20' : '#d1fae5', border: `1px solid ${dark ? '#065f46' : '#6ee7b7'}` }}
              >
                <div className="w-1.5 h-1.5 rounded-full mt-2 shrink-0" style={{ background: '#10b981' }} />
                <p className="text-sm" style={{ color: dark ? '#4ade80' : '#065f46', lineHeight: 1.65 }}>{s}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Improvement opportunities */}
        <section className="mb-8">
          <h2 className="font-semibold text-base mb-4" style={{ color: 'var(--foreground)' }}>Highest-value improvement opportunities</h2>
          <div className="space-y-2.5">
            {OPPORTUNITIES.map(o => (
              <div
                key={o.title}
                className="rounded-xl px-4 py-3.5 flex items-start justify-between gap-4"
                style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
              >
                <div className="flex items-start gap-3">
                  <ArrowRight size={14} style={{ color: '#f59e0b', marginTop: 2, flexShrink: 0 }} />
                  <div>
                    <p className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>{o.title}</p>
                    <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>{o.practice} · {o.domain}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Improvement plan */}
        <section className="mb-8">
          <h2 className="font-semibold text-base mb-4" style={{ color: 'var(--foreground)' }}>Improvement plan</h2>
          <div className="space-y-4">
            {NEXT_SPRINT.map(item => <ActionCard key={item.title} item={item} horizon="Next sprint" dark={dark} />)}
            {NINETY_DAYS.map(item => <ActionCard key={item.title} item={item} horizon="90 days" dark={dark} />)}
            {LONGER_TERM.map(item => <ActionCard key={item.title} item={item} horizon="Longer term" dark={dark} />)}
          </div>
        </section>

        {/* KPIs */}
        <section className="mb-8">
          <h2 className="font-semibold text-base mb-4" style={{ color: 'var(--foreground)' }}>KPIs to monitor</h2>
          <div className="flex flex-wrap gap-2">
            {[
              '% PRs passing all required checks',
              'Change failure rate',
              'Mean time to recovery',
              'Deployment frequency',
              'Cycle time',
              'Lead time for changes',
              'Rollback rate',
            ].map(kpi => (
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

        {/* Footer actions */}
        <div
          className="rounded-xl p-5 flex items-center justify-between flex-wrap gap-3"
          style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
        >
          <div>
            <p className="font-medium text-sm" style={{ color: 'var(--foreground)' }}>Ready to reassess?</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
              Track improvement over time with a follow-up assessment in 60–90 days.
            </p>
          </div>
          <div className="flex gap-3">
            <button
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-base"
              style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
            >
              <Download size={14} />
              Export JSON
            </button>
            <button
              onClick={() => onNavigate('setup')}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-base"
              style={{ background: 'var(--primary)', color: '#fff' }}
              onMouseEnter={e => (e.currentTarget.style.opacity = '0.88')}
              onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
            >
              <RotateCcw size={14} />
              Start reassessment
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
