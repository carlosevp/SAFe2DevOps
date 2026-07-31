import { useEffect, useMemo, useState } from 'react'
import { TrendingUp, TrendingDown, Minus, AlertTriangle, RefreshCw, CheckCircle2, XCircle, X } from 'lucide-react'
import {
  applyEvidenceExclusions,
  collectEvidence,
  confirmEvidence,
  getLatestEvidence,
  type EvidenceMetric,
  type EvidenceSnapshot,
} from '../lib/api'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
  assessmentId?: string | null
  assessmentName?: string
}

const EXCLUSION_OPTIONS = [
  'Bot commits',
  'Data migration work',
  'Experimental pipelines',
  'Dormant branches',
  'Emergency hotfix issues',
  'One-time setup tasks',
]

export default function EvidencePreview({ dark, onNavigate, assessmentId, assessmentName }: Props) {
  const [snapshot, setSnapshot] = useState<EvidenceSnapshot | null>(null)
  const [excluded, setExcluded] = useState<string[]>([])
  const [refreshing, setRefreshing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  useEffect(() => {
    if (!assessmentId) return
    getLatestEvidence(assessmentId)
      .then(data => {
        setSnapshot(data)
        setExcluded(data.exclusions || [])
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load evidence'))
  }, [assessmentId])

  function toggle(item: string) {
    setExcluded(prev => {
      const next = prev.includes(item) ? prev.filter(e => e !== item) : [...prev, item]
      if (assessmentId && snapshot) {
        applyEvidenceExclusions(assessmentId, snapshot.id, next)
          .then(setSnapshot)
          .catch(err => setError(err instanceof Error ? err.message : 'Failed to apply exclusions'))
      }
      return next
    })
  }

  async function handleRefresh() {
    if (!assessmentId) return
    setRefreshing(true)
    setError(null)
    try {
      const data = await collectEvidence(assessmentId, true)
      setSnapshot(data)
      setExcluded(data.exclusions || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  async function handleConfirm() {
    if (!assessmentId || !snapshot) return
    setConfirming(true)
    setError(null)
    try {
      await confirmEvidence(assessmentId, snapshot.id)
      onNavigate('workshop')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Confirm failed')
    } finally {
      setConfirming(false)
    }
  }

  const jiraMetrics = useMemo(
    () => (snapshot?.metrics || []).filter(m => m.source_system === 'jira'),
    [snapshot],
  )
  const adoMetrics = useMemo(
    () => (snapshot?.metrics || []).filter(m => m.source_system === 'azdo'),
    [snapshot],
  )
  const fetchedLabel = snapshot
    ? `Fetched ${new Date(snapshot.collected_at).toLocaleString()}`
    : 'Collecting…'
  const teamLabel = assessmentName || 'team'
  const qualityStates = useMemo(() => {
    const codes = new Set((snapshot?.limitations || []).map(l => l.code))
    if (snapshot?.quality) codes.add(snapshot.quality)
    return codes
  }, [snapshot])

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      <div className="max-w-3xl mx-auto px-6 py-10">
        <div className="flex items-center gap-2 text-xs font-medium mb-6" style={{ color: 'var(--muted-foreground)' }}>
          <button onClick={() => onNavigate('welcome')} className="hover:underline">Assessments</button>
          <span>/</span>
          <button onClick={() => onNavigate('setup')} className="hover:underline">Setup</button>
          <span>/</span>
          <span>Evidence preview</span>
        </div>

        <div className="mb-8">
          <h1 className="text-2xl font-semibold mb-2" style={{ color: 'var(--foreground)' }}>
            Evidence preview
          </h1>
          <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
            Review the delivery data collected from {snapshot?.jira_project_key || 'Jira'} and {snapshot?.ado_repository_name || 'Azure DevOps'} for the last {snapshot?.lookback_days || 90} days. Confirm this is representative before starting the assessment.
          </p>
        </div>

        {error && <div className="mb-4 text-sm" style={{ color: '#dc2626' }}>{error}</div>}

        {!assessmentId && (
          <div className="mb-6 text-sm" style={{ color: 'var(--muted-foreground)' }}>
            Complete assessment setup first to collect an evidence snapshot.
          </div>
        )}

        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--muted-foreground)' }}>
              Jira Cloud · {snapshot?.jira_project_key || '—'}
            </p>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--muted-foreground)' }}>
              {fetchedLabel}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-5">
            {jiraMetrics.map(m => (
              <MetricCard key={m.key} metric={m} dark={dark} />
            ))}
          </div>

          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--muted-foreground)' }}>
              Azure DevOps · {snapshot?.ado_repository_name || '—'}
            </p>
            <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--muted-foreground)' }}>
              {fetchedLabel}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
            {adoMetrics.map(m => (
              <MetricCard key={m.key} metric={m} dark={dark} />
            ))}
          </div>
        </div>

        <div
          className="rounded-xl p-5 mb-6"
          style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
        >
          <p className="text-sm font-semibold mb-1" style={{ color: 'var(--foreground)' }}>
            Exclude non-representative work
          </p>
          <p className="text-sm mb-4" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
            Select anything that would skew the evidence and shouldn't influence the assessment.
          </p>
          <div className="flex flex-wrap gap-2">
            {EXCLUSION_OPTIONS.map(opt => {
              const active = excluded.includes(opt)
              return (
                <button
                  key={opt}
                  onClick={() => toggle(opt)}
                  disabled={!snapshot || snapshot.immutable}
                  className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-full transition-base"
                  style={{
                    background: active ? (dark ? '#3b1010' : '#fee2e2') : 'var(--muted)',
                    color: active ? (dark ? '#fca5a5' : '#991b1b') : 'var(--foreground)',
                    border: `1px solid ${active ? (dark ? '#7f1d1d' : '#fca5a5') : cardBorder}`,
                    opacity: !snapshot || snapshot.immutable ? 0.6 : 1,
                  }}
                >
                  {active && <X size={11} />}
                  {opt}
                </button>
              )
            })}
          </div>
          {excluded.length > 0 && (
            <div
              className="mt-3 flex items-center gap-2 text-xs rounded-lg px-3 py-2 animate-fade-in"
              style={{ background: dark ? '#3b1010' : '#fff7ed', color: dark ? '#fca5a5' : '#92400e' }}
            >
              <AlertTriangle size={12} />
              {excluded.length} item{excluded.length > 1 ? 's' : ''} excluded. This will be noted in the evidence quality summary.
            </div>
          )}
        </div>

        <div
          className="rounded-xl p-5 mb-6"
          style={{ background: dark ? '#0f1d40' : '#eef3fa', border: `1px solid ${dark ? '#1e3358' : '#b0c7e6'}` }}
        >
          <p className="font-semibold mb-3" style={{ color: 'var(--foreground)', fontSize: 15 }}>
            Does this evidence represent how the {teamLabel} team normally delivers?
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => void handleConfirm()}
              disabled={!snapshot || confirming}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-base"
              style={{ background: 'var(--primary)', color: '#fff', opacity: !snapshot || confirming ? 0.7 : 1 }}
              onMouseEnter={e => (e.currentTarget.style.opacity = !snapshot || confirming ? '0.7' : '0.88')}
              onMouseLeave={e => (e.currentTarget.style.opacity = !snapshot || confirming ? '0.7' : '1')}
            >
              <CheckCircle2 size={15} />
              {confirming ? 'Confirming…' : 'Looks representative — start assessment'}
            </button>
            <button
              onClick={() => onNavigate('setup')}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-base"
              style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = cardBorder)}
            >
              Adjust scope
            </button>
            <button
              onClick={() => void handleRefresh()}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-base"
              style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = cardBorder)}
            >
              <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
              Refresh evidence
            </button>
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-3">
          <StateExample
            type="connection-error"
            dark={dark}
            active={qualityStates.has('connection_failure')}
            message={(snapshot?.limitations || []).find(l => l.code === 'connection_failure')?.message}
          />
          <StateExample
            type="no-activity"
            dark={dark}
            active={qualityStates.has('no_activity')}
            message={(snapshot?.limitations || []).find(l => l.code === 'no_activity')?.message}
          />
          <StateExample
            type="incomplete-adoption"
            dark={dark}
            active={qualityStates.has('incomplete_tool_adoption') || qualityStates.has('incomplete_adoption')}
            message={(snapshot?.limitations || []).find(l => l.code === 'incomplete_tool_adoption')?.message}
          />
          <StateExample
            type="unrepresentative"
            dark={dark}
            active={qualityStates.has('unrepresentative_selection') || qualityStates.has('unrepresentative')}
            message={(snapshot?.limitations || []).find(l => l.code === 'unrepresentative_selection')?.message}
          />
        </div>
      </div>
    </div>
  )
}

function MetricCard({ metric, dark }: { metric: EvidenceMetric; dark: boolean }) {
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'
  const isJira = metric.source_system === 'jira'
  const sourceBg = isJira
    ? (dark ? '#0f1d40' : '#eef3fa')
    : (dark ? '#141f35' : '#f0fdfc')
  const sourceColor = isJira
    ? (dark ? '#7ea4d3' : '#1b3a6b')
    : (dark ? '#5de8e0' : '#0e7170')
  const trend = metric.trend

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
    >
      <div className="flex items-start justify-between mb-2">
        <span
          className="text-xs px-1.5 py-0.5 rounded font-medium"
          style={{ background: sourceBg, color: sourceColor, fontSize: 10 }}
        >
          {isJira ? 'Jira' : 'ADO'}
        </span>
        {trend === 'up' && <TrendingUp size={13} style={{ color: '#10b981' }} />}
        {trend === 'down' && <TrendingDown size={13} style={{ color: '#f59e0b' }} />}
        {trend === 'neutral' && <Minus size={13} style={{ color: 'var(--muted-foreground)' }} />}
      </div>
      <div className="font-semibold font-mono text-xl mb-1" style={{ color: 'var(--foreground)' }}>
        {metric.value_text}
      </div>
      <div className="text-xs" style={{ color: 'var(--muted-foreground)', lineHeight: 1.4 }}>
        {metric.label}
      </div>
    </div>
  )
}

function StateExample({
  type,
  dark,
  active,
  message,
}: {
  type: string
  dark: boolean
  active?: boolean
  message?: string
}) {
  const configs = {
    'connection-error': {
      icon: <XCircle size={15} />,
      color: '#dc2626',
      bg: dark ? '#3b1010' : '#fee2e2',
      border: dark ? '#7f1d1d' : '#fca5a5',
      title: 'Connection error',
      desc: 'Could not reach Jira. Check credentials in Integrations.',
    },
    'no-activity': {
      icon: <AlertTriangle size={15} />,
      color: '#d97706',
      bg: dark ? '#3b2409' : '#fef3c7',
      border: dark ? '#78350f' : '#fde68a',
      title: 'No recent activity',
      desc: 'No issues were completed in the last 90 days in this project.',
    },
    'incomplete-adoption': {
      icon: <AlertTriangle size={15} />,
      color: '#d97706',
      bg: dark ? '#3b2409' : '#fef3c7',
      border: dark ? '#78350f' : '#fde68a',
      title: 'Incomplete tool adoption',
      desc: 'Fewer than 20% of commits reference a Jira issue. Traceability evidence is limited.',
    },
    'unrepresentative': {
      icon: <AlertTriangle size={15} />,
      color: '#d97706',
      bg: dark ? '#3b2409' : '#fef3c7',
      border: dark ? '#78350f' : '#fde68a',
      title: 'Potentially unrepresentative',
      desc: 'Evidence includes a large migration batch that completed 75% of issues in a single sprint.',
    },
  }
  const c = configs[type as keyof typeof configs]
  return (
    <div
      className="rounded-xl p-3.5 flex items-start gap-2.5"
      style={{
        background: c.bg,
        border: `1px solid ${c.border}`,
        opacity: active ? 1 : 0.55,
      }}
    >
      <span style={{ color: c.color, marginTop: 1, flexShrink: 0 }}>{c.icon}</span>
      <div>
        <p className="text-xs font-semibold mb-0.5" style={{ color: c.color }}>{c.title}</p>
        <p className="text-xs" style={{ color: c.color, opacity: 0.85, lineHeight: 1.5 }}>{message || c.desc}</p>
      </div>
    </div>
  )
}
