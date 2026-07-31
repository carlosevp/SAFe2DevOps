import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Send, ChevronDown, ChevronUp, MessageSquare, CheckCircle2, AlertCircle, Coffee, Save, Users, Inbox,
  Mic, Pause, RotateCcw, Square, Clock, Link2, Copy, Ban, Paperclip, X,
} from 'lucide-react'
import {
  ApiError,
  getInterview,
  resumeInterview,
  saveInterview,
  saveInterviewDraft,
  startInterview,
  submitInterviewTurn,
  completeInterview,
  getAiSettings,
  getRemoteSettings,
  updateRemoteSettings,
  createRemoteInvite,
  revokeRemoteInvite,
  listRemoteContributions,
  disposeRemoteContribution,
  type InterviewSession,
  type TurnSubmitResult,
  type RemoteContribution,
  type RemoteInvite,
} from '../lib/api'
import { formatAssessmentNotFound } from '../lib/assessmentSession'
import MicrophoneTest from '../components/MicrophoneTest'
import { RealtimeTranscriptionController, type SessionDiagnostics } from '../lib/realtimeTranscription'
import {
  createMicContext,
  isLiveSpeakingState,
  type MicContext,
} from '../lib/voiceStateMachine'
import type { Screen, CoverageState } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
  assessmentId?: string | null
  onAssessmentBound?: (id: string, name: string) => void
}

type UiOutcome = 'none' | 'clarify' | 'sufficient' | 'processing'

const DOMAIN_COLORS: Record<string, string> = {
  CE: '#3b7dd8',
  CI: '#0f8b8d',
  CD: '#7c3aed',
  RoD: '#f59e0b',
}

const coverageLabel: Record<CoverageState, string> = {
  'not-discussed': 'Not discussed',
  partial: 'Partially covered',
  sufficient: 'Sufficiently covered',
  clarify: 'Needs clarification',
  insufficient: 'Poor coverage',
}

function toUiCoverage(state: string): CoverageState {
  if (state === 'not_discussed') return 'not-discussed'
  if (state === 'partial' || state === 'sufficient' || state === 'clarify' || state === 'insufficient') {
    return state
  }
  return 'not-discussed'
}

function newIdempotencyKey() {
  return `turn-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export default function WorkshopRoom({ dark, onNavigate, assessmentId, onAssessmentBound }: Props) {
  const [session, setSession] = useState<InterviewSession | null>(null)
  const effectiveAssessmentId = assessmentId || session?.assessment_id || null
  const [answerText, setAnswerText] = useState('')
  const [clarificationText, setClarificationText] = useState('')
  const [outcome, setOutcome] = useState<UiOutcome>('none')
  const [lastResult, setLastResult] = useState<TurnSubmitResult | null>(null)
  const [showInbox, setShowInbox] = useState(false)
  const [inboxItems, setInboxItems] = useState<RemoteContribution[]>([])
  const [pendingCount, setPendingCount] = useState(0)
  const [remoteEnabled, setRemoteEnabled] = useState(false)
  const [activeInvite, setActiveInvite] = useState<RemoteInvite | null>(null)
  const [inviteBusy, setInviteBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [selectedContribution, setSelectedContribution] = useState<RemoteContribution | null>(null)
  const [remoteNotice, setRemoteNotice] = useState<string | null>(null)
  const [coverageExpanded, setCoverageExpanded] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [micCtx, setMicCtx] = useState<MicContext>(createMicContext())
  const [elapsed, setElapsed] = useState(0)
  const [typedNote, setTypedNote] = useState('')
  const [privacyNotice, setPrivacyNotice] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const [showMicTest, setShowMicTest] = useState(false)
  const [voiceDiag, setVoiceDiag] = useState<SessionDiagnostics | null>(null)
  const [refineFlash, setRefineFlash] = useState(false)
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastIdempotency = useRef<string | null>(null)
  const voiceRef = useRef<RealtimeTranscriptionController | null>(null)
  const hostEditingLive = useRef(false)

  const remotePollDead = useRef(false)

  const refreshRemote = useCallback(async () => {
    if (!effectiveAssessmentId || remotePollDead.current) return
    try {
      const [settings, inbox] = await Promise.all([
        getRemoteSettings(effectiveAssessmentId),
        listRemoteContributions(effectiveAssessmentId),
      ])
      setRemoteEnabled(settings.remote_participation_enabled)
      setActiveInvite(settings.active_invite)
      setPendingCount(settings.pending_count || inbox.pending_count)
      setInboxItems(inbox.items)
    } catch (err) {
      // Stop hammering a missing assessment (avoids console 404 spam).
      if (err instanceof ApiError && err.code === 'assessment_not_found') {
        remotePollDead.current = true
        setError(formatAssessmentNotFound(effectiveAssessmentId))
      }
    }
  }, [effectiveAssessmentId])

  useEffect(() => {
    getAiSettings()
      .then(settings => {
        setVoiceEnabled(settings.voice_enabled)
        if (!settings.retain_source_audio) {
          setPrivacyNotice('Audio is discarded after transcription. Only the editable transcript is kept.')
        }
      })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    remotePollDead.current = false
    if (!effectiveAssessmentId) return
    void refreshRemote()
    const timer = setInterval(() => {
      void refreshRemote()
    }, 8000)
    return () => clearInterval(timer)
  }, [effectiveAssessmentId, refreshRemote])

  useEffect(() => {
    const controller = new RealtimeTranscriptionController({
      onContext: ctx => {
        setMicCtx(ctx)
        if (ctx.state === 'ready_to_edit') {
          const text = controller.getDisplayText()
          if (text) setAnswerText(text)
          setRefineFlash(true)
          setTimeout(() => setRefineFlash(false), 2200)
        } else if (
          ctx.state === 'refinement_failed' ||
          ctx.state === 'fallback_text' ||
          ctx.state === 'finishing' ||
          ctx.state === 'refining'
        ) {
          const text = controller.getDisplayText()
          if (text) setAnswerText(text)
        } else if (isLiveSpeakingState(ctx.state) || ctx.state === 'reconnecting') {
          if (!hostEditingLive.current) {
            setAnswerText(controller.getDisplayText())
          }
        }
      },
      onPrivacyNotice: notice => setPrivacyNotice(notice),
      onDiagnostics: diag => setVoiceDiag(diag),
    })
    voiceRef.current = controller
    const timer = setInterval(() => {
      setElapsed(controller.elapsedSeconds)
      setTick(t => t + 1)
    }, 250)
    return () => {
      clearInterval(timer)
      controller.discard()
      voiceRef.current = null
    }
  }, [])

  useEffect(() => {
    voiceRef.current?.setAssessmentContext(effectiveAssessmentId, session?.topic_label || null)
  }, [effectiveAssessmentId, session?.topic_label])

  const loadSession = useCallback(async () => {
    if (!assessmentId) {
      setLoading(false)
      setError('No assessment selected. Use Resume on the welcome screen, or complete setup first.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      let data: InterviewSession
      try {
        data = await getInterview(assessmentId)
      } catch (err) {
        if (err instanceof ApiError && err.code === 'assessment_not_found') {
          throw err
        }
        const started = await startInterview(assessmentId)
        data = started.session
      }
      if (data.interview_status === 'paused') {
        data = await resumeInterview(assessmentId)
      }
      setSession(data)
      onAssessmentBound?.(data.assessment_id, data.team_name)
      setAnswerText(data.draft_answer_text || '')
      setOutcome(data.last_outcome === 'clarify' ? 'clarify' : data.last_outcome === 'sufficient' ? 'sufficient' : 'none')
    } catch (err) {
      if (err instanceof ApiError && err.code === 'assessment_not_found') {
        setError(formatAssessmentNotFound(assessmentId))
      } else {
        setError(err instanceof Error ? err.message : 'Failed to load interview')
      }
    } finally {
      setLoading(false)
    }
  }, [assessmentId, onAssessmentBound])

  useEffect(() => {
    void loadSession()
  }, [loadSession])

  useEffect(() => {
    if (!effectiveAssessmentId || !session) return
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    autosaveTimer.current = setTimeout(() => {
      void saveInterviewDraft(effectiveAssessmentId, answerText).catch((err: unknown) => {
        if (err instanceof ApiError && err.code === 'assessment_not_found') {
          setError(formatAssessmentNotFound(effectiveAssessmentId))
        }
      })
    }, 900)
    return () => {
      if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    }
  }, [answerText, effectiveAssessmentId, session])

  const practices = session?.practices || []
  const suffCount = practices.filter(p => p.coverage_state === 'sufficient').length
  const partCount = practices.filter(p => p.coverage_state === 'partial').length
  const poorCount = practices.filter(p => p.coverage_state === 'insufficient').length
  const notCount = practices.filter(p => p.coverage_state === 'not_discussed').length
  const coveragePct = Math.round((suffCount / Math.max(practices.length, 16)) * 100)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  const domainGroups = useMemo(() => {
    const order = ['CE', 'CI', 'CD', 'RoD']
    return order.map(short => ({
      short,
      practices: practices.filter(p => p.domain_short_name === short),
    }))
  }, [practices])

  async function handleSubmitAnswer() {
    if (!effectiveAssessmentId || !answerText.trim()) return
    setOutcome('processing')
    setError(null)
    const key = lastIdempotency.current && outcome === 'processing'
      ? lastIdempotency.current
      : newIdempotencyKey()
    lastIdempotency.current = key
    try {
      const result = await submitInterviewTurn(effectiveAssessmentId, {
        answer_text: answerText.trim(),
        idempotency_key: key,
        is_clarification: false,
      })
      setLastResult(result)
      setSession(result.session)
      onAssessmentBound?.(result.session.assessment_id, result.session.team_name)
      resetVoiceForNextAnswer()
      setOutcome(result.session.last_outcome === 'clarify' ? 'clarify' : 'sufficient')
      lastIdempotency.current = null
    } catch (err) {
      setOutcome('none')
      if (err instanceof ApiError && err.code === 'assessment_not_found') {
        setError(formatAssessmentNotFound(effectiveAssessmentId))
      } else {
        setError(err instanceof Error ? err.message : 'Failed to submit answer')
      }
    }
  }

  async function handleSubmitClarification() {
    const text = (answerText || clarificationText).trim()
    if (!effectiveAssessmentId || !text) return
    setOutcome('processing')
    setError(null)
    const key = newIdempotencyKey()
    try {
      const result = await submitInterviewTurn(effectiveAssessmentId, {
        answer_text: text,
        idempotency_key: key,
        is_clarification: true,
      })
      setLastResult(result)
      setSession(result.session)
      onAssessmentBound?.(result.session.assessment_id, result.session.team_name)
      resetVoiceForNextAnswer()
      setOutcome(result.session.last_outcome === 'clarify' ? 'clarify' : 'sufficient')
    } catch (err) {
      setOutcome('clarify')
      if (err instanceof ApiError && err.code === 'assessment_not_found') {
        setError(formatAssessmentNotFound(effectiveAssessmentId))
      } else {
        setError(err instanceof Error ? err.message : 'Failed to submit clarification')
      }
    }
  }

  function resetVoiceForNextAnswer() {
    hostEditingLive.current = false
    setTypedNote('')
    setAnswerText('')
    setClarificationText('')
    voiceRef.current?.discard()
  }

  function continueNext() {
    resetVoiceForNextAnswer()
    setOutcome('none')
    setLastResult(null)
  }

  async function handleSaveExit() {
    if (!effectiveAssessmentId) {
      onNavigate('welcome')
      return
    }
    try {
      await saveInterview(effectiveAssessmentId, answerText)
    } catch {
      // still exit
    }
    onNavigate('welcome')
  }

  async function handleFinish() {
    if (!effectiveAssessmentId || !session?.completion_eligible) return
    try {
      const data = await completeInterview(effectiveAssessmentId)
      setSession(data)
      onNavigate('admin-review')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Cannot finish yet')
    }
  }

  async function handleToggleRemote(enabled: boolean) {
    if (!effectiveAssessmentId) return
    setInviteBusy(true)
    try {
      const settings = await updateRemoteSettings(effectiveAssessmentId, enabled)
      setRemoteEnabled(settings.remote_participation_enabled)
      setActiveInvite(settings.active_invite)
      if (!enabled) setActiveInvite(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update remote settings')
    } finally {
      setInviteBusy(false)
    }
  }

  async function handleCreateInvite() {
    if (!effectiveAssessmentId) return
    setInviteBusy(true)
    try {
      if (!remoteEnabled) {
        await updateRemoteSettings(effectiveAssessmentId, true)
        setRemoteEnabled(true)
      }
      const invite = await createRemoteInvite(effectiveAssessmentId)
      setActiveInvite(invite)
      setRemoteNotice('Invite link created. Copy and share it with remote contributors.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create invite')
    } finally {
      setInviteBusy(false)
    }
  }

  async function handleCopyInvite() {
    if (!activeInvite?.invite_url) return
    try {
      await navigator.clipboard.writeText(activeInvite.invite_url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      setError('Unable to copy invite link')
    }
  }

  async function handleRevokeInvite() {
    if (!effectiveAssessmentId || !activeInvite) return
    setInviteBusy(true)
    try {
      await revokeRemoteInvite(effectiveAssessmentId, activeInvite.jti)
      setActiveInvite(null)
      setRemoteNotice('Invite link revoked.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to revoke invite')
    } finally {
      setInviteBusy(false)
    }
  }

  async function handleDisposition(id: string, action: 'include' | 'defer' | 'dismiss') {
    if (!effectiveAssessmentId) return
    try {
      const result = await disposeRemoteContribution(effectiveAssessmentId, id, action)
      setRemoteNotice(result.notification || `Contribution ${action}d.`)
      if (action === 'include') {
        // Refresh coverage without advancing the host question.
        const data = await getInterview(effectiveAssessmentId)
        const previousQuestion = session?.current_question
        setSession(data)
        if (previousQuestion && data.current_question !== previousQuestion) {
          setError('Host question unexpectedly changed after include')
        }
      }
      setSelectedContribution(null)
      await refreshRemote()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update contribution')
    }
  }

  function formatRelative(ts: string) {
    const then = new Date(ts).getTime()
    if (Number.isNaN(then)) return ts
    const mins = Math.max(0, Math.round((Date.now() - then) / 60000))
    if (mins < 1) return 'just now'
    if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`
    const hours = Math.round(mins / 60)
    return `${hours} hour${hours === 1 ? '' : 's'} ago`
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--background)', color: 'var(--muted-foreground)' }}>
        Preparing adaptive interview…
      </div>
    )
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      <div
        className="sticky top-14 z-40 px-5 py-2.5 flex items-center justify-between"
        style={{ background: 'var(--card)', borderBottom: `1px solid ${cardBorder}` }}
      >
        <div className="flex items-center gap-4">
          <div>
            <span className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>
              {session?.team_name || 'Assessment'}
            </span>
            <span className="text-sm" style={{ color: 'var(--muted-foreground)' }}> · DevOps Maturity Assessment</span>
          </div>
          <div
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full"
            style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--muted-foreground)' }}
          >
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#10b981' }} />
            {session?.interview_status === 'paused' ? 'Paused' : 'In progress'}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--muted-foreground)' }}>
            <Users size={13} />
            <span>Host room</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--muted-foreground)' }}>
            <div className="font-mono font-medium text-xs px-2 py-0.5 rounded" style={{ background: dark ? '#141f35' : '#f1f5f9' }}>
              {coveragePct}% covered
            </div>
          </div>
          <button
            onClick={() => setShowInbox(s => !s)}
            className="relative flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg transition-base"
            style={{ background: showInbox ? 'var(--primary)' : 'var(--muted)', color: showInbox ? '#fff' : 'var(--foreground)', border: `1px solid ${cardBorder}` }}
          >
            <Inbox size={13} />
            <span>Contributions</span>
            {pendingCount > 0 && (
              <span
                className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold flex items-center justify-center"
                style={{ background: '#dc2626', color: '#fff' }}
              >
                {pendingCount}
              </span>
            )}
          </button>
          <button
            onClick={() => void handleSaveExit()}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-base"
            style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
          >
            <Save size={12} />
            Save & exit
          </button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-5 py-6 grid grid-cols-12 gap-5">
        <div className="col-span-3 hidden lg:block">
          <div className="rounded-xl p-4 sticky top-32" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
            <button className="w-full flex items-center justify-between mb-3" onClick={() => setCoverageExpanded(e => !e)}>
              <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--muted-foreground)' }}>Coverage</p>
              {coverageExpanded ? <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} /> : <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} />}
            </button>
            {coverageExpanded && (
              <>
                <div className="flex items-center gap-2 mb-4">
                  <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: dark ? '#1a2540' : '#e2e8f0' }}>
                    <div className="h-full rounded-full transition-all duration-500" style={{ width: `${coveragePct}%`, background: '#10b981' }} />
                  </div>
                  <span className="text-xs font-mono font-semibold" style={{ color: 'var(--foreground)' }}>{coveragePct}%</span>
                </div>
                <div className="space-y-0.5 mb-4">
                  {[
                    { label: 'Sufficient', count: suffCount, color: '#10b981' },
                    { label: 'Partial', count: partCount, color: '#f59e0b' },
                    { label: 'Poor', count: poorCount, color: '#94a3b8' },
                    { label: 'Not discussed', count: notCount, color: dark ? '#334155' : '#cbd5e1' },
                  ].map(s => (
                    <div key={s.label} className="flex items-center justify-between py-1">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full" style={{ background: s.color }} />
                        <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>{s.label}</span>
                      </div>
                      <span className="text-xs font-mono font-medium" style={{ color: 'var(--foreground)' }}>{s.count}</span>
                    </div>
                  ))}
                </div>
                {domainGroups.map(group => (
                  <div key={group.short} className="mb-3">
                    <p className="text-xs font-medium mb-1.5" style={{ color: DOMAIN_COLORS[group.short] }}>{group.short}</p>
                    <div className="space-y-1">
                      {group.practices.map(p => {
                        const cov = toUiCoverage(p.coverage_state)
                        return (
                          <div key={p.practice_key} className="flex items-center gap-1.5">
                            <div
                              className="w-2 h-2 rounded-sm shrink-0"
                              style={{
                                background: cov === 'sufficient' ? '#10b981'
                                  : cov === 'partial' ? '#f59e0b'
                                  : cov === 'clarify' ? '#f97316'
                                  : cov === 'insufficient' ? '#94a3b8'
                                  : dark ? '#334155' : '#cbd5e1',
                              }}
                            />
                            <span className="text-xs leading-snug" style={{ color: 'var(--muted-foreground)', fontSize: 10 }} title={coverageLabel[cov]}>
                              {p.practice_name}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        <div className="col-span-12 lg:col-span-6 space-y-4">
          {error && <div className="text-sm" style={{ color: '#dc2626' }}>{error}</div>}

          <div className="rounded-xl p-6 animate-fade-in" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
            <div className="flex items-center gap-2 mb-4">
              <span
                className="text-xs font-medium px-2.5 py-1 rounded-full"
                style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--primary)' }}
              >
                {session?.topic_label || 'Adaptive question'}
              </span>
            </div>
            <p className="font-serif text-lg mb-4 leading-relaxed" style={{ color: 'var(--foreground)', lineHeight: 1.6 }}>
              {session?.current_question || 'Loading question…'}
            </p>
            {(() => {
              const parts = (session?.why_asking || '')
                .split(/\n\n+/)
                .map(part => part.trim())
                .filter(Boolean)
              const practiceMeanings = parts.length > 1 ? parts.slice(0, -1) : []
              const whyReason = parts.length > 1 ? parts[parts.length - 1] : parts[0] || ''
              if (!practiceMeanings.length && !whyReason) return null
              return (
                <div className="space-y-3">
                  {practiceMeanings.map(meaning => (
                    <div
                      key={meaning.slice(0, 48)}
                      className="p-3 rounded-lg text-sm"
                      style={{ background: dark ? '#141f35' : '#f8fafc', border: `1px solid ${cardBorder}`, color: 'var(--foreground)', lineHeight: 1.65 }}
                    >
                      <p className="text-xs font-semibold mb-1" style={{ color: 'var(--primary)' }}>What this means</p>
                      <p>{meaning}</p>
                    </div>
                  ))}
                  {whyReason && (
                    <div className="p-3 rounded-lg text-sm" style={{ background: dark ? '#141f35' : '#f8fafc', color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
                      <p className="text-xs font-semibold mb-1" style={{ color: 'var(--muted-foreground)' }}>Why we're asking</p>
                      <p>{whyReason}</p>
                    </div>
                  )}
                </div>
              )
            })()}
          </div>

          <div
            className="rounded-xl p-4 flex items-start gap-3"
            style={{ background: dark ? '#141f35' : '#f0fdfc', border: `1px solid ${dark ? '#1e3358' : '#99f5ef'}` }}
          >
            <div className="w-1.5 h-1.5 rounded-full mt-2 shrink-0" style={{ background: '#0f8b8d' }} />
            <div>
              <p className="text-xs font-semibold mb-1" style={{ color: '#0f8b8d' }}>Evidence context</p>
              <p className="text-sm" style={{ color: dark ? '#5de8e0' : '#0e7170', lineHeight: 1.65 }}>
                {session?.evidence_context || 'Evidence will appear here once the interview starts.'}
              </p>
            </div>
          </div>

          {outcome === 'clarify' && (
            <div
              className="rounded-xl p-5 animate-slide-in"
              style={{ background: dark ? '#0f1d40' : '#eef3fa', border: '2px solid var(--primary)' }}
            >
              <div className="flex items-center gap-2 mb-3">
                <AlertCircle size={15} style={{ color: 'var(--primary)' }} />
                <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--primary)' }}>
                  One follow-up
                </span>
              </div>
              <p className="font-serif text-base mb-2" style={{ color: 'var(--foreground)', lineHeight: 1.6 }}>
                {session?.pending_clarification}
              </p>
              {(() => {
                const meanings = (session?.why_asking || '')
                  .split(/\n\n+/)
                  .map(part => part.trim())
                  .filter(Boolean)
                  .slice(0, -1)
                if (!meanings.length) return null
                return (
                  <div className="space-y-2 mb-3">
                    {meanings.map(meaning => (
                      <p key={meaning.slice(0, 48)} className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                        {meaning}
                      </p>
                    ))}
                  </div>
                )
              })()}
              {session?.coverage_confirmation && (
                <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                  {session.coverage_confirmation}
                </p>
              )}
            </div>
          )}

          {(outcome === 'none' || outcome === 'clarify') && (
            <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
              {privacyNotice && (
                <div className="mb-3 text-xs rounded-lg px-3 py-2" style={{ background: dark ? '#141f35' : '#f8fafc', color: 'var(--muted-foreground)', lineHeight: 1.5 }}>
                  Recording privacy: {privacyNotice}
                </div>
              )}

              {voiceEnabled && (micCtx.state === 'idle' || micCtx.state === 'ready') && (
                <div className="text-center py-4">
                  <p className="text-sm mb-1 font-medium" style={{ color: 'var(--foreground)' }}>{micCtx.statusLabel}</p>
                  <p className="text-sm mb-4" style={{ color: 'var(--muted-foreground)' }}>
                    Press the microphone to begin live draft transcription, or type below. Natural pauses will not end the answer.
                    With a higher live-delay setting, text may appear a few seconds after you speak, and more of it after Finish.
                  </p>
                  <button
                    onClick={() => {
                      hostEditingLive.current = false
                      void voiceRef.current?.start()
                    }}
                    className="w-16 h-16 rounded-full flex items-center justify-center mx-auto transition-base"
                    style={{ background: 'var(--primary)', color: '#fff' }}
                  >
                    <Mic size={26} />
                  </button>
                  <p className="text-xs mt-3" style={{ color: 'var(--muted-foreground)' }}>
                    All voices near the selected microphone are transcribed together. Distant speakers may be missed.
                  </p>
                  <button
                    type="button"
                    onClick={() => setShowMicTest(v => !v)}
                    className="text-xs mt-3 underline"
                    style={{ color: 'var(--muted-foreground)' }}
                  >
                    {showMicTest ? 'Hide microphone test' : 'Pre-workshop microphone test'}
                  </button>
                  {showMicTest && (
                    <div className="mt-3 text-left">
                      <MicrophoneTest
                        dark={dark}
                        onDeviceSelected={id => voiceRef.current?.setPreferredDeviceId(id)}
                      />
                    </div>
                  )}
                  <div className="mt-5 pt-4 text-left" style={{ borderTop: `1px solid ${cardBorder}` }}>
                    <p className="text-xs mb-2" style={{ color: 'var(--muted-foreground)' }}>Or type the answer</p>
                    <textarea
                      value={answerText}
                      onChange={e => setAnswerText(e.target.value)}
                      className="w-full rounded-lg p-3 text-sm outline-none resize-none"
                      style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)', minHeight: 120, lineHeight: 1.7 }}
                      placeholder={outcome === 'clarify' ? 'Type your clarification…' : "Type the team's answer…"}
                    />
                    <div className="flex justify-end mt-3">
                      <button
                        onClick={() => void (outcome === 'clarify' ? handleSubmitClarification() : handleSubmitAnswer())}
                        disabled={!answerText.trim()}
                        className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-lg font-medium"
                        style={{ background: 'var(--primary)', color: '#fff', opacity: answerText.trim() ? 1 : 0.5 }}
                      >
                        <Send size={11} />
                        {outcome === 'clarify' ? 'Submit clarification' : 'Submit response'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {(micCtx.state === 'requesting_permission' || micCtx.state === 'connecting' || micCtx.state === 'reconnecting' || micCtx.state === 'disconnected') && (
                <div className="text-center py-6">
                  <p className="text-sm font-medium mb-1" style={{ color: 'var(--foreground)' }}>{micCtx.statusLabel}</p>
                  <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>
                    {micCtx.errorMessage || (micCtx.state === 'reconnecting' ? 'Reconnecting…' : 'Connecting microphone…')}
                  </p>
                </div>
              )}

              {micCtx.state === 'permission_denied' && (
                <div>
                  <p className="text-sm mb-3" style={{ color: '#d97706' }}>{micCtx.errorMessage || 'Permission denied'}</p>
                  <p className="text-sm mb-3" style={{ color: 'var(--muted-foreground)' }}>
                    Continue with a typed response, or grant microphone access and try again.
                  </p>
                  <textarea
                    value={answerText}
                    onChange={e => setAnswerText(e.target.value)}
                    className="w-full rounded-lg p-3 text-sm outline-none resize-none"
                    style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)', minHeight: 160, lineHeight: 1.7 }}
                    placeholder="Type the team's answer…"
                  />
                  <div className="flex justify-between mt-3">
                    <button
                      onClick={() => void voiceRef.current?.start()}
                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                      style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}
                    >
                      <Mic size={12} /> Try microphone again
                    </button>
                    <button
                      onClick={() => void (outcome === 'clarify' ? handleSubmitClarification() : handleSubmitAnswer())}
                      disabled={!answerText.trim()}
                      className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-lg font-medium"
                      style={{ background: 'var(--primary)', color: '#fff', opacity: answerText.trim() ? 1 : 0.5 }}
                    >
                      <Send size={11} /> {outcome === 'clarify' ? 'Submit clarification' : 'Submit response'}
                    </button>
                  </div>
                </div>
              )}

              {isLiveSpeakingState(micCtx.state) && (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2.5 h-2.5 rounded-full"
                        style={{
                          background: micCtx.state === 'paused' ? '#f59e0b' : '#dc2626',
                          animation: micCtx.state !== 'paused' ? 'pulse-ring 1.5s ease infinite' : 'none',
                          boxShadow: micCtx.state !== 'paused' ? '0 0 0 4px rgba(220,38,38,0.2)' : 'none',
                        }}
                      />
                      <span className="text-xs font-medium" style={{ color: micCtx.state === 'paused' ? '#f59e0b' : '#dc2626' }}>
                        {micCtx.statusLabel}
                        {micCtx.state === 'live_draft' ? ' (provisional)' : ''}
                      </span>
                    </div>
                    <span className="text-xs font-mono" style={{ color: 'var(--muted-foreground)' }}>
                      <Clock size={11} className="inline mr-1" />
                      {String(Math.floor(elapsed / 60)).padStart(2, '0')}:{String(elapsed % 60).padStart(2, '0')}
                      <span style={{ display: 'none' }}>{tick}</span>
                    </span>
                  </div>
                  <p className="text-xs mb-2" style={{ color: 'var(--muted-foreground)' }}>
                    Live draft — text may revise as segments complete. Not final until you finish and review.
                  </p>
                  <textarea
                    value={answerText}
                    onChange={e => {
                      hostEditingLive.current = true
                      setAnswerText(e.target.value)
                    }}
                    className="w-full rounded-lg p-3 text-sm outline-none resize-none"
                    style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)', minHeight: 140, lineHeight: 1.7 }}
                    placeholder="Live draft will appear here…"
                  />
                  <div className="flex items-center justify-between mt-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => (micCtx.state === 'paused' ? voiceRef.current?.resume() : voiceRef.current?.pause())}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                        style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
                      >
                        {micCtx.state === 'paused' ? <Mic size={12} /> : <Pause size={12} />}
                        {micCtx.state === 'paused' ? 'Resume' : 'Pause'}
                      </button>
                      <button
                        onClick={() => {
                          voiceRef.current?.discard()
                          hostEditingLive.current = false
                          setAnswerText('')
                          setElapsed(0)
                        }}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                        style={{ background: 'var(--muted)', color: 'var(--muted-foreground)', border: `1px solid ${cardBorder}` }}
                      >
                        <RotateCcw size={12} />
                        Discard
                      </button>
                    </div>
                    <button
                      onClick={() => {
                        hostEditingLive.current = false
                        void voiceRef.current?.finish()
                      }}
                      className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-lg font-medium"
                      style={{ background: 'var(--primary)', color: '#fff' }}
                    >
                      <Square size={11} />
                      Finish response
                    </button>
                  </div>
                  <div className="mt-3 pt-3" style={{ borderTop: `1px solid ${cardBorder}` }}>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={typedNote}
                        onChange={e => setTypedNote(e.target.value)}
                        placeholder="Append a typed note…"
                        className="flex-1 text-sm px-3 py-2 rounded-lg outline-none"
                        style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
                      />
                      <button
                        onClick={() => {
                          if (!typedNote.trim()) return
                          voiceRef.current?.appendTypedNote(typedNote)
                          setAnswerText(prev => [prev, typedNote.trim()].filter(Boolean).join('\n\n'))
                          setTypedNote('')
                        }}
                        className="p-2 rounded-lg"
                        style={{ background: 'var(--primary)', color: '#fff' }}
                      >
                        <Send size={13} />
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {(micCtx.state === 'finishing' || micCtx.state === 'refining') && (
                <div>
                  <p className="text-sm font-medium mb-2" style={{ color: 'var(--foreground)' }}>{micCtx.statusLabel}</p>
                  <p className="text-sm mb-3" style={{ color: 'var(--muted-foreground)' }}>
                    {micCtx.state === 'finishing'
                      ? 'Finishing — waiting for any delayed live transcript, then refining…'
                      : 'Running an optional accuracy pass on the recording. Your live draft is kept if that pass is unavailable.'}
                  </p>
                  <textarea
                    value={answerText}
                    readOnly
                    className="w-full rounded-lg p-3 text-sm outline-none resize-none opacity-90"
                    style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)', minHeight: 140, lineHeight: 1.7 }}
                  />
                </div>
              )}

              {(micCtx.state === 'ready_to_edit' || micCtx.state === 'refinement_failed' || micCtx.state === 'fallback_text' || micCtx.state === 'error' || (!voiceEnabled && micCtx.state === 'idle')) && (
                <div>
                  {micCtx.state === 'refinement_failed' && (micCtx.refinementWarning || micCtx.errorMessage) && (
                    <p className="text-sm mb-3" style={{ color: 'var(--muted-foreground)' }}>
                      {micCtx.refinementWarning || micCtx.errorMessage}
                    </p>
                  )}
                  {(micCtx.state === 'fallback_text' || micCtx.state === 'error') && (micCtx.errorMessage || micCtx.refinementWarning) && (
                    <p className="text-sm mb-3" style={{ color: '#d97706' }}>
                      {micCtx.refinementWarning || micCtx.errorMessage}
                    </p>
                  )}
                  {refineFlash && micCtx.state === 'ready_to_edit' && (
                    <p className="text-xs mb-2" style={{ color: '#0f8b8d' }}>Accuracy refinement completed — review before submitting.</p>
                  )}
                  <p className="text-sm mb-3" style={{ color: 'var(--muted-foreground)' }}>
                    {micCtx.state === 'ready_to_edit' || micCtx.state === 'refinement_failed'
                      ? 'Edit the transcript, then submit only when the host confirms it is complete. Nothing is auto-submitted.'
                      : 'Type the team\'s response. You can edit freely before submitting.'}
                  </p>
                  <textarea
                    value={answerText}
                    onChange={e => setAnswerText(e.target.value)}
                    className="w-full rounded-lg p-3 text-sm outline-none resize-none"
                    style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)', minHeight: 160, lineHeight: 1.7 }}
                    placeholder="Capture the team's answer here…"
                  />
                  <div className="flex items-center justify-between mt-3">
                    <div className="flex items-center gap-2">
                      {voiceEnabled && (
                        <button
                          onClick={() => {
                            hostEditingLive.current = false
                            void voiceRef.current?.start()
                          }}
                          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                          style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
                        >
                          <Mic size={12} />
                          Record again
                        </button>
                      )}
                      {micCtx.state === 'refinement_failed' && (
                        <button
                          onClick={() => void voiceRef.current?.retryRefine()}
                          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                          style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
                        >
                          <RotateCcw size={12} />
                          Retry accuracy pass
                        </button>
                      )}
                      <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>Autosaves as you type</span>
                    </div>
                    <button
                      onClick={() => void (outcome === 'clarify' ? handleSubmitClarification() : handleSubmitAnswer())}
                      disabled={!answerText.trim()}
                      className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-lg font-medium transition-base"
                      style={{ background: 'var(--primary)', color: '#fff', opacity: answerText.trim() ? 1 : 0.5 }}
                    >
                      <Send size={11} />
                      {outcome === 'clarify' ? 'Submit clarification' : 'Submit response'}
                    </button>
                  </div>
                  {import.meta.env.DEV && voiceDiag && (
                    <details className="mt-4 text-xs" style={{ color: 'var(--muted-foreground)' }}>
                      <summary>Dev voice diagnostics</summary>
                      <pre className="mt-2 whitespace-pre-wrap rounded-lg p-2" style={{ background: 'var(--muted)' }}>
{JSON.stringify({
  connectionState: voiceDiag.connectionState,
  itemIds: voiceDiag.itemIds,
  timeToFirstDeltaMs: voiceDiag.timeToFirstDeltaMs,
  refineDurationMs: voiceDiag.refineDurationMs,
  deviceLabel: voiceDiag.deviceLabel,
  liveModel: voiceDiag.liveModel,
  finalModel: voiceDiag.finalModel,
  liveDraft: voiceDiag.liveDraft,
  completedRealtime: voiceDiag.completedRealtime,
  refinedFinal: voiceDiag.refinedFinal,
}, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              )}
            </div>
          )}

          {outcome === 'processing' && (
            <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
              <div className="text-center py-8">
                <div className="flex justify-center gap-1.5 mb-4">
                  {[0, 1, 2].map(i => (
                    <div
                      key={i}
                      className="w-2 h-2 rounded-full"
                      style={{ background: 'var(--primary)', animation: `typing-dots 1.2s ease ${i * 0.2}s infinite` }}
                    />
                  ))}
                </div>
                <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
                  Reviewing your response against the assessment model and available evidence…
                </p>
              </div>
            </div>
          )}

          {outcome === 'sufficient' && (
            <div
              className="rounded-xl p-5 animate-fade-in"
              style={{ background: dark ? '#092b20' : '#d1fae5', border: `1px solid ${dark ? '#065f46' : '#6ee7b7'}` }}
            >
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle2 size={16} style={{ color: '#10b981' }} />
                <span className="text-sm font-semibold" style={{ color: dark ? '#6ee7b7' : '#065f46' }}>
                  Coverage update
                </span>
              </div>
              <p className="text-sm mb-3" style={{ color: dark ? '#4ade80' : '#047857', lineHeight: 1.65 }}>
                {session?.coverage_confirmation || session?.overall_coverage_summary}
              </p>
              <div className="space-y-1.5 mb-4">
                {(lastResult?.covered_practices || []).map(label => (
                  <div key={`c-${label}`} className="flex items-center gap-2 text-sm">
                    <div className="w-2 h-2 rounded-full" style={{ background: '#10b981' }} />
                    <span style={{ color: dark ? '#e8edf5' : '#0f172a' }}>{label}</span>
                    <span className="text-xs" style={{ color: '#10b981' }}>· sufficiently covered</span>
                  </div>
                ))}
                {(lastResult?.partial_practices || []).map(label => (
                  <div key={`p-${label}`} className="flex items-center gap-2 text-sm">
                    <div className="w-2 h-2 rounded-full" style={{ background: '#f59e0b' }} />
                    <span style={{ color: dark ? '#e8edf5' : '#0f172a' }}>{label}</span>
                    <span className="text-xs" style={{ color: '#f59e0b' }}>· partially covered</span>
                  </div>
                ))}
                {(lastResult?.insufficient_practices || []).map(label => (
                  <div key={`i-${label}`} className="flex items-center gap-2 text-sm">
                    <div className="w-2 h-2 rounded-full" style={{ background: '#94a3b8' }} />
                    <span style={{ color: dark ? '#e8edf5' : '#0f172a' }}>{label}</span>
                    <span className="text-xs" style={{ color: '#64748b' }}>· poor coverage — moving on</span>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={continueNext}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-base"
                  style={{ background: '#10b981', color: '#fff' }}
                >
                  Continue
                </button>
                {session?.completion_eligible && (
                  <button
                    onClick={() => void handleFinish()}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-base"
                    style={{ background: 'var(--primary)', color: '#fff' }}
                  >
                    Finish assessment
                  </button>
                )}
                <button
                  onClick={() => onNavigate('checkpoint')}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-base"
                  style={{ background: dark ? '#0f2a1c' : '#a7f3d0', color: dark ? '#4ade80' : '#065f46' }}
                >
                  <Coffee size={13} />
                  Take a short break
                </button>
                <button
                  onClick={() => void handleSaveExit()}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-base"
                  style={{ background: dark ? '#0f2a1c' : '#a7f3d0', color: dark ? '#4ade80' : '#065f46' }}
                >
                  <Save size={13} />
                  Save & exit
                </button>
              </div>
            </div>
          )}

          <div className="text-center pt-2">
            <button
              onClick={() => onNavigate('checkpoint')}
              className="text-xs transition-base px-3 py-1.5 rounded-lg"
              style={{ color: 'var(--muted-foreground)' }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--muted)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              View coverage checkpoint →
            </button>
          </div>
        </div>

        <div className="col-span-3 hidden lg:block">
          {showInbox ? (
            <div className="rounded-xl p-4 sticky top-32 animate-slide-in" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--muted-foreground)' }}>Contributions</p>
                <button onClick={() => setShowInbox(false)} className="text-xs" style={{ color: 'var(--muted-foreground)' }}>Close</button>
              </div>

              <div className="rounded-lg p-3 mb-3 space-y-2" style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium" style={{ color: 'var(--foreground)' }}>Remote participation</span>
                  <button
                    disabled={inviteBusy}
                    onClick={() => void handleToggleRemote(!remoteEnabled)}
                    className="text-[11px] px-2 py-1 rounded"
                    style={{
                      background: remoteEnabled ? (dark ? '#0f2a1c' : '#d1fae5') : 'var(--card)',
                      color: remoteEnabled ? (dark ? '#4ade80' : '#065f46') : 'var(--muted-foreground)',
                      border: `1px solid ${cardBorder}`,
                    }}
                  >
                    {remoteEnabled ? 'Enabled' : 'Disabled'}
                  </button>
                </div>
                {remoteEnabled && (
                  <>
                    {activeInvite ? (
                      <div className="space-y-2">
                        <p className="text-[11px] break-all" style={{ color: 'var(--muted-foreground)', lineHeight: 1.45 }}>
                          {activeInvite.invite_url}
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          <button
                            onClick={() => void handleCopyInvite()}
                            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded"
                            style={{ background: 'var(--primary)', color: '#fff' }}
                          >
                            <Copy size={11} />
                            {copied ? 'Copied' : 'Copy link'}
                          </button>
                          <button
                            disabled={inviteBusy}
                            onClick={() => void handleRevokeInvite()}
                            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded"
                            style={{ background: 'var(--card)', color: 'var(--muted-foreground)', border: `1px solid ${cardBorder}` }}
                          >
                            <Ban size={11} />
                            Revoke
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        disabled={inviteBusy}
                        onClick={() => void handleCreateInvite()}
                        className="flex items-center gap-1.5 text-[11px] px-2.5 py-1.5 rounded w-full justify-center"
                        style={{ background: 'var(--primary)', color: '#fff' }}
                      >
                        <Link2 size={12} />
                        Create invite link
                      </button>
                    )}
                  </>
                )}
              </div>

              {remoteNotice && (
                <div className="mb-3 text-[11px] rounded-lg px-2.5 py-2" style={{ background: dark ? '#0f2a1c' : '#ecfdf5', color: dark ? '#4ade80' : '#065f46', lineHeight: 1.45 }}>
                  {remoteNotice}
                </div>
              )}

              <div className="space-y-3 max-h-[60vh] overflow-y-auto">
                {inboxItems.length === 0 && (
                  <p className="text-xs" style={{ color: 'var(--muted-foreground)' }}>No remote contributions yet.</p>
                )}
                {inboxItems.map(item => (
                  <div key={item.id} className="rounded-lg p-3" style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold" style={{ color: 'var(--foreground)' }}>{item.contributor_name}</span>
                      <span className="text-[10px]" style={{ color: 'var(--muted-foreground)' }}>{formatRelative(item.timestamp)}</span>
                    </div>
                    <p className="text-[11px] font-medium mb-1" style={{ color: 'var(--primary)' }}>{item.topic}</p>
                    <p className="text-xs mb-2" style={{ color: 'var(--muted-foreground)', lineHeight: 1.55 }}>
                      {item.preview}
                      {item.has_attachment && (
                        <span className="inline-flex items-center gap-1 ml-1" style={{ color: 'var(--foreground)' }}>
                          <Paperclip size={10} />
                        </span>
                      )}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {item.status === 'pending' && (
                        <>
                          <button onClick={() => void handleDisposition(item.id, 'include')} className="text-[11px] px-2 py-1 rounded" style={{ background: dark ? '#0f2a1c' : '#d1fae5', color: dark ? '#4ade80' : '#065f46' }}>Include</button>
                          <button onClick={() => void handleDisposition(item.id, 'defer')} className="text-[11px] px-2 py-1 rounded" style={{ background: 'var(--card)', color: 'var(--muted-foreground)', border: `1px solid ${cardBorder}` }}>Defer</button>
                          <button onClick={() => void handleDisposition(item.id, 'dismiss')} className="text-[11px] px-2 py-1 rounded" style={{ background: 'var(--card)', color: 'var(--muted-foreground)', border: `1px solid ${cardBorder}` }}>Dismiss</button>
                        </>
                      )}
                      <button onClick={() => setSelectedContribution(item)} className="text-[11px] px-2 py-1 rounded" style={{ background: 'var(--card)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}>
                        Open
                      </button>
                    </div>
                    {item.status !== 'pending' && (
                      <p className="text-[10px] mt-1.5 uppercase tracking-wide" style={{ color: 'var(--muted-foreground)' }}>{item.status}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="rounded-xl p-4 sticky top-32" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
              <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: 'var(--muted-foreground)' }}>Domains</p>
              {domainGroups.map(group => {
                const suff = group.practices.filter(p => p.coverage_state === 'sufficient').length
                const total = group.practices.length || 4
                return (
                  <div key={group.short} className="mb-3">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-medium" style={{ color: DOMAIN_COLORS[group.short] }}>{group.short}</span>
                      <span className="text-xs font-mono" style={{ color: 'var(--muted-foreground)' }}>{suff}/{total}</span>
                    </div>
                    <div className="h-1.5 rounded-full overflow-hidden" style={{ background: dark ? '#1a2540' : '#e2e8f0' }}>
                      <div className="h-full rounded-full" style={{ width: `${(suff / total) * 100}%`, background: DOMAIN_COLORS[group.short], opacity: 0.7 }} />
                    </div>
                  </div>
                )
              })}
              <div className="mt-4 pt-3" style={{ borderTop: `1px solid ${cardBorder}` }}>
                <div className="flex items-center gap-2 mb-2">
                  <MessageSquare size={13} style={{ color: 'var(--muted-foreground)' }} />
                  <button onClick={() => setShowInbox(true)} className="text-xs" style={{ color: 'var(--muted-foreground)' }}>
                    Invite remote contributor
                  </button>
                </div>
                {pendingCount > 0 && (
                  <p className="text-[11px]" style={{ color: 'var(--primary)' }}>{pendingCount} pending contribution{pendingCount === 1 ? '' : 's'}</p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {selectedContribution && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center px-4 py-6" style={{ background: 'rgba(15,23,42,0.45)' }}>
          <div className="w-full max-w-lg rounded-2xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}`, maxHeight: '85vh', overflowY: 'auto' }}>
            <div className="flex items-start justify-between mb-3">
              <div>
                <p className="text-sm font-semibold" style={{ color: 'var(--foreground)' }}>{selectedContribution.contributor_name}</p>
                <p className="text-xs" style={{ color: 'var(--muted-foreground)' }}>
                  {selectedContribution.contributor_email || 'No email'} · {formatRelative(selectedContribution.timestamp)}
                </p>
              </div>
              <button onClick={() => setSelectedContribution(null)} style={{ color: 'var(--muted-foreground)' }}>
                <X size={16} />
              </button>
            </div>
            <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--primary)' }}>{selectedContribution.topic}</p>
            <p className="text-sm mb-3" style={{ color: 'var(--foreground)', lineHeight: 1.6 }}>{selectedContribution.question_text}</p>
            <div className="rounded-lg p-3 mb-3" style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}>
              <p className="text-sm" style={{ color: 'var(--foreground)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{selectedContribution.body}</p>
            </div>
            {selectedContribution.has_attachment && (
              <p className="text-xs mb-3 flex items-center gap-1.5" style={{ color: 'var(--muted-foreground)' }}>
                <Paperclip size={12} />
                {selectedContribution.attachment_filename || 'Attachment'}
              </p>
            )}
            {selectedContribution.affected_practices.length > 0 && (
              <p className="text-xs mb-3" style={{ color: 'var(--muted-foreground)' }}>
                Practices affected: {selectedContribution.affected_practices.join(', ')}
              </p>
            )}
            {selectedContribution.status === 'pending' && (
              <div className="flex flex-wrap gap-2">
                <button onClick={() => void handleDisposition(selectedContribution.id, 'include')} className="text-xs px-3 py-2 rounded-lg font-medium" style={{ background: 'var(--primary)', color: '#fff' }}>Include</button>
                <button onClick={() => void handleDisposition(selectedContribution.id, 'defer')} className="text-xs px-3 py-2 rounded-lg" style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}>Defer</button>
                <button onClick={() => void handleDisposition(selectedContribution.id, 'dismiss')} className="text-xs px-3 py-2 rounded-lg" style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}>Dismiss</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
