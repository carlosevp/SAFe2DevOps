import { useState, useEffect, useRef } from 'react'
import { Mic, MicOff, Pause, Square, Send, RotateCcw, ChevronDown, ChevronUp, MessageSquare, CheckCircle2, AlertCircle, Coffee, Save, Clock, Users, Inbox } from 'lucide-react'
import { SAMPLE_PRACTICES, WORKSHOP_QUESTIONS, REMOTE_CONTRIBUTIONS } from '../data/sampleData'
import type { Screen, CoverageState } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
}

type RecordingState = 'idle' | 'recording' | 'paused' | 'processing' | 'done'
type OutcomeState = 'none' | 'clarify' | 'sufficient'

const DOMAIN_COLORS: Record<string, string> = {
  CE: '#3b7dd8',
  CI: '#0f8b8d',
  CD: '#7c3aed',
  RoD: '#f59e0b',
}

const DOMAIN_LABELS: Record<string, string> = {
  CE: 'Continuous Exploration',
  CI: 'Continuous Integration',
  CD: 'Continuous Deployment',
  RoD: 'Release on Demand',
}

const coverageLabel: Record<CoverageState, string> = {
  'not-discussed': 'Not discussed',
  partial: 'Partially covered',
  sufficient: 'Sufficiently covered',
  clarify: 'Needs clarification',
}

const MOCK_TRANSCRIPT = `Jordan: We usually pick up a card from the backlog once sprint planning is done. The dev works on it in a feature branch, raises a PR when ready.

Sam: Yeah, and we've got a pipeline that runs the unit tests on every PR. It needs to pass before anyone can approve it.

Jordan: After merge to main, the CI build kicks off automatically. If it passes, it deploys to the staging environment. We don't deploy to production automatically though — someone manually triggers that.

Alex: We check the Jira ticket's acceptance criteria before triggering the prod deployment. And after it's live, we usually watch the dashboards for about 20 minutes.`

const CLARIFICATION = 'You mentioned builds run automatically when a PR is raised. Are pull requests blocked from merging when the build or a quality gate fails?'

export default function WorkshopRoom({ dark, onNavigate }: Props) {
  const [questionIndex, setQuestionIndex] = useState(0)
  const [recordingState, setRecordingState] = useState<RecordingState>('idle')
  const [elapsed, setElapsed] = useState(0)
  const [transcript, setTranscript] = useState('')
  const [typedNote, setTypedNote] = useState('')
  const [showWhy, setShowWhy] = useState(false)
  const [outcome, setOutcome] = useState<OutcomeState>('none')
  const [clarificationText, setClarificationText] = useState('')
  const [showInbox, setShowInbox] = useState(false)
  const [inboxItems, setInboxItems] = useState(REMOTE_CONTRIBUTIONS)
  const [coverageExpanded, setCoverageExpanded] = useState(true)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const transcriptRef = useRef<HTMLTextAreaElement>(null)

  const question = WORKSHOP_QUESTIONS[questionIndex]

  useEffect(() => {
    if (recordingState === 'recording') {
      timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [recordingState])

  function formatTime(s: number) {
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
  }

  function startRecording() {
    setRecordingState('recording')
    setElapsed(0)
    setTranscript('')
    // Simulate partial transcript appearing
    let charIndex = 0
    const mockText = MOCK_TRANSCRIPT
    const interval = setInterval(() => {
      charIndex = Math.min(charIndex + 8, mockText.length)
      setTranscript(mockText.slice(0, charIndex))
      if (charIndex >= mockText.length) clearInterval(interval)
    }, 40)
  }

  function finishResponse() {
    setRecordingState('processing')
    setTimeout(() => {
      setRecordingState('done')
      setTimeout(() => setOutcome('clarify'), 1200)
    }, 2200)
  }

  function submitClarification() {
    setOutcome('sufficient')
  }

  function continueNext() {
    if (questionIndex < WORKSHOP_QUESTIONS.length - 1) {
      setQuestionIndex(q => q + 1)
      setRecordingState('idle')
      setTranscript('')
      setTypedNote('')
      setOutcome('none')
      setClarificationText('')
    } else {
      onNavigate('checkpoint')
    }
  }

  const suffCount = SAMPLE_PRACTICES.filter(p => p.coverage === 'sufficient').length
  const partCount = SAMPLE_PRACTICES.filter(p => p.coverage === 'partial').length
  const notCount = SAMPLE_PRACTICES.filter(p => p.coverage === 'not-discussed').length
  const coveragePct = Math.round((suffCount / 16) * 100)

  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      {/* Workshop top bar */}
      <div
        className="sticky top-14 z-40 px-5 py-2.5 flex items-center justify-between"
        style={{ background: 'var(--card)', borderBottom: `1px solid ${cardBorder}` }}
      >
        <div className="flex items-center gap-4">
          <div>
            <span className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>Claims Integration</span>
            <span className="text-sm" style={{ color: 'var(--muted-foreground)' }}> · DevOps Maturity Assessment</span>
          </div>
          <div
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full"
            style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--muted-foreground)' }}
          >
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#10b981' }} />
            In progress
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--muted-foreground)' }}>
            <Users size={13} />
            <span>3 in room</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--muted-foreground)' }}>
            <div
              className="font-mono font-medium text-xs px-2 py-0.5 rounded"
              style={{ background: dark ? '#141f35' : '#f1f5f9' }}
            >
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
            {inboxItems.filter(i => i.status === 'pending').length > 0 && (
              <span
                className="absolute -top-1 -right-1 w-4 h-4 rounded-full text-xs flex items-center justify-center font-bold"
                style={{ background: '#f59e0b', color: '#fff', fontSize: 9 }}
              >
                {inboxItems.filter(i => i.status === 'pending').length}
              </span>
            )}
          </button>
          <button
            onClick={() => onNavigate('welcome')}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-base"
            style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
          >
            <Save size={12} />
            Save & exit
          </button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-5 py-6 grid grid-cols-12 gap-5">
        {/* Left: Coverage sidebar */}
        <div className="col-span-3 hidden lg:block">
          <div
            className="rounded-xl p-4 sticky top-32"
            style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
          >
            <button
              className="w-full flex items-center justify-between mb-3"
              onClick={() => setCoverageExpanded(e => !e)}
            >
              <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--muted-foreground)' }}>
                Coverage
              </p>
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

                {['CE', 'CI', 'CD', 'RoD'].map(domain => {
                  const practices = SAMPLE_PRACTICES.filter(p => p.domain === domain)
                  return (
                    <div key={domain} className="mb-3">
                      <p className="text-xs font-medium mb-1.5" style={{ color: DOMAIN_COLORS[domain] }}>
                        {domain}
                      </p>
                      <div className="space-y-1">
                        {practices.map(p => (
                          <div key={p.id} className="flex items-center gap-1.5">
                            <div
                              className="w-2 h-2 rounded-sm shrink-0"
                              style={{
                                background: p.coverage === 'sufficient' ? '#10b981'
                                  : p.coverage === 'partial' ? '#f59e0b'
                                  : p.coverage === 'clarify' ? '#f97316'
                                  : dark ? '#334155' : '#cbd5e1',
                              }}
                            />
                            <span className="text-xs leading-snug" style={{ color: 'var(--muted-foreground)', fontSize: 10 }}>
                              {p.name}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </>
            )}
          </div>
        </div>

        {/* Center: Main question + response */}
        <div className="col-span-12 lg:col-span-6 space-y-4">
          {/* Question card */}
          <div
            className="rounded-xl p-6 animate-fade-in"
            style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
          >
            <div className="flex items-center gap-2 mb-4">
              <span
                className="text-xs font-medium px-2.5 py-1 rounded-full"
                style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--primary)' }}
              >
                {question.topic}
              </span>
              <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>
                {questionIndex + 1} of {WORKSHOP_QUESTIONS.length}
              </span>
            </div>

            <p
              className="font-serif text-lg mb-4 leading-relaxed"
              style={{ color: 'var(--foreground)', lineHeight: 1.6 }}
            >
              {question.text}
            </p>

            <button
              onClick={() => setShowWhy(w => !w)}
              className="flex items-center gap-1.5 text-xs transition-base"
              style={{ color: 'var(--muted-foreground)' }}
            >
              {showWhy ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Why we're asking
            </button>

            {showWhy && (
              <div
                className="mt-3 p-3 rounded-lg animate-fade-in text-sm"
                style={{ background: dark ? '#141f35' : '#f8fafc', color: 'var(--muted-foreground)', lineHeight: 1.65 }}
              >
                {question.why}
              </div>
            )}
          </div>

          {/* Evidence context card */}
          <div
            className="rounded-xl p-4 flex items-start gap-3"
            style={{
              background: dark ? '#141f35' : '#f0fdfc',
              border: `1px solid ${dark ? '#1e3358' : '#99f5ef'}`,
            }}
          >
            <div className="w-1.5 h-1.5 rounded-full mt-2 shrink-0" style={{ background: '#0f8b8d' }} />
            <div>
              <p className="text-xs font-semibold mb-1" style={{ color: '#0f8b8d' }}>Evidence context</p>
              <p className="text-sm" style={{ color: dark ? '#5de8e0' : '#0e7170', lineHeight: 1.65 }}>
                {question.evidence}
              </p>
            </div>
          </div>

          {/* Recording state */}
          {outcome === 'none' && (
            <div
              className="rounded-xl p-5"
              style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
            >
              {recordingState === 'idle' && (
                <div className="text-center py-4">
                  <p className="text-sm mb-4" style={{ color: 'var(--muted-foreground)' }}>
                    Ready to listen. Press the microphone to begin.
                  </p>
                  <button
                    onClick={startRecording}
                    className="w-16 h-16 rounded-full flex items-center justify-center mx-auto transition-base"
                    style={{ background: 'var(--primary)', color: '#fff' }}
                    onMouseEnter={e => (e.currentTarget.style.opacity = '0.85')}
                    onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
                  >
                    <Mic size={26} />
                  </button>
                  <p className="text-xs mt-3" style={{ color: 'var(--muted-foreground)' }}>
                    All voices in the room will be transcribed together
                  </p>
                </div>
              )}

              {(recordingState === 'recording' || recordingState === 'paused') && (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2.5 h-2.5 rounded-full"
                        style={{
                          background: recordingState === 'recording' ? '#dc2626' : '#f59e0b',
                          animation: recordingState === 'recording' ? 'pulse-ring 1.5s ease infinite' : 'none',
                          boxShadow: recordingState === 'recording' ? '0 0 0 4px rgba(220,38,38,0.2)' : 'none',
                        }}
                      />
                      <span className="text-xs font-medium" style={{ color: recordingState === 'recording' ? '#dc2626' : '#f59e0b' }}>
                        {recordingState === 'recording' ? 'Listening…' : 'Paused'}
                      </span>
                    </div>
                    <span className="text-xs font-mono" style={{ color: 'var(--muted-foreground)' }}>
                      <Clock size={11} className="inline mr-1" />
                      {formatTime(elapsed)}
                    </span>
                  </div>

                  <textarea
                    ref={transcriptRef}
                    value={transcript}
                    onChange={e => setTranscript(e.target.value)}
                    className="w-full rounded-lg p-3 text-sm outline-none resize-none"
                    style={{
                      background: 'var(--muted)',
                      border: '1px solid var(--border)',
                      color: 'var(--foreground)',
                      minHeight: 140,
                      lineHeight: 1.7,
                      fontFamily: 'Inter, sans-serif',
                    }}
                    placeholder="Live transcript will appear here…"
                  />

                  <div className="flex items-center justify-between mt-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setRecordingState(s => s === 'recording' ? 'paused' : 'recording')}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-base"
                        style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
                      >
                        {recordingState === 'recording' ? <Pause size={12} /> : <Mic size={12} />}
                        {recordingState === 'recording' ? 'Pause' : 'Resume'}
                      </button>
                      <button
                        onClick={() => { setRecordingState('idle'); setTranscript(''); setElapsed(0) }}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-base"
                        style={{ background: 'var(--muted)', color: 'var(--muted-foreground)', border: `1px solid ${cardBorder}` }}
                      >
                        <RotateCcw size={12} />
                        Discard
                      </button>
                    </div>
                    <button
                      onClick={finishResponse}
                      className="flex items-center gap-1.5 text-xs px-4 py-1.5 rounded-lg font-medium transition-base"
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
                        onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
                        onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
                      />
                      <button
                        onClick={() => { if (typedNote) { setTranscript(t => t + (t ? '\n\n' : '') + typedNote); setTypedNote('') } }}
                        className="p-2 rounded-lg transition-base"
                        style={{ background: 'var(--primary)', color: '#fff' }}
                      >
                        <Send size={13} />
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {recordingState === 'processing' && (
                <div className="text-center py-8">
                  <div className="flex justify-center gap-1.5 mb-4">
                    {[0, 1, 2].map(i => (
                      <div
                        key={i}
                        className="w-2 h-2 rounded-full"
                        style={{
                          background: 'var(--primary)',
                          animation: `typing-dots 1.2s ease ${i * 0.2}s infinite`,
                        }}
                      />
                    ))}
                  </div>
                  <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
                    Reviewing your response against the assessment model and available evidence…
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Clarification panel */}
          {outcome === 'clarify' && (
            <div
              className="rounded-xl p-5 animate-slide-in"
              style={{ background: dark ? '#0f1d40' : '#eef3fa', border: `2px solid var(--primary)` }}
            >
              <div className="flex items-center gap-2 mb-3">
                <AlertCircle size={15} style={{ color: 'var(--primary)' }} />
                <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--primary)' }}>
                  One follow-up
                </span>
              </div>
              <p className="font-serif text-base mb-4" style={{ color: 'var(--foreground)', lineHeight: 1.6 }}>
                {CLARIFICATION}
              </p>
              <textarea
                value={clarificationText}
                onChange={e => setClarificationText(e.target.value)}
                placeholder="Type your clarification or use the microphone…"
                className="w-full rounded-lg p-3 text-sm outline-none resize-none mb-3"
                style={{
                  background: 'var(--card)',
                  border: '1px solid var(--border)',
                  color: 'var(--foreground)',
                  minHeight: 80,
                  lineHeight: 1.7,
                }}
                onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
                onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
              />
              <button
                onClick={submitClarification}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-base"
                style={{ background: 'var(--primary)', color: '#fff' }}
                onMouseEnter={e => (e.currentTarget.style.opacity = '0.88')}
                onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
              >
                <Send size={13} />
                Submit clarification
              </button>
            </div>
          )}

          {/* Sufficient coverage */}
          {outcome === 'sufficient' && (
            <div
              className="rounded-xl p-5 animate-fade-in"
              style={{ background: dark ? '#092b20' : '#d1fae5', border: `1px solid ${dark ? '#065f46' : '#6ee7b7'}` }}
            >
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle2 size={16} style={{ color: '#10b981' }} />
                <span className="text-sm font-semibold" style={{ color: dark ? '#6ee7b7' : '#065f46' }}>
                  Sufficient coverage gained
                </span>
              </div>
              <p className="text-sm mb-3" style={{ color: dark ? '#4ade80' : '#047857', lineHeight: 1.65 }}>
                This gave us enough context about how work is developed, built, and deployed.
              </p>
              <div className="space-y-1.5 mb-4">
                {[
                  { label: 'Continuous Integration', state: 'sufficiently covered', color: '#10b981' },
                  { label: 'Continuous Deployment', state: 'sufficiently covered', color: '#10b981' },
                  { label: 'Verify & validate', state: 'partially covered', color: '#f59e0b' },
                ].map(c => (
                  <div key={c.label} className="flex items-center gap-2 text-sm">
                    <div className="w-2 h-2 rounded-full" style={{ background: c.color }} />
                    <span style={{ color: dark ? '#e8edf5' : '#0f172a' }}>{c.label}</span>
                    <span className="text-xs" style={{ color: c.color }}>· {c.state}</span>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={continueNext}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-base"
                  style={{ background: '#10b981', color: '#fff' }}
                  onMouseEnter={e => (e.currentTarget.style.opacity = '0.88')}
                  onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
                >
                  Continue
                </button>
                <button
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-base"
                  style={{ background: dark ? '#0f2a1c' : '#a7f3d0', color: dark ? '#4ade80' : '#065f46' }}
                >
                  <Coffee size={13} />
                  Take a short break
                </button>
                <button
                  onClick={() => onNavigate('welcome')}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-base"
                  style={{ background: dark ? '#0f2a1c' : '#a7f3d0', color: dark ? '#4ade80' : '#065f46' }}
                >
                  <Save size={13} />
                  Save & exit
                </button>
              </div>
            </div>
          )}

          {/* Checkpoint trigger */}
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

        {/* Right: Contribution inbox or domain detail */}
        <div className="col-span-3 hidden lg:block">
          {showInbox ? (
            <div
              className="rounded-xl p-4 sticky top-32 animate-slide-in"
              style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
            >
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--muted-foreground)' }}>
                  Contributions
                </p>
                <button
                  onClick={() => setShowInbox(false)}
                  className="text-xs transition-base px-1.5 py-0.5 rounded"
                  style={{ color: 'var(--muted-foreground)' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--muted)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  Close
                </button>
              </div>
              <div className="space-y-3">
                {inboxItems.map(item => (
                  <div
                    key={item.id}
                    className="rounded-lg p-3"
                    style={{
                      background: item.status === 'pending' ? (dark ? '#141f35' : '#fffbeb') : 'var(--muted)',
                      border: `1px solid ${item.status === 'pending' ? (dark ? '#78350f' : '#fde68a') : cardBorder}`,
                    }}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-semibold" style={{ color: 'var(--foreground)' }}>{item.name}</span>
                      <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>{item.timestamp}</span>
                    </div>
                    <span
                      className="text-xs px-1.5 py-0.5 rounded mb-2 inline-block"
                      style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--muted-foreground)' }}
                    >
                      {item.topic}
                    </span>
                    <p className="text-xs mb-2.5" style={{ color: 'var(--muted-foreground)', lineHeight: 1.55 }}>
                      {item.preview.slice(0, 90)}…
                    </p>
                    {item.status === 'pending' && (
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => setInboxItems(prev => prev.map(i => i.id === item.id ? { ...i, status: 'included' } : i))}
                          className="text-xs px-2 py-1 rounded transition-base font-medium"
                          style={{ background: '#10b981', color: '#fff' }}
                        >
                          Include
                        </button>
                        <button
                          onClick={() => setInboxItems(prev => prev.map(i => i.id === item.id ? { ...i, status: 'deferred' } : i))}
                          className="text-xs px-2 py-1 rounded transition-base"
                          style={{ background: 'var(--muted)', color: 'var(--muted-foreground)', border: `1px solid ${cardBorder}` }}
                        >
                          Defer
                        </button>
                      </div>
                    )}
                    {item.status === 'included' && (
                      <span className="text-xs font-medium flex items-center gap-1" style={{ color: '#10b981' }}>
                        <CheckCircle2 size={11} /> Included
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div
              className="rounded-xl p-4 sticky top-32"
              style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
            >
              <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: 'var(--muted-foreground)' }}>
                Domains
              </p>
              {['CE', 'CI', 'CD', 'RoD'].map(domain => {
                const practices = SAMPLE_PRACTICES.filter(p => p.domain === domain)
                const suff = practices.filter(p => p.coverage === 'sufficient').length
                const total = practices.length
                return (
                  <div key={domain} className="mb-3">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-medium" style={{ color: DOMAIN_COLORS[domain] }}>{domain}</span>
                      <span className="text-xs font-mono" style={{ color: 'var(--muted-foreground)' }}>{suff}/{total}</span>
                    </div>
                    <div className="h-1.5 rounded-full overflow-hidden" style={{ background: dark ? '#1a2540' : '#e2e8f0' }}>
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${(suff / total) * 100}%`, background: DOMAIN_COLORS[domain], opacity: 0.7 }}
                      />
                    </div>
                  </div>
                )
              })}
              <div className="mt-4 pt-3" style={{ borderTop: `1px solid ${cardBorder}` }}>
                <div className="flex items-center gap-2">
                  <MessageSquare size={13} style={{ color: 'var(--muted-foreground)' }} />
                  <button
                    onClick={() => onNavigate('remote-contributor')}
                    className="text-xs transition-base"
                    style={{ color: 'var(--muted-foreground)' }}
                    onMouseEnter={e => (e.currentTarget.style.color = 'var(--foreground)')}
                    onMouseLeave={e => (e.currentTarget.style.color = 'var(--muted-foreground)')}
                  >
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
