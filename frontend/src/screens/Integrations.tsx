import { useEffect, useState } from 'react'
import { Eye, EyeOff, CheckCircle2, XCircle, RefreshCw, AlertCircle, Lock, Info } from 'lucide-react'
import {
  getIntegrations,
  refreshCatalog,
  saveAdoCredentials,
  saveJiraCredentials,
  testAdoConnection,
  testJiraConnection,
  type IntegrationStatus,
} from '../lib/api'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
}

type ConnStatus = 'connected' | 'error' | 'idle' | 'testing' | 'unknown' | 'failed'

function mapStatus(value?: string | null): ConnStatus {
  if (value === 'connected') return 'connected'
  if (value === 'failed') return 'failed'
  if (value === 'testing') return 'testing'
  if (value === 'unknown') return 'unknown'
  return 'idle'
}

function formatValidated(iso: string | null): string {
  if (!iso) return 'Not yet tested'
  const dt = new Date(iso)
  return `Validated ${dt.toLocaleString()}`
}

function FieldInput({
  value,
  placeholder,
  secret,
  onChange,
}: {
  value: string
  placeholder: string
  secret?: boolean
  onChange: (v: string) => void
}) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input
        type={secret && !show ? 'password' : 'text'}
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-lg px-3 py-2.5 text-sm pr-10 outline-none transition-base"
        style={{
          background: 'var(--muted)',
          border: '1px solid var(--border)',
          color: 'var(--foreground)',
          fontFamily: secret ? 'JetBrains Mono, monospace' : undefined,
          fontSize: secret ? 13 : undefined,
        }}
        onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
        onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
      />
      {secret && (
        <button
          className="absolute right-3 top-1/2 -translate-y-1/2 transition-base"
          style={{ color: 'var(--muted-foreground)' }}
          onClick={() => setShow(s => !s)}
          type="button"
        >
          {show ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
      )}
    </div>
  )
}

function StatusBadge({ status, validatedAt }: { status: ConnStatus; validatedAt: string | null }) {
  if (status === 'connected') {
    return (
      <span className="flex items-center gap-1.5 text-xs font-medium" style={{ color: '#059669' }}>
        <CheckCircle2 size={13} /> Connected · {formatValidated(validatedAt)}
      </span>
    )
  }
  if (status === 'failed' || status === 'error') {
    return (
      <span className="flex items-center gap-1.5 text-xs font-medium" style={{ color: '#dc2626' }}>
        <XCircle size={13} /> Connection failed — check credentials
      </span>
    )
  }
  if (status === 'testing') {
    return (
      <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--muted-foreground)' }}>
        <RefreshCw size={13} className="animate-spin" /> Testing connection…
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--muted-foreground)' }}>
      <AlertCircle size={13} /> Not yet tested
    </span>
  )
}

export default function Integrations({ dark, onNavigate }: Props) {
  const [status, setStatus] = useState<IntegrationStatus | null>(null)
  const [jiraStatus, setJiraStatus] = useState<ConnStatus>('idle')
  const [adoStatus, setAdoStatus] = useState<ConnStatus>('idle')
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [jiraUrl, setJiraUrl] = useState('')
  const [jiraEmail, setJiraEmail] = useState('')
  const [jiraToken, setJiraToken] = useState('')
  const [adoUrl, setAdoUrl] = useState('')
  const [adoPat, setAdoPat] = useState('')
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  useEffect(() => {
    getIntegrations()
      .then(data => {
        setStatus(data)
        setJiraStatus(mapStatus(data.jira_status))
        setAdoStatus(mapStatus(data.ado_status))
        setJiraUrl(data.jira_site_url || '')
        setJiraEmail(data.jira_service_account_email || '')
        setAdoUrl(data.ado_org_url || '')
        // Secrets never returned after save.
        setJiraToken('')
        setAdoPat('')
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load integrations'))
  }, [])

  async function saveJira() {
    setError(null)
    const data = await saveJiraCredentials({
      site_url: jiraUrl,
      service_account_email: jiraEmail,
      api_token: jiraToken || undefined,
    })
    setStatus(data)
    setJiraStatus(mapStatus(data.jira_status))
    setJiraToken('')
  }

  async function saveAdo() {
    setError(null)
    const data = await saveAdoCredentials({
      org_url: adoUrl,
      pat: adoPat || undefined,
    })
    setStatus(data)
    setAdoStatus(mapStatus(data.ado_status))
    setAdoPat('')
  }

  async function handleTest(which: 'jira' | 'azdo') {
    setError(null)
    try {
      if (which === 'jira') {
        setJiraStatus('testing')
        await saveJira()
        await testJiraConnection()
        const data = await getIntegrations()
        setStatus(data)
        setJiraStatus(mapStatus(data.jira_status))
      } else {
        setAdoStatus('testing')
        await saveAdo()
        await testAdoConnection()
        const data = await getIntegrations()
        setStatus(data)
        setAdoStatus(mapStatus(data.ado_status))
      }
    } catch (err) {
      if (which === 'jira') setJiraStatus('failed')
      else setAdoStatus('failed')
      setError(err instanceof Error ? err.message : 'Connection test failed')
    }
  }

  async function handleRefresh() {
    setRefreshing(true)
    setError(null)
    try {
      const data = await refreshCatalog()
      setStatus(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Catalog refresh failed')
    } finally {
      setRefreshing(false)
    }
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
            {status?.provider_mode === 'mock' ? ' Mock providers are active for local/demo use.' : ''}
          </p>
        </div>

        {error && (
          <div className="mb-4 text-sm" style={{ color: '#dc2626' }}>{error}</div>
        )}

        <div className="space-y-5 mb-6">
          <div className="rounded-xl p-6" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold" style={{ background: dark ? '#1a2540' : '#eef3fa', color: 'var(--primary)' }}>JC</div>
                <div>
                  <h3 className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>Jira Cloud</h3>
                  <StatusBadge status={jiraStatus} validatedAt={status?.jira_last_validated_at || null} />
                </div>
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>Jira site URL</label>
                <FieldInput value={jiraUrl} placeholder="https://yourorg.atlassian.net" onChange={setJiraUrl} />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>Service account email</label>
                <FieldInput value={jiraEmail} placeholder="svc-maturity@yourorg.com" onChange={setJiraEmail} />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>API token</label>
                <FieldInput
                  value={jiraToken}
                  placeholder={status?.jira_token_configured ? 'Configured — enter new token to rotate' : 'Enter API token…'}
                  secret
                  onChange={setJiraToken}
                />
              </div>
            </div>
            <div className="mt-4 rounded-lg p-3 flex items-start gap-2" style={{ background: dark ? '#141f35' : '#f8fafc', border: `1px solid ${cardBorder}` }}>
              <Lock size={13} style={{ color: 'var(--muted-foreground)', marginTop: 1, flexShrink: 0 }} />
              <p className="text-xs leading-relaxed" style={{ color: 'var(--muted-foreground)' }}>
                {status?.jira_permissions_note || 'Requires read-only Jira access. Tokens are encrypted at rest and never returned after save.'}
              </p>
            </div>
            <div className="flex items-center justify-between mt-4">
              <button onClick={() => handleTest('jira')} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium" style={{ background: 'var(--primary)', color: '#fff' }}>
                Test connection
              </button>
              <button onClick={() => saveJira().catch(err => setError(err.message))} className="text-sm px-3 py-2 rounded-lg" style={{ color: 'var(--muted-foreground)' }}>
                Save
              </button>
            </div>
          </div>

          <div className="rounded-xl p-6" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold" style={{ background: dark ? '#1a2540' : '#eef3fa', color: 'var(--primary)' }}>AZ</div>
                <div>
                  <h3 className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>Azure DevOps Services</h3>
                  <StatusBadge status={adoStatus} validatedAt={status?.ado_last_validated_at || null} />
                </div>
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>Organization URL</label>
                <FieldInput value={adoUrl} placeholder="https://dev.azure.com/yourorg" onChange={setAdoUrl} />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>Personal access token</label>
                <FieldInput
                  value={adoPat}
                  placeholder={status?.ado_pat_configured ? 'Configured — enter new PAT to rotate' : 'Enter PAT…'}
                  secret
                  onChange={setAdoPat}
                />
              </div>
            </div>
            <div className="mt-4 rounded-lg p-3 flex items-start gap-2" style={{ background: dark ? '#141f35' : '#f8fafc', border: `1px solid ${cardBorder}` }}>
              <Lock size={13} style={{ color: 'var(--muted-foreground)', marginTop: 1, flexShrink: 0 }} />
              <p className="text-xs leading-relaxed" style={{ color: 'var(--muted-foreground)' }}>
                {status?.ado_permissions_note || 'Requires read-only PAT scopes. Tokens are never echoed after save.'}
              </p>
            </div>
            <div className="flex items-center justify-between mt-4">
              <button onClick={() => handleTest('azdo')} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium" style={{ background: 'var(--primary)', color: '#fff' }}>
                Test connection
              </button>
              <button onClick={() => saveAdo().catch(err => setError(err.message))} className="text-sm px-3 py-2 rounded-lg" style={{ color: 'var(--muted-foreground)' }}>
                Save
              </button>
            </div>
          </div>
        </div>

        <div className="rounded-xl p-5 flex items-center justify-between" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
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
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>
    </div>
  )
}
