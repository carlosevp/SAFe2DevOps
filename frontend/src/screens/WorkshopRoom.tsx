import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Send, ChevronDown, ChevronUp, MessageSquare, CheckCircle2, AlertCircle, Coffee, Save, Users, Inbox,
  Mic, Pause, RotateCcw, Square, Clock,
} from 'lucide-react'
import {
  getInterview,
  resumeInterview,
  saveInterview,
  saveInterviewDraft,
  startInterview,
  submitInterviewTurn,
  completeInterview,
  getAiSettings,
  type InterviewSession,
  type TurnSubmitResult,
} from '../lib/api'
import { RealtimeTranscriptionController } from '../lib/realtimeTranscription'
import { createMicContext, type MicContext } from '../lib/voiceStateMachine'
import { REMOTE_CONTRIBUTIONS } from '../data/sampleData'
import type { Screen, CoverageState } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
  assessmentId?: string | null
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
}

function toUiCoverage(state: string): CoverageState {
  if (state === 'not_discussed') return 'not-discussed'
  if (state === 'partial' || state === 'sufficient' || state === 'clarify') return state
  return 'not-discussed'
}

function newIdempotencyKey() {
  return `turn-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export default function WorkshopRoom({ dark, onNavigate, assessmentId }: Props) {
  const [session, setSession] = useState<InterviewSession | null>(null)
  const [answerText, setAnswerText] = useState('')
  const [clarificationText, setClarificationText] = useState('')
  const [outcome, setOutcome] = useState<UiOutcome>('none')
  const [lastResult, setLastResult] = useState<TurnSubmitResult | null>(null)
  const [showWhy, setShowWhy] = useState(false)
  const [showInbox, setShowInbox] = useState(false)
  const [inboxItems] = useState(REMOTE_CONTRIBUTIONS)
  const [coverageExpanded, setCoverageExpanded] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [micCtx, setMicCtx] = useState<MicContext>(createMicContext())
  const [elapsed, setElapsed] = useState(0)
  const [typedNote, setTypedNote] = useState('')
  const [privacyNotice, setPrivacyNotice] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastIdempotency = useRef<string | null>(null)
  const voiceRef = useRef<RealtimeTranscriptionController | null>(null)

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
    const controller = new RealtimeTranscriptionController({
      onContext: ctx => {
        setMicCtx(ctx)
        if (ctx.state === 'ready_to_edit' || ctx.state === 'fallback_text') {
          const text = controller.getDisplayText()
          if (text) setAnswerText(text)
        } else if (ctx.state === 'listening' || ctx.state === 'paused' || ctx.state === 'reconnecting') {
          setAnswerText(controller.getDisplayText())
        }
      },
      onPrivacyNotice: notice => setPrivacyNotice(notice),
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

  const loadSession = useCallback(async () => {
    if (!assessmentId) {
      setLoading(false)
      setError('No assessment selected. Complete setup and evidence confirmation first.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      let data: InterviewSession
      try {
        data = await getInterview(assessmentId)
      } catch {
        const started = await startInterview(assessmentId)
        data = started.session
      }
      if (data.interview_status === 'paused') {
        data = await resumeInterview(assessmentId)
      }
      setSession(data)
      setAnswerText(data.draft_answer_text || '')
      setOutcome(data.last_outcome === 'clarify' ? 'clarify' : data.last_outcome === 'sufficient' ? 'sufficient' : 'none')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load interview')
    } finally {
      setLoading(false)
    }
  }, [assessmentId])

  useEffect(() => {
    void loadSession()
  }, [loadSession])

  useEffect(() => {
    if (!assessmentId || !session) return
    if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    autosaveTimer.current = setTimeout(() => {
      void saveInterviewDraft(assessmentId, answerText).catch(() => undefined)
    }, 900)
    return () => {
      if (autosaveTimer.current) clearTimeout(autosaveTimer.current)
    }
  }, [answerText, assessmentId, session])

  const practices = session?.practices || []
  const suffCount = practices.filter(p => p.coverage_state === 'sufficient').length
  const partCount = practices.filter(p => p.coverage_state === 'partial').length
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
    if (!assessmentId || !answerText.trim()) return
    setOutcome('processing')
    setError(null)
    const key = lastIdempotency.current && outcome === 'processing'
      ? lastIdempotency.current
      : newIdempotencyKey()
    lastIdempotency.current = key
    try {
      const result = await submitInterviewTurn(assessmentId, {
        answer_text: answerText.trim(),
        idempotency_key: key,
        is_clarification: false,
      })
      setLastResult(result)
      setSession(result.session)
      setAnswerText('')
      setOutcome(result.session.last_outcome === 'clarify' ? 'clarify' : 'sufficient')
      lastIdempotency.current = null
    } catch (err) {
      setOutcome('none')
      setError(err instanceof Error ? err.message : 'Failed to submit answer')
    }
  }

  async function handleSubmitClarification() {
    if (!assessmentId || !clarificationText.trim()) return
    setOutcome('processing')
    setError(null)
    const key = newIdempotencyKey()
    try {
      const result = await submitInterviewTurn(assessmentId, {
        answer_text: clarificationText.trim(),
        idempotency_key: key,
        is_clarification: true,
      })
      setLastResult(result)
      setSession(result.session)
      setClarificationText('')
      setOutcome(result.session.last_outcome === 'clarify' ? 'clarify' : 'sufficient')
    } catch (err) {
      setOutcome('clarify')
      setError(err instanceof Error ? err.message : 'Failed to submit clarification')
    }
  }

  function continueNext() {
    setOutcome('none')
    setLastResult(null)
  }

  async function handleSaveExit() {
    if (!assessmentId) {
      onNavigate('welcome')
      return
    }
    try {
      await saveInterview(assessmentId, answerText)
    } catch {
      // still exit
    }
    onNavigate('welcome')
  }

  async function handleFinish() {
    if (!assessmentId || !session?.completion_eligible) return
    try {
      const data = await completeInterview(assessmentId)
      setSession(data)
      onNavigate('admin-review')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Cannot finish yet')
    }
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
            <button onClick={() => setShowWhy(w => !w)} className="flex items-center gap-1.5 text-xs transition-base" style={{ color: 'var(--muted-foreground)' }}>
              {showWhy ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Why we're asking
            </button>
            {showWhy && (
              <div className="mt-3 p-3 rounded-lg animate-fade-in text-sm" style={{ background: dark ? '#141f35' : '#f8fafc', color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
                {session?.why_asking}
              </div>
            )}
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

          {outcome === 'none' && (
            <div className="rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
              {privacyNotice && (
                <div className="mb-3 text-xs rounded-lg px-3 py-2" style={{ background: dark ? '#141f35' : '#f8fafc', color: 'var(--muted-foreground)', lineHeight: 1.5 }}>
                  Recording privacy: {privacyNotice}
                </div>
              )}

              {voiceEnabled && micCtx.state === 'idle' && (
                <div className="text-center py-4">
                  <p className="text-sm mb-4" style={{ color: 'var(--muted-foreground)' }}>
                    Ready to listen. Press the microphone to begin, or type below.
                  </p>
                  <button
                    onClick={() => void voiceRef.current?.start()}
                    className="w-16 h-16 rounded-full flex items-center justify-center mx-auto transition-base"
                    style={{ background: 'var(--primary)', color: '#fff' }}
                  >
                    <Mic size={26} />
                  </button>
                  <p className="text-xs mt-3" style={{ color: 'var(--muted-foreground)' }}>
                    All voices in the room will be transcribed together
                  </p>
                </div>
              )}

              {(micCtx.state === 'requesting_permission' || micCtx.state === 'connecting' || micCtx.state === 'reconnecting') && (
                <div className="text-center py-6">
                  <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>
                    {micCtx.state === 'reconnecting' ? (micCtx.errorMessage || 'Reconnecting…') : 'Connecting microphone…'}
                  </p>
                </div>
              )}

              {(micCtx.state === 'listening' || micCtx.state === 'paused') && (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2.5 h-2.5 rounded-full"
                        style={{
                          background: micCtx.state === 'listening' ? '#dc2626' : '#f59e0b',
                          animation: micCtx.state === 'listening' ? 'pulse-ring 1.5s ease infinite' : 'none',
                          boxShadow: micCtx.state === 'listening' ? '0 0 0 4px rgba(220,38,38,0.2)' : 'none',
                        }}
                      />
                      <span className="text-xs font-medium" style={{ color: micCtx.state === 'listening' ? '#dc2626' : '#f59e0b' }}>
                        {micCtx.state === 'listening' ? 'Listening…' : 'Paused'}
                      </span>
                    </div>
                    <span className="text-xs font-mono" style={{ color: 'var(--muted-foreground)' }}>
                      <Clock size={11} className="inline mr-1" />
                      {String(Math.floor(elapsed / 60)).padStart(2, '0')}:{String(elapsed % 60).padStart(2, '0')}
                      <span style={{ display: 'none' }}>{tick}</span>
                    </span>
                  </div>
                  <textarea
                    value={answerText}
                    onChange={e => setAnswerText(e.target.value)}
                    className="w-full rounded-lg p-3 text-sm outline-none resize-none"
                    style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)', minHeight: 140, lineHeight: 1.7 }}
                    placeholder="Live transcript will appear here…"
                  />
                  <div className="flex items-center justify-between mt-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => (micCtx.state === 'listening' ? voiceRef.current?.pause() : voiceRef.current?.resume())}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                        style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
                      >
                        {micCtx.state === 'listening' ? <Pause size={12} /> : <Mic size={12} />}
                        {micCtx.state === 'listening' ? 'Pause' : 'Resume'}
                      </button>
                      <button
                        onClick={() => {
                          voiceRef.current?.discard()
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
                      onClick={() => void voiceRef.current?.finish()}
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

              {(micCtx.state === 'ready_to_edit' || micCtx.state === 'fallback_text' || micCtx.state === 'error' || (!voiceEnabled && micCtx.state === 'idle')) && (
                <div>
                  {(micCtx.state === 'fallback_text' || micCtx.state === 'error') && micCtx.errorMessage && (
                    <p className="text-sm mb-3" style={{ color: '#d97706' }}>{micCtx.errorMessage}</p>
                  )}
                  <p className="text-sm mb-3" style={{ color: 'var(--muted-foreground)' }}>
                    {micCtx.state === 'ready_to_edit'
                      ? 'Review and edit the transcript, then submit when the host confirms it is complete.'
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
                          onClick={() => void voiceRef.current?.start()}
                          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg"
                          style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
                        >
                          <Mic size={12} />
                          Record again
                        </button>
                      )}
                      <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>Autosaves as you type</span>
                    </div>
                    <button
                      onClick={() => void handleSubmitAnswer()}
                      disabled={!answerText.trim()}
                      className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-lg font-medium transition-base"
                      style={{ background: 'var(--primary)', color: '#fff', opacity: answerText.trim() ? 1 : 0.5 }}
                    >
                      <Send size={11} />
                      Submit response
                    </button>
                  </div>
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
              <p className="font-serif text-base mb-4" style={{ color: 'var(--foreground)', lineHeight: 1.6 }}>
                {session?.pending_clarification}
              </p>
              {session?.coverage_confirmation && (
                <p className="text-sm mb-3" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                  {session.coverage_confirmation}
                </p>
              )}
              <textarea
                value={clarificationText}
                onChange={e => setClarificationText(e.target.value)}
                placeholder="Type your clarification…"
                className="w-full rounded-lg p-3 text-sm outline-none resize-none mb-3"
                style={{ background: 'var(--card)', border: '1px solid var(--border)', color: 'var(--foreground)', minHeight: 80, lineHeight: 1.7 }}
              />
              <button
                onClick={() => void handleSubmitClarification()}
                disabled={!clarificationText.trim()}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-base"
                style={{ background: 'var(--primary)', color: '#fff', opacity: clarificationText.trim() ? 1 : 0.5 }}
              >
                <Send size={13} />
                Submit clarification
              </button>
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
              <div className="space-y-3">
                {inboxItems.map(item => (
                  <div key={item.id} className="rounded-lg p-3" style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-semibold" style={{ color: 'var(--foreground)' }}>{item.name}</span>
                    </div>
                    <p className="text-xs" style={{ color: 'var(--muted-foreground)', lineHeight: 1.55 }}>{item.preview.slice(0, 90)}…</p>
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
                <div className="flex items-center gap-2">
                  <MessageSquare size={13} style={{ color: 'var(--muted-foreground)' }} />
                  <button onClick={() => onNavigate('remote-contributor')} className="text-xs" style={{ color: 'var(--muted-foreground)' }}>
                    Invite remote contributor
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
