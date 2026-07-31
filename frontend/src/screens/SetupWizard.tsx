import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, ChevronLeft, Check, Info, Copy, Users, Laptop, Globe } from 'lucide-react'
import {
  collectEvidence,
  createAssessment,
  listAdoBranches,
  listAdoPipelines,
  listAdoProjects,
  listAdoRepos,
  listJiraBoards,
  listJiraProjects,
  setSourceSelection,
  type CatalogPipeline,
  type CatalogProject,
  type CatalogRepo,
} from '../lib/api'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
  onAssessmentReady?: (assessmentId: string, assessmentName: string) => void
}

function StepIndicator({ current, total, dark }: { current: number; total: number; dark: boolean }) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }, (_, i) => {
        const done = i < current
        const active = i === current
        return (
          <div key={i} className="flex items-center gap-2">
            <div
              className="flex items-center justify-center text-xs font-semibold transition-base"
              style={{
                width: 28,
                height: 28,
                borderRadius: '50%',
                background: done ? '#10b981' : active ? 'var(--primary)' : dark ? '#1a2540' : '#e2e8f0',
                color: done || active ? '#fff' : 'var(--muted-foreground)',
                fontSize: 11,
              }}
            >
              {done ? <Check size={13} /> : i + 1}
            </div>
            {i < total - 1 && (
              <div
                style={{
                  width: 24,
                  height: 2,
                  borderRadius: 1,
                  background: done ? '#10b981' : dark ? '#1e3358' : '#e2e8f0',
                }}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>
      {children}
    </label>
  )
}

function TextField({
  value,
  placeholder,
  hint,
  onChange,
}: {
  value: string
  placeholder: string
  hint?: string
  onChange: (v: string) => void
}) {
  return (
    <div>
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-base"
        style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
        onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
        onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
      />
      {hint && <p className="text-xs mt-1.5" style={{ color: 'var(--muted-foreground)' }}>{hint}</p>}
    </div>
  )
}

function SelectField({
  options,
  value,
  onChange,
  disabled,
}: {
  options: { value: string; label: string }[]
  value: string
  onChange: (v: string) => void
  disabled?: boolean
}) {
  return (
    <select
      className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-base appearance-none"
      style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
      value={value}
      disabled={disabled}
      onChange={e => onChange(e.target.value)}
      onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
      onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
    >
      {options.map(o => (
        <option key={o.value || o.label} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

const STEP_TITLES = [
  'Team & scope',
  'Jira project',
  'Azure DevOps source',
  'Evidence influence',
  'Participation',
]

const INFLUENCE_API = {
  context: 'context_only',
  balanced: 'balanced',
  evidence: 'evidence_led',
} as const

const PARTICIPATION_API = {
  room: 'facilitated_room',
  'room-remote': 'hybrid_remote',
  later: 'remote_only',
} as const

export default function SetupWizard({ dark, onNavigate, onAssessmentReady }: Props) {
  const [step, setStep] = useState(0)
  const [lookback, setLookback] = useState(90)
  const [influence, setInfluence] = useState<'context' | 'balanced' | 'evidence'>('balanced')
  const [participation, setParticipation] = useState<'room' | 'room-remote' | 'later'>('room-remote')
  const [linkCopied, setLinkCopied] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [teamName, setTeamName] = useState('Claims Integration')
  const [productName, setProductName] = useState('Claims API')
  const [description, setDescription] = useState('REST API for insurance claims processing, consumed by the claims portal.')
  const [ownerName, setOwnerName] = useState('Jordan Mills')
  const [ownerEmail, setOwnerEmail] = useState('jordan.mills@claimsco.example')
  const [valueStream, setValueStream] = useState('')

  const [jiraProjects, setJiraProjects] = useState<CatalogProject[]>([])
  const [jiraBoards, setJiraBoards] = useState<CatalogProject[]>([])
  const [jiraProjectKey, setJiraProjectKey] = useState('')
  const [jiraBoardId, setJiraBoardId] = useState('')
  const [jiraJql, setJiraJql] = useState('')

  const [adoProjects, setAdoProjects] = useState<CatalogProject[]>([])
  const [adoRepos, setAdoRepos] = useState<CatalogRepo[]>([])
  const [adoBranches, setAdoBranches] = useState<string[]>([])
  const [adoPipelines, setAdoPipelines] = useState<CatalogPipeline[]>([])
  const [adoProjectId, setAdoProjectId] = useState('')
  const [adoRepoId, setAdoRepoId] = useState('')
  const [defaultBranch, setDefaultBranch] = useState('main')
  const [selectedPipelineIds, setSelectedPipelineIds] = useState<string[]>([])

  const cardBorder = dark ? '#1e3358' : '#e2e8f0'
  const cardBg = 'var(--card)'

  useEffect(() => {
    Promise.all([listJiraProjects(), listAdoProjects()])
      .then(([jira, ado]) => {
        setJiraProjects(jira)
        setAdoProjects(ado)
        if (jira[0]?.key) setJiraProjectKey(jira[0].key)
        if (ado[0]?.id) setAdoProjectId(ado[0].id)
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load catalog'))
  }, [])

  useEffect(() => {
    if (!jiraProjectKey) return
    listJiraBoards(jiraProjectKey)
      .then(boards => {
        setJiraBoards(boards)
        setJiraBoardId('')
      })
      .catch(() => setJiraBoards([]))
  }, [jiraProjectKey])

  useEffect(() => {
    if (!adoProjectId) return
    listAdoRepos(adoProjectId)
      .then(repos => {
        setAdoRepos(repos)
        const first = repos[0]
        setAdoRepoId(first?.id || '')
        if (first?.default_branch) setDefaultBranch(first.default_branch)
      })
      .catch(() => setAdoRepos([]))
  }, [adoProjectId])

  useEffect(() => {
    if (!adoProjectId || !adoRepoId) return
    const repo = adoRepos.find(r => r.id === adoRepoId)
    listAdoBranches(adoProjectId, adoRepoId)
      .then(branches => {
        setAdoBranches(branches)
        if (repo?.default_branch) setDefaultBranch(repo.default_branch)
        else if (branches[0]) setDefaultBranch(branches[0])
      })
      .catch(() => setAdoBranches([]))
    listAdoPipelines(adoProjectId, repo?.name)
      .then(pipelines => {
        setAdoPipelines(pipelines)
        setSelectedPipelineIds(pipelines.map(p => p.id))
      })
      .catch(() => setAdoPipelines([]))
  }, [adoProjectId, adoRepoId, adoRepos])

  const jiraProject = useMemo(
    () => jiraProjects.find(p => p.key === jiraProjectKey) || null,
    [jiraProjects, jiraProjectKey],
  )
  const adoProject = useMemo(
    () => adoProjects.find(p => p.id === adoProjectId) || null,
    [adoProjects, adoProjectId],
  )
  const adoRepo = useMemo(
    () => adoRepos.find(r => r.id === adoRepoId) || null,
    [adoRepos, adoRepoId],
  )
  const jiraBoard = useMemo(
    () => jiraBoards.find(b => b.id === jiraBoardId) || null,
    [jiraBoards, jiraBoardId],
  )

  function copyLink() {
    setLinkCopied(true)
    setTimeout(() => setLinkCopied(false), 2000)
  }

  const scopeStatement = `Assess the ${teamName || 'team'} using the ${jiraProjectKey || 'selected'} Jira project and ${adoRepo?.name || 'selected'} repository as representative evidence from the last ${lookback} days.`

  async function finishSetup() {
    setSubmitting(true)
    setError(null)
    try {
      const assessment = await createAssessment({
        team_name: teamName,
        product_service_name: productName,
        description: description || undefined,
        value_stream: valueStream || undefined,
        owner_name: ownerName,
        owner_email: ownerEmail,
        lookback_days: Math.min(365, Math.max(30, lookback)),
        evidence_influence_mode: INFLUENCE_API[influence],
        participation_mode: PARTICIPATION_API[participation],
      })
      await setSourceSelection(assessment.id, {
        jira_project_key: jiraProjectKey,
        jira_project_name: jiraProject?.name || null,
        jira_board_id: jiraBoardId || null,
        jira_board_name: jiraBoard?.name || null,
        jira_jql: jiraJql || null,
        ado_project_id: adoProjectId,
        ado_project_name: adoProject?.name || null,
        ado_repository_id: adoRepoId,
        ado_repository_name: adoRepo?.name || 'repository',
        default_branch: defaultBranch,
        selected_pipelines: adoPipelines
          .filter(p => selectedPipelineIds.includes(p.id))
          .map(p => ({ id: p.id, name: p.name })),
      })
      await collectEvidence(assessment.id)
      onAssessmentReady?.(assessment.id, assessment.team_name)
      onNavigate('evidence')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Setup failed')
    } finally {
      setSubmitting(false)
    }
  }

  function togglePipeline(id: string) {
    setSelectedPipelineIds(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]))
  }

  function renderStep() {
    switch (step) {
      case 0:
        return (
          <div className="space-y-5">
            <div className="grid md:grid-cols-2 gap-4">
              <div><Label>Team name</Label><TextField placeholder="e.g. Claims Integration" value={teamName} onChange={setTeamName} /></div>
              <div><Label>Product, application, or service</Label><TextField placeholder="e.g. Claims API" value={productName} onChange={setProductName} /></div>
            </div>
            <div><Label>Brief description (optional)</Label><TextField placeholder="What does this team deliver?" value={description} onChange={setDescription} /></div>
            <div className="grid md:grid-cols-2 gap-4">
              <div><Label>Assessment owner</Label><TextField placeholder="Name" value={ownerName} onChange={setOwnerName} /></div>
              <div><Label>Owner email</Label><TextField placeholder="owner@example.com" value={ownerEmail} onChange={setOwnerEmail} /></div>
            </div>
            <div><Label>Value stream (optional)</Label><TextField placeholder="e.g. Claims Processing" value={valueStream} onChange={setValueStream} /></div>

            <div>
              <Label>Evidence lookback period</Label>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min={30}
                  max={365}
                  value={lookback}
                  onChange={e => setLookback(Number(e.target.value))}
                  className="flex-1"
                  style={{ accentColor: 'var(--primary)' }}
                />
                <div className="flex items-center gap-1.5">
                  <input
                    type="number"
                    min={30}
                    max={365}
                    value={lookback}
                    onChange={e => setLookback(Number(e.target.value))}
                    className="w-16 rounded-lg px-2 py-1.5 text-sm text-center outline-none font-mono"
                    style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
                  />
                  <span className="text-sm" style={{ color: 'var(--muted-foreground)' }}>days</span>
                </div>
              </div>
              <p className="text-xs mt-1.5" style={{ color: 'var(--muted-foreground)' }}>
                Default 90 days · Configurable 30–365
              </p>
            </div>

            <div
              className="rounded-xl p-4"
              style={{ background: dark ? '#0f1d40' : '#eef3fa', border: `1px solid ${dark ? '#1e3358' : '#b0c7e6'}` }}
            >
              <p className="text-xs font-medium mb-1" style={{ color: 'var(--muted-foreground)' }}>Generated scope statement</p>
              <p className="text-sm italic font-serif" style={{ color: 'var(--foreground)', lineHeight: 1.65 }}>
                "{scopeStatement}"
              </p>
            </div>
          </div>
        )

      case 1:
        return (
          <div className="space-y-5">
            <div
              className="rounded-xl p-4 flex items-start gap-3"
              style={{ background: dark ? '#141f35' : '#f0fdfc', border: `1px solid ${dark ? '#1e3358' : '#ccfbf7'}` }}
            >
              <Info size={14} style={{ color: '#0f8b8d', marginTop: 1, flexShrink: 0 }} />
              <p className="text-sm" style={{ color: dark ? '#5de8e0' : '#0e7170', lineHeight: 1.6 }}>
                Choose the most recent or representative project that reflects how this team normally works.
              </p>
            </div>
            <div>
              <Label>Jira project</Label>
              <SelectField
                value={jiraProjectKey}
                onChange={setJiraProjectKey}
                options={jiraProjects.map(p => ({ value: p.key || p.id, label: `${p.key} — ${p.name}` }))}
              />
            </div>
            <div>
              <Label>Board (optional)</Label>
              <SelectField
                value={jiraBoardId}
                onChange={setJiraBoardId}
                options={[
                  { value: '', label: '— None —' },
                  ...jiraBoards.map(b => ({ value: b.id, label: b.name })),
                ]}
              />
            </div>
            <div>
              <Label>JQL refinement (optional)</Label>
              <TextField
                placeholder={`project = ${jiraProjectKey || 'CLAIM'} AND type != Epic AND created >= -${lookback}d`}
                value={jiraJql}
                onChange={setJiraJql}
              />
              <p className="text-xs mt-1.5" style={{ color: 'var(--muted-foreground)' }}>
                Advanced filter. Leave blank to use all issues in the selected project within the lookback period.
              </p>
            </div>
          </div>
        )

      case 2:
        return (
          <div className="space-y-5">
            <div
              className="rounded-xl p-4 flex items-start gap-3"
              style={{ background: dark ? '#141f35' : '#f0fdfc', border: `1px solid ${dark ? '#1e3358' : '#ccfbf7'}` }}
            >
              <Info size={14} style={{ color: '#0f8b8d', marginTop: 1, flexShrink: 0 }} />
              <p className="text-sm" style={{ color: dark ? '#5de8e0' : '#0e7170', lineHeight: 1.6 }}>
                Choose one representative repository linked as closely as possible to the selected Jira project.
              </p>
            </div>
            <div>
              <Label>Project</Label>
              <SelectField
                value={adoProjectId}
                onChange={setAdoProjectId}
                options={adoProjects.map(p => ({ value: p.id, label: p.name }))}
              />
            </div>
            <div>
              <Label>Repository</Label>
              <SelectField
                value={adoRepoId}
                onChange={setAdoRepoId}
                options={adoRepos.map(r => ({ value: r.id, label: r.name }))}
                disabled={!adoProjectId}
              />
            </div>
            <div>
              <Label>Default branch</Label>
              <SelectField
                value={defaultBranch}
                onChange={setDefaultBranch}
                options={(adoBranches.length ? adoBranches : [defaultBranch]).map(b => ({ value: b, label: b }))}
              />
            </div>
            <div>
              <Label>Pipelines</Label>
              <div className="space-y-2">
                {adoPipelines.map(p => (
                  <div
                    key={p.id}
                    className="rounded-lg px-3 py-2.5 flex items-center justify-between"
                    style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}
                  >
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ background: '#10b981' }} />
                      <span className="text-sm font-mono" style={{ color: 'var(--foreground)', fontSize: 12 }}>{p.name}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--muted-foreground)' }}>
                      <span>{p.runs ?? '—'} runs</span>
                      <span style={{ color: '#10b981', fontWeight: 500 }}>{p.success_rate || '—'}</span>
                      <input
                        type="checkbox"
                        checked={selectedPipelineIds.includes(p.id)}
                        onChange={() => togglePipeline(p.id)}
                        style={{ accentColor: 'var(--primary)' }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-xs mt-2" style={{ color: 'var(--muted-foreground)' }}>
                Auto-discovered pipelines. Uncheck any that are not representative.
              </p>
            </div>
          </div>
        )

      case 3:
        return (
          <div className="space-y-4">
            <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
              Choose how tool data influences final maturity scores. This can be changed by an admin before review.
            </p>
            {([
              {
                key: 'context',
                label: 'Context only',
                desc: 'Tool data guides questions and confidence but does not directly influence maturity scores. Team conversation is the primary input.',
              },
              {
                key: 'balanced',
                label: 'Balanced',
                badge: 'Recommended',
                desc: 'Tool evidence contributes to scoring when relevant, while team explanations provide context and can raise or lower preliminary scores.',
              },
              {
                key: 'evidence',
                label: 'Evidence-led',
                desc: 'Observed tool behavior has stronger scoring influence. Conflicting claims between tool evidence and team statements require clarification.',
              },
            ] as { key: typeof influence; label: string; badge?: string; desc: string }[]).map(opt => {
              const active = influence === opt.key
              return (
                <button
                  key={opt.key}
                  onClick={() => setInfluence(opt.key)}
                  className="w-full text-left rounded-xl p-4 transition-base"
                  style={{
                    background: active ? (dark ? '#0f1d40' : '#eef3fa') : 'var(--card)',
                    border: `2px solid ${active ? 'var(--primary)' : cardBorder}`,
                  }}
                >
                  <div className="flex items-center gap-2 mb-1.5">
                    <div
                      className="w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0"
                      style={{ borderColor: active ? 'var(--primary)' : 'var(--border)' }}
                    >
                      {active && <div className="w-2 h-2 rounded-full" style={{ background: 'var(--primary)' }} />}
                    </div>
                    <span className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>{opt.label}</span>
                    {opt.badge && (
                      <span
                        className="text-xs px-2 py-0.5 rounded-full font-medium"
                        style={{ background: '#d1fae5', color: '#065f46' }}
                      >
                        {opt.badge}
                      </span>
                    )}
                  </div>
                  <p className="text-sm ml-6" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                    {opt.desc}
                  </p>
                </button>
              )
            })}
          </div>
        )

      case 4:
        return (
          <div className="space-y-4">
            <p className="text-sm mb-2" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
              How will the team participate in this assessment?
            </p>
            {([
              { key: 'room', icon: <Laptop size={16} />, label: 'In-room workshop', desc: 'One facilitator leads the session. Team members speak through a shared microphone.' },
              { key: 'room-remote', icon: <Globe size={16} />, label: 'In-room workshop with remote contributors', desc: 'Same as above, with additional contributors joining via a signed invite link.' },
              { key: 'later', icon: <Users size={16} />, label: 'Save setup and start later', desc: 'Complete setup now and begin the interview at a later time. Invite links can be generated now.' },
            ] as { key: typeof participation; icon: React.ReactNode; label: string; desc: string }[]).map(opt => {
              const active = participation === opt.key
              return (
                <button
                  key={opt.key}
                  onClick={() => setParticipation(opt.key)}
                  className="w-full text-left rounded-xl p-4 transition-base"
                  style={{
                    background: active ? (dark ? '#0f1d40' : '#eef3fa') : 'var(--card)',
                    border: `2px solid ${active ? 'var(--primary)' : cardBorder}`,
                  }}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className="w-4 h-4 rounded-full border-2 mt-0.5 flex items-center justify-center shrink-0"
                      style={{ borderColor: active ? 'var(--primary)' : 'var(--border)' }}
                    >
                      {active && <div className="w-2 h-2 rounded-full" style={{ background: 'var(--primary)' }} />}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span style={{ color: 'var(--muted-foreground)' }}>{opt.icon}</span>
                        <span className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>{opt.label}</span>
                      </div>
                      <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>{opt.desc}</p>
                    </div>
                  </div>
                </button>
              )
            })}

            {(participation === 'room-remote' || participation === 'later') && (
              <div
                className="rounded-xl p-5 animate-fade-in"
                style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
              >
                <p className="text-sm font-semibold mb-3" style={{ color: 'var(--foreground)' }}>Remote contributor invite</p>
                <div
                  className="flex items-center justify-between rounded-lg px-3 py-2.5 mb-3"
                  style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}
                >
                  <span className="text-xs font-mono" style={{ color: 'var(--muted-foreground)', letterSpacing: '0.01em' }}>
                    https://safe-assess.io/join/{teamName.toLowerCase().replace(/\s+/g, '-').slice(0, 24) || 'team'}-invite
                  </span>
                  <button
                    onClick={copyLink}
                    className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded ml-2 transition-base shrink-0"
                    style={{
                      background: linkCopied ? '#d1fae5' : 'var(--primary)',
                      color: linkCopied ? '#065f46' : '#fff',
                    }}
                  >
                    <Copy size={11} />
                    {linkCopied ? 'Copied' : 'Copy'}
                  </button>
                </div>
                <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--muted-foreground)' }}>
                  <span>Expires in 7 days</span>
                  <span>·</span>
                  <span>0 contributors joined</span>
                </div>
              </div>
            )}
          </div>
        )

      default:
        return null
    }
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      <div className="max-w-2xl mx-auto px-6 py-10">
        <div className="flex items-center gap-2 text-xs font-medium mb-6" style={{ color: 'var(--muted-foreground)' }}>
          <button onClick={() => onNavigate('welcome')} className="hover:underline">Assessments</button>
          <span>/</span>
          <span>New assessment setup</span>
        </div>

        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-semibold" style={{ color: 'var(--foreground)' }}>
              {STEP_TITLES[step]}
            </h1>
            <p className="text-sm mt-1" style={{ color: 'var(--muted-foreground)' }}>
              Step {step + 1} of {STEP_TITLES.length}
            </p>
          </div>
          <StepIndicator current={step} total={STEP_TITLES.length} dark={dark} />
        </div>

        {error && (
          <div className="mb-4 text-sm" style={{ color: '#dc2626' }}>{error}</div>
        )}

        <div
          className="rounded-xl p-6 mb-6"
          style={{ background: cardBg, border: `1px solid ${cardBorder}` }}
        >
          {renderStep()}
        </div>

        <div className="flex items-center justify-between">
          <button
            onClick={() => step > 0 ? setStep(s => s - 1) : onNavigate('welcome')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-base"
            style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
            onMouseLeave={e => (e.currentTarget.style.borderColor = cardBorder)}
          >
            <ChevronLeft size={15} />
            {step === 0 ? 'Cancel' : 'Back'}
          </button>
          <button
            disabled={submitting}
            onClick={() => {
              if (step < STEP_TITLES.length - 1) setStep(s => s + 1)
              else void finishSetup()
            }}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-base"
            style={{ background: 'var(--primary)', color: '#fff', opacity: submitting ? 0.7 : 1 }}
            onMouseEnter={e => (e.currentTarget.style.opacity = submitting ? '0.7' : '0.88')}
            onMouseLeave={e => (e.currentTarget.style.opacity = submitting ? '0.7' : '1')}
          >
            {step < STEP_TITLES.length - 1 ? 'Continue' : submitting ? 'Collecting…' : 'Review evidence'}
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}
