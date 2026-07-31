import { useState } from 'react'
import { Eye, EyeOff, CheckCircle2, XCircle, RefreshCw, AlertCircle, Lock, Info } from 'lucide-react'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
}

type ConnStatus = 'connected' | 'error' | 'idle' | 'testing'

function MaskedInput({ value, placeholder }: { value: string; placeholder: string }) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        defaultValue={value}
        placeholder={placeholder}
        className="w-full rounded-lg px-3 py-2.5 text-sm pr-10 outline-none transition-base"
        style={{
          background: 'var(--muted)',
          border: '1px solid var(--border)',
          color: 'var(--foreground)',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 13,
        }}
        onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
        onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
      />
      <button
        className="absolute right-3 top-1/2 -translate-y-1/2 transition-base"
        style={{ color: 'var(--muted-foreground)' }}
        onClick={() => setShow(s => !s)}
        type="button"
      >
        {show ? <EyeOff size={15} /> : <Eye size={15} />}
      </button>
    </div>
  )
}

function StatusBadge({ status }: { status: ConnStatus }) {
  if (status === 'connected') return (
    <span className="flex items-center gap-1.5 text-xs font-medium" style={{ color: '#059669' }}>
      <CheckCircle2 size={13} /> Connected · Validated 2 hours ago
    </span>
  )
  if (status === 'error') return (
    <span className="flex items-center gap-1.5 text-xs font-medium" style={{ color: '#dc2626' }}>
      <XCircle size={13} /> Connection failed — check credentials
    </span>
  )
  if (status === 'testing') return (
    <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--muted-foreground)' }}>
      <RefreshCw size={13} className="animate-spin" /> Testing connection…
    </span>
  )
  return (
    <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--muted-foreground)' }}>
      <AlertCircle size={13} /> Not yet tested
    </span>
  )
}

function IntegrationCard({
  title,
  logo,
  fields,
  status,
  onTest,
  dark,
  permissionsNote,
}: {
  title: string
  logo: string
  fields: { label: string; type: 'text' | 'secret'; placeholder: string; value: string }[]
  status: ConnStatus
  onTest: () => void
  dark: boolean
  permissionsNote: string
}) {
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'
  return (
    <div
      className="rounded-xl p-6"
      style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
    >
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold"
            style={{ background: dark ? '#1a2540' : '#eef3fa', color: 'var(--primary)' }}
          >
            {logo}
          </div>
          <div>
            <h3 className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>{title}</h3>
            <StatusBadge status={status} />
          </div>
        </div>
        {status === 'connected' && (
          <div
            className="w-2.5 h-2.5 rounded-full"
            style={{ background: '#10b981', boxShadow: '0 0 0 3px rgba(16,185,129,0.2)' }}
          />
        )}
      </div>

      <div className="space-y-4">
        {fields.map(f => (
          <div key={f.label}>
            <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>
              {f.label}
            </label>
            {f.type === 'secret' ? (
              <MaskedInput value={f.value} placeholder={f.placeholder} />
            ) : (
              <input
                type="text"
                defaultValue={f.value}
                placeholder={f.placeholder}
                className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-base"
                style={{
                  background: 'var(--muted)',
                  border: '1px solid var(--border)',
                  color: 'var(--foreground)',
                }}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
                onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
              />
            )}
          </div>
        ))}
      </div>

      <div
        className="mt-4 rounded-lg p-3 flex items-start gap-2"
        style={{ background: dark ? '#141f35' : '#f8fafc', border: `1px solid ${cardBorder}` }}
      >
        <Lock size={13} style={{ color: 'var(--muted-foreground)', marginTop: 1, flexShrink: 0 }} />
        <p className="text-xs leading-relaxed" style={{ color: 'var(--muted-foreground)' }}>
          {permissionsNote}
        </p>
      </div>

      <div className="flex items-center justify-between mt-4">
        <button
          onClick={onTest}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-base"
          style={{
            background: 'var(--primary)',
            color: '#fff',
          }}
          onMouseEnter={e => (e.currentTarget.style.opacity = '0.88')}
          onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
        >
          Test connection
        </button>
        <button
          className="text-sm transition-base px-3 py-2 rounded-lg"
          style={{ color: 'var(--muted-foreground)' }}
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--muted)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
        >
          Save
        </button>
      </div>
    </div>
  )
}

export default function Integrations({ dark, onNavigate }: Props) {
  const [jiraStatus, setJiraStatus] = useState<ConnStatus>('connected')
  const [azdoStatus, setAzdoStatus] = useState<ConnStatus>('connected')
  const [refreshing, setRefreshing] = useState(false)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  function handleTest(which: 'jira' | 'azdo') {
    if (which === 'jira') {
      setJiraStatus('testing')
      setTimeout(() => setJiraStatus('connected'), 1800)
    } else {
      setAzdoStatus('testing')
      setTimeout(() => setAzdoStatus('connected'), 1800)
    }
  }

  function handleRefresh() {
    setRefreshing(true)
    setTimeout(() => setRefreshing(false), 2000)
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      <div className="max-w-3xl mx-auto px-6 py-10">
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs font-medium mb-3" style={{ color: 'var(--muted-foreground)' }}>
            <button onClick={() => onNavigate('welcome')} className="hover:underline">Admin</button>
            <span>/</span>
            <span>Integrations</span>
          </div>
          <h1 className="text-2xl font-semibold mb-2" style={{ color: 'var(--foreground)' }}>Integrations</h1>
          <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
            Configure the delivery data sources used for all assessments. Credentials are stored server-side and never exposed to participants.
          </p>
        </div>

        <div
          className="rounded-xl p-4 mb-6 flex items-start gap-3"
          style={{ background: dark ? '#141f35' : '#f0fdfc', border: `1px solid ${dark ? '#1e3358' : '#ccfbf7'}` }}
        >
          <Info size={15} style={{ color: '#0f8b8d', marginTop: 1, flexShrink: 0 }} />
          <p className="text-sm" style={{ color: dark ? '#5de8e0' : '#0e7170', lineHeight: 1.6 }}>
            The pilot supports one Jira Cloud environment and one Azure DevOps Services environment. Both must be configured before starting an assessment.
          </p>
        </div>

        <div className="space-y-5 mb-6">
          <IntegrationCard
            title="Jira Cloud"
            logo="JC"
            dark={dark}
            status={jiraStatus}
            onTest={() => handleTest('jira')}
            permissionsNote="Requires read-only access: browse_projects, view_workflow_transition. Service account credentials are encrypted at rest and never displayed in full after saving."
            fields={[
              { label: 'Jira site URL', type: 'text', placeholder: 'https://yourorg.atlassian.net', value: 'https://claimsco.atlassian.net' },
              { label: 'Service account email', type: 'text', placeholder: 'svc-maturity@yourorg.com', value: 'svc-maturity@claimsco.com' },
              { label: 'API token', type: 'secret', placeholder: 'Enter API token…', value: 'ATATTxxxxxxxxxxxxxxxx' },
            ]}
          />
          <IntegrationCard
            title="Azure DevOps Services"
            logo="AZ"
            dark={dark}
            status={azdoStatus}
            onTest={() => handleTest('azdo')}
            permissionsNote="Requires read-only PAT scopes: Code (Read), Build (Read), Release (Read). Tokens are never echoed back after initial save."
            fields={[
              { label: 'Organization URL', type: 'text', placeholder: 'https://dev.azure.com/yourorg', value: 'https://dev.azure.com/claimsco' },
              { label: 'Personal access token', type: 'secret', placeholder: 'Enter PAT…', value: 'xxxxxxxxxxxxxxxxxxxxxxxx' },
            ]}
          />
        </div>

        <div
          className="rounded-xl p-5 flex items-center justify-between"
          style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
        >
          <div>
            <p className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>Refresh available projects and repositories</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
              Fetches the current list of Jira projects and ADO repositories for use in setup wizards.
            </p>
          </div>
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-base ml-4 shrink-0"
            style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
            onMouseLeave={e => (e.currentTarget.style.borderColor = cardBorder)}
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>
    </div>
  )
}
