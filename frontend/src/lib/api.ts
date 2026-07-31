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
  voice_enabled: boolean
  voice_language: string
  voice_stop_mode: 'manual' | 'vad'
  silence_timeout_ms: number
  max_recording_seconds: number
  retain_source_audio: boolean
  retain_corrected_transcript: boolean
  remote_voice_enabled: boolean
  updated_at: string | null
}

export type RealtimeSessionCredentials = {
  client_secret: string
  expires_at: string
  provider: 'mock' | 'live'
  realtime_calls_url: string
  transcription_model: string
  language: string | null
  stop_mode: 'manual' | 'vad'
  silence_timeout_ms: number
  max_recording_seconds: number
  voice_enabled: boolean
  session_config: Record<string, unknown>
  privacy: {
    retain_source_audio: boolean
    retain_corrected_transcript: boolean
    storage_mode: string
    privacy_notice: string
  }
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
  transcription_model?: string
  voice_enabled?: boolean
  voice_language?: string
  voice_stop_mode?: 'manual' | 'vad'
  silence_timeout_ms?: number
  max_recording_seconds?: number
  retain_source_audio?: boolean
  retain_corrected_transcript?: boolean
  remote_voice_enabled?: boolean
}) {
  return apiFetch<AiSettings>('/api/ai-settings', { method: 'PUT', body: JSON.stringify(body) })
}

export function createRealtimeSession() {
  return apiFetch<RealtimeSessionCredentials>('/api/voice/realtime-session', { method: 'POST' })
}

export function registerTempVoiceAudio(assessmentId?: string | null) {
  return apiFetch<{ id: string; path_label: string; retained: boolean; expires_at: string; cleaned_up: boolean }>(
    '/api/voice/audio/temp',
    {
      method: 'POST',
      body: JSON.stringify({ assessment_id: assessmentId || null, filename: 'capture.webm' }),
    },
  )
}

export function cleanupTempVoiceAudio(audioId: string, force = false) {
  const q = force ? '?force=true' : ''
  return apiFetch<{ id: string; cleaned_up: boolean; removed: boolean }>(`/api/voice/audio/${audioId}${q}`, {
    method: 'DELETE',
  })
}

export type RemoteInvite = {
  jti: string
  invite_url: string
  expires_at: string
  revoked: boolean
  created_at?: string | null
}

export type RemoteSettings = {
  assessment_id: string
  remote_participation_enabled: boolean
  active_invite: RemoteInvite | null
  pending_count: number
}

export type RemoteContribution = {
  id: string
  contributor_name: string
  contributor_email: string | null
  timestamp: string
  topic: string
  question_text: string
  body: string
  preview: string
  status: string
  has_attachment: boolean
  attachment_filename?: string | null
  attachment_content_type?: string | null
  affected_practices: string[]
  interview_turn_id?: string | null
}

export type RemoteTopic = {
  team_name: string
  assessment_name: string
  topic_label: string
  question_text: string
  evidence_context: string
  remote_participation_enabled: boolean
  invite_valid: boolean
}

export type RemoteJoinResult = {
  contributor_id: string
  display_name: string
  email: string
  team_name: string
  assessment_name: string
  topic_label: string
  question_text: string
  evidence_context: string
}

export function getRemoteSettings(assessmentId: string) {
  return apiFetch<RemoteSettings>(`/api/assessments/${assessmentId}/remote`)
}

export function updateRemoteSettings(assessmentId: string, remote_participation_enabled: boolean) {
  return apiFetch<RemoteSettings>(`/api/assessments/${assessmentId}/remote`, {
    method: 'PUT',
    body: JSON.stringify({ remote_participation_enabled }),
  })
}

export function createRemoteInvite(assessmentId: string, ttl_seconds?: number) {
  return apiFetch<RemoteInvite>(`/api/assessments/${assessmentId}/remote/invites`, {
    method: 'POST',
    body: JSON.stringify(ttl_seconds ? { ttl_seconds } : {}),
  })
}

export function revokeRemoteInvite(assessmentId: string, jti: string) {
  return apiFetch<RemoteInvite>(`/api/assessments/${assessmentId}/remote/invites/${jti}/revoke`, {
    method: 'POST',
  })
}

export function listRemoteContributions(assessmentId: string, status?: string) {
  const q = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiFetch<{ items: RemoteContribution[]; pending_count: number }>(
    `/api/assessments/${assessmentId}/remote/contributions${q}`,
  )
}

export function getRemoteContribution(assessmentId: string, contributionId: string) {
  return apiFetch<RemoteContribution>(`/api/assessments/${assessmentId}/remote/contributions/${contributionId}`)
}

export function disposeRemoteContribution(
  assessmentId: string,
  contributionId: string,
  action: 'include' | 'defer' | 'dismiss',
) {
  return apiFetch<{
    contribution: RemoteContribution
    affected_practices: string[]
    notification: string | null
    host_question_unchanged: boolean
  }>(`/api/assessments/${assessmentId}/remote/contributions/${contributionId}/disposition`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
}

export function getRemoteTopic(token: string) {
  return apiFetch<RemoteTopic>(`/api/remote/topic?token=${encodeURIComponent(token)}`)
}

export function joinRemote(token: string, display_name: string, email: string) {
  return apiFetch<RemoteJoinResult>('/api/remote/join', {
    method: 'POST',
    body: JSON.stringify({ token, display_name, email }),
  })
}

export async function submitRemoteContribution(input: {
  token: string
  contributor_id: string
  body: string
  attachment?: File | null
}) {
  const form = new FormData()
  form.append('token', input.token)
  form.append('contributor_id', input.contributor_id)
  form.append('body', input.body)
  if (input.attachment) form.append('attachment', input.attachment)

  const response = await fetch(`${API_BASE}/api/remote/contributions`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()
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
  return payload as {
    id: string
    status: string
    topic: string
    preview: string
    has_attachment: boolean
    confirmation_message: string
  }
}

export type ReviewPractice = {
  practice_key: string
  practice_name: string
  domain_key: string
  domain_short_name: string
  coverage_state: string
  ai_candidate_score: number | null
  named_maturity_level: string | null
  confidence: number | null
  human_evidence: string
  jira_evidence: string
  ado_evidence: string
  source_turn_ids: string[]
  contradictions: string[]
  limitations: string[]
  scoring_rationale: string
  missing_information: string[]
  admin_final_score: number | null
  admin_rationale: string | null
  evidence_unreliable: boolean
  admin_observation: string | null
  recommendation_text: string | null
}

export type ImprovementAction = {
  id: string
  title: string
  practice_key: string | null
  domain_key: string | null
  observation: string
  supporting_evidence: string
  why_it_matters: string
  recommended_action: string
  time_horizon: string
  kpi: string
  priority: number
}

export type ReviewPackage = {
  assessment_id: string
  team_name: string
  product_service_name: string
  status: string
  lookback_days: number
  evidence_influence_mode: string
  overall_maturity: number | null
  confidence_summary: string | null
  evidence_quality: string | null
  strengths: string[]
  maturity_gaps: string[]
  evidence_limitations: string[]
  practices: ReviewPractice[]
  improvement_actions: ImprovementAction[]
  radar: { domain_key: string; domain_short_name: string; domain_name: string; score: number; weight: number }[]
  heatmap: { practice_key: string; practice_name: string; domain_short_name: string; score: number | null; named_maturity_level?: string | null }[]
  chart_summary: string
  ready_to_publish: boolean
  ai_vs_final: { practice_key: string; ai_candidate_score: number | null; admin_final_score: number | null; admin_rationale?: string | null }[]
}

export type StandardFindingStatus =
  | 'aligned'
  | 'partially_aligned'
  | 'finding'
  | 'insufficient_evidence'
  | 'not_applicable'

export type EnterpriseStandardCondition = {
  id?: string
  field: string
  operator: string
  value: string
  logical_group: 'all' | 'any'
}

export type EnterpriseStandard = {
  id: string
  stable_key: string
  title: string
  category: string
  description: string
  requirement_level: 'required' | 'preferred' | 'recommended'
  active: boolean
  applicability_mode: 'always' | 'conditions'
  mapped_practice_keys: string[]
  primary_interview_guidance: string
  follow_up_guidance: string
  evidence_expectations: string
  recommendation_when_unmet: string
  display_order: number
  conditions: EnterpriseStandardCondition[]
  referenced: boolean
  created_at: string
  updated_at: string
}

export type EnterpriseStandardInput = Omit<
  EnterpriseStandard,
  'id' | 'referenced' | 'created_at' | 'updated_at' | 'conditions'
> & { conditions: Omit<EnterpriseStandardCondition, 'id'>[] }

export type TechnologyContext = {
  id?: string
  assessment_id?: string
  primary_technology: string
  application_type: string
  current_platform: string
  target_platform: string
  hosting_location: string
  customer_exposure: string
  lifecycle_stage: string
  application_has_secrets: boolean
  uses_cicd: boolean
  context_tags: string[]
  notes: string
  confirmed_at?: string | null
  applicable_standard_count?: number
  applicable_standard_keys?: string[]
}

export type StandardFinding = {
  id: string
  assessment_id: string
  snapshot_id: string
  stable_key: string
  title: string
  category: string
  requirement_level: 'required' | 'preferred' | 'recommended'
  mapped_practice_keys: string[]
  status: StandardFindingStatus
  human_evidence_summary: string
  tool_evidence_summary: string
  source_interview_turn_ids: string[]
  source_evidence_metric_ids: string[]
  confidence: number | null
  observation: string
  recommendation: string
  admin_edited_status: boolean
  admin_note: string
  time_horizon: string
}

export type PublishedEnterpriseStandards = {
  applicable_count: number
  aligned_count: number
  partially_aligned_count: number
  finding_count: number
  insufficient_evidence_count: number
  not_applicable_count: number
  findings_by_category: Record<
    string,
    {
      standard: string
      stable_key: string
      category: string
      requirement_level: string
      status: string
      observation: string
      supporting_evidence: string
      recommendation: string
      related_safe_practices: string[]
      suggested_time_horizon: string
    }[]
  >
  recommendation_cards: {
    standard: string
    stable_key: string
    category: string
    requirement_level: string
    status: string
    observation: string
    supporting_evidence: string
    recommendation: string
    related_safe_practices: string[]
    suggested_time_horizon: string
  }[]
}

export type PublishedResults = {
  assessment_id: string
  version: number
  title: string
  team_name: string
  product_service_name: string
  published_at: string
  lookback_days: number
  evidence_influence_mode: string
  overall_maturity: number
  confidence_summary: string
  evidence_quality: string
  practices_assessed: number
  practices_total: number
  strengths: string[]
  maturity_gaps: string[]
  evidence_limitations: string[]
  radar: ReviewPackage['radar']
  heatmap: ReviewPackage['heatmap']
  improvement_actions: ImprovementAction[]
  chart_summary: string
  scores: Record<string, number>
  enterprise_standards?: PublishedEnterpriseStandards | null
}

export function startReview(assessmentId: string) {
  return apiFetch<ReviewPackage>(`/api/assessments/${assessmentId}/review/start`, { method: 'POST' })
}

export function getReview(assessmentId: string) {
  return apiFetch<ReviewPackage>(`/api/assessments/${assessmentId}/review`)
}

export function setReviewScore(
  assessmentId: string,
  practiceKey: string,
  body: { score?: number; rationale?: string; accept_candidate?: boolean },
) {
  return apiFetch<ReviewPackage>(`/api/assessments/${assessmentId}/review/practices/${practiceKey}/score`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function markEvidenceUnreliable(assessmentId: string, practiceKey: string, unreliable = true, note?: string) {
  return apiFetch<ReviewPackage>(`/api/assessments/${assessmentId}/review/practices/${practiceKey}/unreliable`, {
    method: 'POST',
    body: JSON.stringify({ unreliable, note }),
  })
}

export function addReviewObservation(assessmentId: string, practiceKey: string, observation: string) {
  return apiFetch<ReviewPackage>(`/api/assessments/${assessmentId}/review/practices/${practiceKey}/observation`, {
    method: 'POST',
    body: JSON.stringify({ observation }),
  })
}

export function editRecommendation(assessmentId: string, practiceKey: string, recommendation_text: string) {
  return apiFetch<ReviewPackage>(`/api/assessments/${assessmentId}/review/practices/${practiceKey}/recommendation`, {
    method: 'PUT',
    body: JSON.stringify({ recommendation_text }),
  })
}

export function reopenReviewTopic(assessmentId: string, practiceKey: string) {
  return apiFetch<ReviewPackage>(`/api/assessments/${assessmentId}/review/practices/${practiceKey}/reopen`, {
    method: 'POST',
  })
}

export function editImprovement(assessmentId: string, actionId: string, body: Partial<ImprovementAction>) {
  return apiFetch<ReviewPackage>(`/api/assessments/${assessmentId}/review/improvements/${actionId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function approveReview(assessmentId: string) {
  return apiFetch<ReviewPackage>(`/api/assessments/${assessmentId}/review/approve`, { method: 'POST' })
}

export function publishAssessment(assessmentId: string) {
  return apiFetch<{ id: string; assessment_id: string; version: number; title: string; immutable: boolean }>(
    `/api/assessments/${assessmentId}/publish`,
    { method: 'POST' },
  )
}

export function getPublishedResults(assessmentId: string, version?: number) {
  const q = version != null ? `?version=${version}` : ''
  return apiFetch<PublishedResults>(`/api/assessments/${assessmentId}/results${q}`)
}

export function exportReportUrl(assessmentId: string, version: number, kind: 'pdf' | 'json') {
  return `${API_BASE}/api/assessments/${assessmentId}/results/${version}/export/${kind}`
}

export function listEnterpriseStandards(params?: { search?: string; category?: string; active?: boolean }) {
  const qs = new URLSearchParams()
  if (params?.search) qs.set('search', params.search)
  if (params?.category) qs.set('category', params.category)
  if (params?.active != null) qs.set('active', String(params.active))
  const q = qs.toString()
  return apiFetch<EnterpriseStandard[]>(`/api/enterprise-standards${q ? `?${q}` : ''}`)
}

export function createEnterpriseStandard(body: EnterpriseStandardInput) {
  return apiFetch<EnterpriseStandard>('/api/enterprise-standards', { method: 'POST', body: JSON.stringify(body) })
}

export function updateEnterpriseStandard(id: string, body: Partial<EnterpriseStandardInput>) {
  return apiFetch<EnterpriseStandard>(`/api/enterprise-standards/${id}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function duplicateEnterpriseStandard(id: string) {
  return apiFetch<EnterpriseStandard>(`/api/enterprise-standards/${id}/duplicate`, { method: 'POST' })
}

export function activateEnterpriseStandard(id: string) {
  return apiFetch<EnterpriseStandard>(`/api/enterprise-standards/${id}/activate`, { method: 'POST' })
}

export function deactivateEnterpriseStandard(id: string) {
  return apiFetch<EnterpriseStandard>(`/api/enterprise-standards/${id}/deactivate`, { method: 'POST' })
}

export function deleteEnterpriseStandard(id: string) {
  return apiFetch<void>(`/api/enterprise-standards/${id}`, { method: 'DELETE' })
}

export function exportEnterpriseStandards() {
  return apiFetch<{ standards: EnterpriseStandardInput[] }>('/api/enterprise-standards/export')
}

export function importEnterpriseStandards(standards: EnterpriseStandardInput[]) {
  return apiFetch<EnterpriseStandard[]>('/api/enterprise-standards/import', {
    method: 'POST',
    body: JSON.stringify({ standards }),
  })
}

export function upsertTechnologyContext(
  assessmentId: string,
  body: Omit<TechnologyContext, 'id' | 'assessment_id' | 'confirmed_at' | 'applicable_standard_count' | 'applicable_standard_keys'>,
  confirm = false,
) {
  const q = confirm ? '?confirm=true' : ''
  return apiFetch<TechnologyContext>(`/api/assessments/${assessmentId}/technology-context${q}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function getTechnologyContext(assessmentId: string) {
  return apiFetch<TechnologyContext | null>(`/api/assessments/${assessmentId}/technology-context`)
}

export function listReviewEnterpriseStandards(assessmentId: string) {
  return apiFetch<StandardFinding[]>(`/api/assessments/${assessmentId}/review/enterprise-standards`)
}

export function updateReviewEnterpriseFinding(
  assessmentId: string,
  findingId: string,
  body: {
    status?: StandardFindingStatus
    observation?: string
    recommendation?: string
    admin_note?: string
  },
) {
  return apiFetch<StandardFinding>(
    `/api/assessments/${assessmentId}/review/enterprise-standards/${findingId}`,
    { method: 'PUT', body: JSON.stringify(body) },
  )
}
