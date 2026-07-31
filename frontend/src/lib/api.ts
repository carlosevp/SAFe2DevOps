const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  status: number
  code: string
  details: unknown

  constructor(status: number, code: string, message: string, details: unknown = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {})
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...init,
    headers,
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    const error = typeof payload === 'object' && payload && 'error' in payload
      ? (payload as { error: { code?: string; message?: string; details?: unknown } }).error
      : undefined
    throw new ApiError(
      response.status,
      error?.code || `http_${response.status}`,
      error?.message || 'Request failed',
      error?.details || {},
    )
  }

  return payload as T
}

export type IntegrationStatus = {
  jira_site_url: string | null
  jira_service_account_email: string | null
  jira_token_configured: boolean
  jira_status: string
  jira_last_validated_at: string | null
  jira_last_error: string | null
  ado_org_url: string | null
  ado_pat_configured: boolean
  ado_status: string
  ado_last_validated_at: string | null
  ado_last_error: string | null
  catalog_refreshed_at: string | null
  jira_permissions_note: string
  ado_permissions_note: string
  provider_mode: string
}

export type CatalogProject = { id: string; key?: string | null; name: string }
export type CatalogRepo = { id: string; name: string; default_branch: string }
export type CatalogPipeline = { id: string; name: string; runs?: number | null; success_rate?: string | null }

export type AssessmentSummary = {
  id: string
  team_name: string
  product_service_name: string
  owner_name: string
  owner_email: string
  lookback_days: number
  evidence_influence_mode: string
  participation_mode: string
  status: string
  created_at: string
  updated_at: string
}

export type EvidenceMetric = {
  key: string
  label: string
  value_text: string
  value_numeric?: number | null
  source_system: string
  trend?: string | null
  freshness_label?: string | null
}

export type EvidenceSnapshot = {
  id: string
  assessment_id: string
  lookback_days: number
  collected_at: string
  jira_project_key: string
  ado_repository_name: string
  provenance_summary: string
  payload_ref?: string | null
  payload_checksum?: string | null
  quality: string
  immutable: boolean
  is_representative: boolean
  metrics: EvidenceMetric[]
  limitations: { code: string; message: string; source_system?: string | null }[]
  exclusions: string[]
}

export function getIntegrations() {
  return apiFetch<IntegrationStatus>('/api/integrations')
}

export function saveJiraCredentials(body: { site_url: string; service_account_email: string; api_token?: string }) {
  return apiFetch<IntegrationStatus>('/api/integrations/jira', { method: 'PUT', body: JSON.stringify(body) })
}

export function saveAdoCredentials(body: { org_url: string; pat?: string }) {
  return apiFetch<IntegrationStatus>('/api/integrations/ado', { method: 'PUT', body: JSON.stringify(body) })
}

export function testJiraConnection() {
  return apiFetch<{ ok: boolean; message: string; tested_at: string }>('/api/integrations/jira/test', { method: 'POST' })
}

export function testAdoConnection() {
  return apiFetch<{ ok: boolean; message: string; tested_at: string }>('/api/integrations/ado/test', { method: 'POST' })
}

export function refreshCatalog() {
  return apiFetch<IntegrationStatus>('/api/integrations/catalog/refresh', { method: 'POST' })
}

export function listJiraProjects() {
  return apiFetch<CatalogProject[]>('/api/integrations/catalog/jira/projects')
}

export function listJiraBoards(projectKey: string) {
  return apiFetch<CatalogProject[]>(`/api/integrations/catalog/jira/projects/${encodeURIComponent(projectKey)}/boards`)
}

export function listAdoProjects() {
  return apiFetch<CatalogProject[]>('/api/integrations/catalog/ado/projects')
}

export function listAdoRepos(projectId: string) {
  return apiFetch<CatalogRepo[]>(`/api/integrations/catalog/ado/projects/${encodeURIComponent(projectId)}/repositories`)
}

export function listAdoBranches(projectId: string, repoId: string) {
  return apiFetch<string[]>(
    `/api/integrations/catalog/ado/projects/${encodeURIComponent(projectId)}/repositories/${encodeURIComponent(repoId)}/branches`,
  )
}

export function listAdoPipelines(projectId: string, repositoryName?: string) {
  const q = repositoryName ? `?repository_name=${encodeURIComponent(repositoryName)}` : ''
  return apiFetch<CatalogPipeline[]>(`/api/integrations/catalog/ado/projects/${encodeURIComponent(projectId)}/pipelines${q}`)
}

export function createAssessment(body: {
  team_name: string
  product_service_name: string
  description?: string
  value_stream?: string
  owner_name: string
  owner_email: string
  lookback_days: number
  evidence_influence_mode: 'context_only' | 'balanced' | 'evidence_led'
  participation_mode: 'facilitated_room' | 'hybrid_remote' | 'remote_only'
}) {
  return apiFetch<AssessmentSummary>('/api/assessments', { method: 'POST', body: JSON.stringify(body) })
}

export function setSourceSelection(assessmentId: string, body: Record<string, unknown>) {
  return apiFetch<AssessmentSummary>(`/api/assessments/${assessmentId}/source-selection`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function collectEvidence(assessmentId: string, refresh = false) {
  const q = refresh ? '?refresh=true' : ''
  return apiFetch<EvidenceSnapshot>(`/api/assessments/${assessmentId}/evidence/collect${q}`, { method: 'POST' })
}

export function getLatestEvidence(assessmentId: string) {
  return apiFetch<EvidenceSnapshot>(`/api/assessments/${assessmentId}/evidence/latest`)
}

export function applyEvidenceExclusions(assessmentId: string, snapshotId: string, exclusions: string[]) {
  return apiFetch<EvidenceSnapshot>(`/api/assessments/${assessmentId}/evidence/${snapshotId}/exclusions`, {
    method: 'POST',
    body: JSON.stringify({ exclusions }),
  })
}

export function confirmEvidence(assessmentId: string, snapshotId: string) {
  return apiFetch<EvidenceSnapshot>(`/api/assessments/${assessmentId}/evidence/${snapshotId}/confirm`, {
    method: 'POST',
  })
}

export type CoverageStateApi = 'not_discussed' | 'partial' | 'sufficient' | 'clarify'

export type InterviewPractice = {
  practice_key: string
  practice_name: string
  domain_key: string
  domain_short_name: string
  coverage_state: CoverageStateApi
  open_gaps: string[]
}

export type InterviewSession = {
  assessment_id: string
  team_name: string
  product_service_name: string
  status: string
  interview_status: string
  current_question: string
  why_asking: string
  evidence_context: string
  topic_label: string
  pending_clarification: string | null
  draft_answer_text: string
  last_outcome: 'none' | 'clarify' | 'sufficient'
  overall_coverage_summary: string
  coverage_confirmation: string | null
  turn_count: number
  answered_turn_count: number
  completion_eligible: boolean
  completion_blockers: string[]
  practices: InterviewPractice[]
  telemetry: {
    provider: string
    model: string
    reasoning_effort: string
    latency_ms?: number | null
    input_tokens?: number | null
    output_tokens?: number | null
    prompt_config_version: string
  } | null
}

export type TurnSubmitResult = {
  session: InterviewSession
  analysis_summary: string
  claims: string[]
  covered_practices: string[]
  partial_practices: string[]
  clarify_practices: string[]
  duplicated: boolean
}

export type CheckpointData = {
  assessment_id: string
  headline: string
  summary: string
  sufficient_count: number
  partial_count: number
  not_discussed_count: number
  clarify_count: number
  covered: { label: string; domain: string }[]
  remaining: { label: string; domain: string; priority: string }[]
  completion_eligible: boolean
  completion_blockers: string[]
  impact_note: string
}

export type AiSettings = {
  assessment_model: string
  reasoning_effort: string
  interview_provider: 'mock' | 'live'
  transcription_model: string
  prompt_config_version: string
  available_models: string[]
  available_reasoning_efforts: string[]
  updated_at: string | null
}

export function startInterview(assessmentId: string) {
  return apiFetch<{ session: InterviewSession }>(`/api/assessments/${assessmentId}/interview/start`, { method: 'POST' })
}

export function getInterview(assessmentId: string) {
  return apiFetch<InterviewSession>(`/api/assessments/${assessmentId}/interview`)
}

export function resumeInterview(assessmentId: string) {
  return apiFetch<InterviewSession>(`/api/assessments/${assessmentId}/interview/resume`, { method: 'POST' })
}

export function saveInterview(assessmentId: string, draft_answer_text = '') {
  return apiFetch<InterviewSession>(`/api/assessments/${assessmentId}/interview/save`, {
    method: 'POST',
    body: JSON.stringify({ draft_answer_text }),
  })
}

export function saveInterviewDraft(assessmentId: string, draft_answer_text: string) {
  return apiFetch<InterviewSession>(`/api/assessments/${assessmentId}/interview/draft`, {
    method: 'PUT',
    body: JSON.stringify({ draft_answer_text }),
  })
}

export function submitInterviewTurn(
  assessmentId: string,
  body: { answer_text: string; idempotency_key: string; is_clarification?: boolean },
) {
  return apiFetch<TurnSubmitResult>(`/api/assessments/${assessmentId}/interview/turns`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getInterviewCheckpoint(assessmentId: string) {
  return apiFetch<CheckpointData>(`/api/assessments/${assessmentId}/interview/checkpoint`)
}

export function completeInterview(assessmentId: string) {
  return apiFetch<InterviewSession>(`/api/assessments/${assessmentId}/interview/complete`, { method: 'POST' })
}

export function getAiSettings() {
  return apiFetch<AiSettings>('/api/ai-settings')
}

export function updateAiSettings(body: {
  assessment_model?: string
  reasoning_effort?: string
  interview_provider?: 'mock' | 'live'
}) {
  return apiFetch<AiSettings>('/api/ai-settings', { method: 'PUT', body: JSON.stringify(body) })
}
