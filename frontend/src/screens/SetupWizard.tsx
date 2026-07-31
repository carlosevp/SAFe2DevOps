import { useState } from 'react'
import { ChevronRight, ChevronLeft, Check, Info, Copy, Users, Laptop, Globe } from 'lucide-react'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
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

function Input({ placeholder, defaultValue, hint }: { placeholder: string; defaultValue?: string; hint?: string }) {
  return (
    <div>
      <input
        type="text"
        placeholder={placeholder}
        defaultValue={defaultValue}
        className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-base"
        style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
        onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
        onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
      />
      {hint && <p className="text-xs mt-1.5" style={{ color: 'var(--muted-foreground)' }}>{hint}</p>}
    </div>
  )
}

function Select({ options, defaultValue }: { options: string[]; defaultValue?: string }) {
  return (
    <select
      className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-base appearance-none"
      style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
      defaultValue={defaultValue}
      onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
      onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
    >
      {options.map(o => <option key={o}>{o}</option>)}
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

export default function SetupWizard({ dark, onNavigate }: Props) {
  const [step, setStep] = useState(0)
  const [lookback, setLookback] = useState(90)
  const [influence, setInfluence] = useState<'context' | 'balanced' | 'evidence'>('balanced')
  const [participation, setParticipation] = useState<'room' | 'room-remote' | 'later'>('room-remote')
  const [linkCopied, setLinkCopied] = useState(false)

  const cardBorder = dark ? '#1e3358' : '#e2e8f0'
  const cardBg = 'var(--card)'

  function copyLink() {
    setLinkCopied(true)
    setTimeout(() => setLinkCopied(false), 2000)
  }

  const scopeStatement = `Assess the Claims Integration team using the CLAIM Jira project and claims-api repository as representative evidence from the last ${lookback} days.`

  function renderStep() {
    switch (step) {
      case 0:
        return (
          <div className="space-y-5">
            <div className="grid md:grid-cols-2 gap-4">
              <div><Label>Team name</Label><Input placeholder="e.g. Claims Integration" defaultValue="Claims Integration" /></div>
              <div><Label>Product, application, or service</Label><Input placeholder="e.g. Claims API" defaultValue="Claims API" /></div>
            </div>
            <div><Label>Brief description (optional)</Label><Input placeholder="What does this team deliver?" defaultValue="REST API for insurance claims processing, consumed by the claims portal." /></div>
            <div className="grid md:grid-cols-2 gap-4">
              <div><Label>Assessment owner</Label><Input placeholder="Name or email" defaultValue="Jordan Mills" /></div>
              <div><Label>Value stream (optional)</Label><Input placeholder="e.g. Claims Processing" /></div>
            </div>

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
            <div><Label>Jira project</Label><Select options={['CLAIM — Claims Integration', 'PORTAL — Claims Portal', 'INFRA — Infrastructure']} defaultValue="CLAIM — Claims Integration" /></div>
            <div><Label>Board (optional)</Label><Select options={['— None —', 'Claims Integration Sprint Board', 'Kanban Board']} /></div>
            <div>
              <Label>JQL refinement (optional)</Label>
              <Input placeholder='project = CLAIM AND type != Epic AND created >= -90d' />
              <p className="text-xs mt-1.5" style={{ color: 'var(--muted-foreground)' }}>
                Advanced filter. Leave blank to use all issues in the selected project within the lookback period.
              </p>
            </div>

            <div
              className="rounded-xl p-4 border"
              style={{ background: 'var(--card)', borderColor: cardBorder }}
            >
              <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: 'var(--muted-foreground)' }}>
                Activity preview · Last 90 days
              </p>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: 'Issues completed', value: '67' },
                  { label: 'Bugs created', value: '11' },
                  { label: 'Avg cycle time', value: '6.4d' },
                ].map(m => (
                  <div key={m.label} className="text-center p-3 rounded-lg" style={{ background: 'var(--muted)' }}>
                    <div className="text-xl font-semibold font-mono" style={{ color: 'var(--foreground)' }}>{m.value}</div>
                    <div className="text-xs mt-1" style={{ color: 'var(--muted-foreground)' }}>{m.label}</div>
                  </div>
                ))}
              </div>
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
            <div><Label>Project</Label><Select options={['Claims Co', 'InfraTeam', 'Platform Services']} defaultValue="Claims Co" /></div>
            <div><Label>Repository</Label><Select options={['claims-api', 'claims-portal', 'claims-shared-libs']} defaultValue="claims-api" /></div>
            <div><Label>Default branch</Label><Select options={['main', 'master', 'develop']} defaultValue="main" /></div>
            <div>
              <Label>Pipelines</Label>
              <div className="space-y-2">
                {[
                  { name: 'claims-api-CI', runs: 61, success: '87%', confirmed: true },
                  { name: 'claims-api-CD-prod', runs: 31, success: '94%', confirmed: true },
                  { name: 'claims-api-PR-validation', runs: 44, success: '91%', confirmed: true },
                ].map(p => (
                  <div
                    key={p.name}
                    className="rounded-lg px-3 py-2.5 flex items-center justify-between"
                    style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}
                  >
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ background: '#10b981' }} />
                      <span className="text-sm font-mono" style={{ color: 'var(--foreground)', fontSize: 12 }}>{p.name}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--muted-foreground)' }}>
                      <span>{p.runs} runs</span>
                      <span style={{ color: '#10b981', fontWeight: 500 }}>{p.success}</span>
                      <input type="checkbox" defaultChecked={p.confirmed} style={{ accentColor: 'var(--primary)' }} />
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
                    https://safe-assess.io/join/claims-int-2024-a7f3b
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
        {/* Breadcrumb */}
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
            onClick={() => {
              if (step < STEP_TITLES.length - 1) setStep(s => s + 1)
              else onNavigate('evidence')
            }}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-base"
            style={{ background: 'var(--primary)', color: '#fff' }}
            onMouseEnter={e => (e.currentTarget.style.opacity = '0.88')}
            onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
          >
            {step < STEP_TITLES.length - 1 ? 'Continue' : 'Review evidence'}
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}
