import { useEffect, useState } from 'react'
import { Eye, EyeOff, CheckCircle2, XCircle, RefreshCw, AlertCircle, Lock, Info, Stethoscope } from 'lucide-react'
import {
  getIntegrations,
  refreshCatalog,
  refreshAdoCatalog,
  refreshJiraCatalog,
  runAdoDiagnostics,
  runJiraDiagnostics,
  saveAdoCredentials,
  saveJiraCredentials,
  testAdoConnection,
  testJiraConnection,
  type IntegrationDiagnostics,
  type IntegrationStatus,
} from '../lib/api'
import { availabilityLabel, permissionHint } from '../lib/integrationAvailability'
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

function formatValidated(iso: string | null | undefined): string {
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

function DiagnosticsPanel({ title, data, dark }: { title: string; data: IntegrationDiagnostics | null; dark: boolean }) {
  if (!data) return null
  const row = (label: string, value: string | number | null | undefined) => (
    <div className="flex justify-between gap-3 text-xs py-1" style={{ color: 'var(--muted-foreground)' }}>
      <span>{label}</span>
      <span style={{ color: 'var(--foreground)', textAlign: 'right' }}>{value ?? '—'}</span>
    </div>
  )
  return (
    <div className="mt-4 rounded-lg p-3" style={{ background: dark ? '#141f35' : '#f8fafc', border: '1px solid var(--border)' }}>
      <p className="text-xs font-semibold mb-2" style={{ color: 'var(--foreground)' }}>{title}</p>
      {row('Configured', data.configured_site_or_org)}
      {row('Resolved API host', data.resolved_api_host)}
      {data.credential_mode != null && row('Credential mode', data.credential_mode)}
      {data.cloud_id_present != null && row('Cloud ID present', data.cloud_id_present ? 'yes' : 'no')}
      {row('Identity', data.identity_test)}
      {row('Project catalog', data.project_catalog_test)}
      {data.issue_search_test != null && row('Issue search', data.issue_search_test)}
      {data.repository_test != null && row('Repositories', data.repository_test)}
      {data.pipeline_build_test != null && row('Pipelines/builds', data.pipeline_build_test)}
      {row('Visible projects', data.visible_project_count)}
      {row('Last successful refresh', data.last_successful_refresh_at ? new Date(data.last_successful_refresh_at).toLocaleString() : null)}
      {row('Error category', data.error_category)}
      {data.corrective_action && (
        <p className="text-xs mt-2" style={{ color: dark ? '#5de8e0' : '#0e7170' }}>{data.corrective_action}</p>
      )}
      {data.message && (
        <p className="text-xs mt-1" style={{ color: 'var(--muted-foreground)' }}>{data.message}</p>
      )}
    </div>
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
  const [jiraMode, setJiraMode] = useState<'classic_account_api_token' | 'scoped_service_account_token'>('classic_account_api_token')
  const [jiraCloudId, setJiraCloudId] = useState('')
  const [adoUrl, setAdoUrl] = useState('')
  const [adoPat, setAdoPat] = useState('')
  const [jiraDiag, setJiraDiag] = useState<IntegrationDiagnostics | null>(null)
  const [adoDiag, setAdoDiag] = useState<IntegrationDiagnostics | null>(null)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  useEffect(() => {
    getIntegrations()
      .then(data => {
        setStatus(data)
        setJiraStatus(mapStatus(data.jira_status))
        setAdoStatus(mapStatus(data.ado_status))
        setJiraUrl(data.jira_site_url || '')
        setJiraEmail(data.jira_service_account_email || '')
        setJiraMode((data.jira_credential_mode as typeof jiraMode) || 'classic_account_api_token')
        setJiraCloudId(data.jira_cloud_id || '')
        setAdoUrl(data.ado_org_url || '')
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
      credential_mode: jiraMode,
      cloud_id: jiraCloudId || null,
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
        const result = await testJiraConnection()
        const data = await getIntegrations()
        setStatus(data)
        setJiraStatus(mapStatus(data.jira_status))
        if (result.message) setError(result.ok ? null : result.message)
      } else {
        setAdoStatus('testing')
        await saveAdo()
        const result = await testAdoConnection()
        const data = await getIntegrations()
        setStatus(data)
        setAdoStatus(mapStatus(data.ado_status))
        if (result.message) setError(result.ok ? null : result.message)
      }
    } catch (err) {
      if (which === 'jira') setJiraStatus('failed')
      else setAdoStatus('failed')
      setError(err instanceof Error ? err.message : 'Connection test failed')
    }
  }

  async function handleRefresh(target: 'all' | 'jira' | 'ado' = 'all') {
    setRefreshing(true)
    setError(null)
    try {
      const data =
        target === 'jira'
          ? await refreshJiraCatalog()
          : target === 'ado'
            ? await refreshAdoCatalog()
            : await refreshCatalog()
      setStatus(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Catalog refresh failed')
      const data = await getIntegrations().catch(() => null)
      if (data) setStatus(data)
    } finally {
      setRefreshing(false)
    }
  }

  async function handleDiagnostics(which: 'jira' | 'ado') {
    setError(null)
    try {
      if (which === 'jira') setJiraDiag(await runJiraDiagnostics())
      else setAdoDiag(await runAdoDiagnostics())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Diagnostics failed')
    }
  }

  const jiraHint = permissionHint(
    status?.setup_state?.jira.availability,
    status?.jira_last_error_category || (status?.jira_capabilities?.last_error_category as string | undefined),
  )
  const adoHint = permissionHint(
    status?.setup_state?.ado.availability,
    status?.ado_last_error_category || (status?.ado_capabilities?.last_error_category as string | undefined),
  )

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
            The pilot supports one Jira Cloud environment and one Azure DevOps Services environment.
            Connection tests verify identity; catalog refresh and capability checks verify project/repository access.
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
                  <p className="text-xs mt-1" style={{ color: 'var(--muted-foreground)' }}>
                    Setup: {availabilityLabel(status?.setup_state?.jira.availability)}
                    {status?.jira_catalog_stale ? ' · catalog stale' : ''}
                  </p>
                </div>
              </div>
            </div>
            {jiraHint && (
              <div className="mb-4 text-xs rounded-lg p-3" style={{ background: dark ? '#141f35' : '#fff7ed', color: dark ? '#fdba74' : '#9a3412' }}>
                {jiraHint}
              </div>
            )}
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
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>Credential mode</label>
                <select
                  className="w-full rounded-lg px-3 py-2.5 text-sm outline-none"
                  style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
                  value={jiraMode}
                  onChange={e => setJiraMode(e.target.value as typeof jiraMode)}
                >
                  <option value="classic_account_api_token">Classic account API token (site URL)</option>
                  <option value="scoped_service_account_token">Scoped service-account token (Atlassian gateway)</option>
                </select>
              </div>
              {jiraMode === 'scoped_service_account_token' && (
                <div>
                  <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>Jira cloud ID (optional override)</label>
                  <FieldInput value={jiraCloudId} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" onChange={setJiraCloudId} />
                </div>
              )}
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
            <div className="flex items-center justify-between mt-4 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <button onClick={() => handleTest('jira')} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium" style={{ background: 'var(--primary)', color: '#fff' }}>
                  Test connection
                </button>
                <button onClick={() => handleRefresh('jira')} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}>
                  <RefreshCw size={13} /> Retry catalog
                </button>
                {status?.diagnostics_enabled !== false && (
                  <button onClick={() => void handleDiagnostics('jira')} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}>
                    <Stethoscope size={13} /> View diagnostics
                  </button>
                )}
              </div>
              <button onClick={() => saveJira().catch(err => setError(err.message))} className="text-sm px-3 py-2 rounded-lg" style={{ color: 'var(--muted-foreground)' }}>
                Save
              </button>
            </div>
            <DiagnosticsPanel title="Jira diagnostics" data={jiraDiag} dark={dark} />
          </div>

          <div className="rounded-xl p-6" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center text-sm font-bold" style={{ background: dark ? '#1a2540' : '#eef3fa', color: 'var(--primary)' }}>AZ</div>
                <div>
                  <h3 className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>Azure DevOps Services</h3>
                  <StatusBadge status={adoStatus} validatedAt={status?.ado_last_validated_at || null} />
                  <p className="text-xs mt-1" style={{ color: 'var(--muted-foreground)' }}>
                    Setup: {availabilityLabel(status?.setup_state?.ado.availability)}
                    {status?.ado_catalog_stale ? ' · catalog stale' : ''}
                  </p>
                </div>
              </div>
            </div>
            {adoHint && (
              <div className="mb-4 text-xs rounded-lg p-3" style={{ background: dark ? '#141f35' : '#fff7ed', color: dark ? '#fdba74' : '#9a3412' }}>
                {adoHint}
              </div>
            )}
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
            <div className="flex items-center justify-between mt-4 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <button onClick={() => handleTest('azdo')} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium" style={{ background: 'var(--primary)', color: '#fff' }}>
                  Test connection
                </button>
                <button onClick={() => handleRefresh('ado')} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}>
                  <RefreshCw size={13} /> Retry catalog
                </button>
                {status?.diagnostics_enabled !== false && (
                  <button onClick={() => void handleDiagnostics('ado')} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm" style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}>
                    <Stethoscope size={13} /> View diagnostics
                  </button>
                )}
              </div>
              <button onClick={() => saveAdo().catch(err => setError(err.message))} className="text-sm px-3 py-2 rounded-lg" style={{ color: 'var(--muted-foreground)' }}>
                Save
              </button>
            </div>
            <DiagnosticsPanel title="Azure DevOps diagnostics" data={adoDiag} dark={dark} />
          </div>
        </div>

        <div className="rounded-xl p-5 flex items-center justify-between" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
          <div>
            <p className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>Refresh available projects and repositories</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)' }}>
              Fetches catalogs independently. A transient failure keeps the last successful catalog and marks it stale.
            </p>
          </div>
          <button
            onClick={() => handleRefresh('all')}
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
