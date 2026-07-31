import { useEffect, useState } from 'react'
import { Info } from 'lucide-react'
import { getAiSettings, getVoiceDiagnostics, updateAiSettings, type VoiceDiagnostics } from '../lib/api'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="relative inline-flex items-center rounded-full transition-base"
      style={{
        width: 40,
        height: 22,
        background: checked ? 'var(--primary)' : (document.documentElement.classList.contains('dark') ? '#1e3358' : '#cbd5e1'),
        flexShrink: 0,
      }}
    >
      <span
        className="inline-block rounded-full transition-all duration-200"
        style={{
          width: 16,
          height: 16,
          background: '#fff',
          transform: checked ? 'translateX(20px)' : 'translateX(3px)',
        }}
      />
    </button>
  )
}

function SettingRow({
  label,
  hint,
  children,
  dark,
}: {
  label: string
  hint?: string
  children: React.ReactNode
  dark: boolean
}) {
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'
  return (
    <div
      className="flex items-start justify-between gap-4 py-4"
      style={{ borderBottom: `1px solid ${cardBorder}` }}
    >
      <div className="flex-1">
        <p className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>{label}</p>
        {hint && (
          <p className="text-xs mt-0.5" style={{ color: 'var(--muted-foreground)', lineHeight: 1.5 }}>{hint}</p>
        )}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

function SelectField({
  options,
  value,
  defaultValue,
  onChange,
}: {
  options: string[]
  value?: string
  defaultValue?: string
  onChange?: (v: string) => void
}) {
  return (
    <select
      className="rounded-lg px-2.5 py-1.5 text-sm outline-none transition-base appearance-none"
      style={{
        background: 'var(--muted)',
        border: '1px solid var(--border)',
        color: 'var(--foreground)',
        minWidth: 140,
      }}
      {...(value !== undefined ? { value } : { defaultValue })}
      onChange={e => onChange?.(e.target.value)}
      onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
      onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
    >
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )
}

function NumberField({
  value,
  defaultValue,
  min,
  max,
  suffix,
  onChange,
}: {
  value?: number
  defaultValue?: number
  min: number
  max: number
  suffix?: string
  onChange?: (v: number) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        {...(value !== undefined ? { value } : { defaultValue })}
        min={min}
        max={max}
        onChange={e => onChange?.(Number(e.target.value))}
        className="w-16 rounded-lg px-2.5 py-1.5 text-sm text-right outline-none font-mono"
        style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
        onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
        onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
      />
      {suffix && <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>{suffix}</span>}
    </div>
  )
}

export default function AISettings({ dark, onNavigate }: Props) {
  const [voiceEnabled, setVoiceEnabled] = useState(true)
  const [retainAudio, setRetainAudio] = useState(false)
  const [retainTranscript, setRetainTranscript] = useState(true)
  const [remoteVoice, setRemoteVoice] = useState(false)
  const [adminRequired, setAdminRequired] = useState(true)
  const [vadEnabled, setVadEnabled] = useState(false)
  const [silenceSec, setSilenceSec] = useState(2)
  const [maxMinutes, setMaxMinutes] = useState(15)
  const [liveModel, setLiveModel] = useState('gpt-live-transcribe')
  const [finalModel, setFinalModel] = useState('gpt-transcribe')
  const [liveDelay, setLiveDelay] = useState('low')
  const [languages, setLanguages] = useState('en')
  const [companyVocabulary, setCompanyVocabulary] = useState('')
  const [finalRefinement, setFinalRefinement] = useState(true)
  const [diagnostics, setDiagnostics] = useState<VoiceDiagnostics | null>(null)
  const [saved, setSaved] = useState(false)
  const [model, setModel] = useState('gpt-5.6-terra')
  const [effort, setEffort] = useState('medium')
  const [provider, setProvider] = useState<'mock' | 'live'>('mock')
  const [models, setModels] = useState<string[]>(['gpt-5.6-terra'])
  const [efforts, setEfforts] = useState<string[]>(['low', 'medium', 'high'])
  const [error, setError] = useState<string | null>(null)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  useEffect(() => {
    getAiSettings()
      .then(data => {
        setModel(data.assessment_model)
        setEffort(data.reasoning_effort)
        setProvider(data.interview_provider)
        setModels(data.available_models)
        setEfforts(data.available_reasoning_efforts)
        setVoiceEnabled(data.voice_enabled)
        setLiveModel(data.live_transcription_model || data.transcription_model || 'gpt-live-transcribe')
        setFinalModel(data.final_transcription_model || 'gpt-transcribe')
        setLiveDelay(data.live_delay || 'high')
        setLanguages((data.expected_languages || ['en']).join(','))
        setCompanyVocabulary((data.company_vocabulary || []).join(', '))
        setFinalRefinement(data.final_refinement_enabled !== false)
        setVadEnabled(data.voice_stop_mode === 'vad')
        setSilenceSec(Math.round(data.silence_timeout_ms / 1000) || 2)
        setMaxMinutes(Math.round(data.max_recording_seconds / 60) || 15)
        setRetainAudio(data.retain_source_audio)
        setRetainTranscript(data.retain_corrected_transcript)
        setRemoteVoice(data.remote_voice_enabled)
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load AI settings'))
    getVoiceDiagnostics()
      .then(setDiagnostics)
      .catch(() => undefined)
  }, [])

  async function handleSave() {
    setError(null)
    try {
      const expected = languages
        .split(/[,\s]+/)
        .map(s => s.trim().toLowerCase())
        .filter(Boolean)
      const vocab = companyVocabulary
        .split(',')
        .map(s => s.trim())
        .filter(Boolean)
      await updateAiSettings({
        assessment_model: model,
        reasoning_effort: effort,
        interview_provider: provider,
        live_transcription_model: liveModel,
        transcription_model: liveModel,
        final_transcription_model: finalModel,
        live_delay: liveDelay as 'minimal' | 'low' | 'medium' | 'high' | 'xhigh',
        expected_languages: expected.length ? expected : ['en'],
        company_vocabulary: vocab,
        final_refinement_enabled: finalRefinement,
        voice_enabled: voiceEnabled,
        voice_language: expected[0] || 'en',
        voice_stop_mode: vadEnabled ? 'vad' : 'manual',
        silence_timeout_ms: Math.max(200, Math.min(10000, silenceSec * 1000)),
        max_recording_seconds: Math.max(30, maxMinutes * 60),
        retain_source_audio: retainAudio,
        retain_corrected_transcript: retainTranscript,
        remote_voice_enabled: remoteVoice,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
      const diag = await getVoiceDiagnostics().catch(() => null)
      if (diag) setDiagnostics(diag)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    }
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      <div className="max-w-2xl mx-auto px-6 py-10">
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs font-medium mb-3" style={{ color: 'var(--muted-foreground)' }}>
            <button onClick={() => onNavigate('welcome')} className="hover:underline">Admin</button>
            <span>/</span>
            <span>AI & Voice settings</span>
          </div>
          <h1 className="text-2xl font-semibold mb-2" style={{ color: 'var(--foreground)' }}>AI & Voice settings</h1>
          <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
            Configure transcription, AI model behavior, and evidence influence defaults. API secrets are managed under Integrations.
          </p>
        </div>

        {/* Voice settings */}
        <div
          className="rounded-xl px-5 mb-5"
          style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
        >
          <h2 className="font-semibold text-sm py-4" style={{ color: 'var(--foreground)' }}>Voice transcription</h2>

          <SettingRow label="Enable voice transcription" hint="Allow the host to use the microphone for live in-room transcription." dark={dark}>
            <Toggle checked={voiceEnabled} onChange={setVoiceEnabled} />
          </SettingRow>

          <SettingRow label="Live transcription model" hint="Pass 1: OpenAI Realtime WebRTC draft. Default gpt-live-transcribe." dark={dark}>
            <SelectField
              options={['gpt-live-transcribe', 'gpt-4o-transcribe', 'gpt-4o-mini-transcribe', 'gpt-realtime-whisper', 'whisper-1']}
              value={liveModel}
              onChange={setLiveModel}
            />
          </SettingRow>

          <SettingRow label="Final transcription model" hint="Pass 2: accuracy refinement of the finished recording. Default gpt-transcribe." dark={dark}>
            <SelectField
              options={['gpt-transcribe', 'gpt-4o-transcribe', 'gpt-4o-mini-transcribe', 'whisper-1']}
              value={finalModel}
              onChange={setFinalModel}
            />
          </SettingRow>

          <SettingRow
            label="Live delay"
            hint="For gpt-live-transcribe: higher delay = better word accuracy, slower partials. Default high. Temperature does not apply to transcription."
            dark={dark}
          >
            <SelectField
              options={['minimal', 'low', 'medium', 'high', 'xhigh']}
              value={liveDelay}
              onChange={setLiveDelay}
            />
          </SettingRow>

          <SettingRow label="Expected languages" hint="Comma-separated ISO codes, e.g. en or en,es. Default en." dark={dark}>
            <input
              value={languages}
              onChange={e => setLanguages(e.target.value)}
              className="rounded-lg px-2.5 py-1.5 text-sm outline-none w-36"
              style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
            />
          </SettingRow>

          <SettingRow label="Company vocabulary" hint="Extra keyword hints (comma-separated). Keep focused — avoid hundreds of terms." dark={dark}>
            <input
              value={companyVocabulary}
              onChange={e => setCompanyVocabulary(e.target.value)}
              placeholder="AcmeConnect, WidgetAPI"
              className="rounded-lg px-2.5 py-1.5 text-sm outline-none w-48"
              style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
            />
          </SettingRow>

          <SettingRow label="Final refinement" hint="Upload the finished answer audio once for gpt-transcribe accuracy pass." dark={dark}>
            <Toggle checked={finalRefinement} onChange={setFinalRefinement} />
          </SettingRow>

          <SettingRow label="Legacy VAD stop mode" hint="Not used for gpt-live-transcribe (turn_detection is null). Kept for older models." dark={dark}>
            <div className="flex items-center gap-3">
              <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>VAD</span>
              <Toggle checked={vadEnabled} onChange={setVadEnabled} />
            </div>
          </SettingRow>

          <SettingRow label="Silence timeout" hint="Only applies when VAD is enabled for non-live models." dark={dark}>
            <NumberField value={silenceSec} min={1} max={10} suffix="sec" onChange={setSilenceSec} />
          </SettingRow>

          <SettingRow label="Maximum recording length" hint="Hard limit per response." dark={dark}>
            <NumberField value={maxMinutes} min={1} max={60} suffix="min" onChange={setMaxMinutes} />
          </SettingRow>

          <SettingRow label="Retain audio after transcription" hint="Disabled by default. Temporary refine uploads are deleted unless this is enabled." dark={dark}>
            <Toggle checked={retainAudio} onChange={setRetainAudio} />
          </SettingRow>

          <SettingRow label="Retain corrected transcript" hint="Transcripts edited by the host are retained for the admin record." dark={dark}>
            <Toggle checked={retainTranscript} onChange={setRetainTranscript} />
          </SettingRow>

          <SettingRow label="Remote voice" hint="Not available in the initial release. Remote contributors type responses only." dark={dark}>
            <div className="flex items-center gap-2">
              <Toggle checked={remoteVoice} onChange={setRemoteVoice} />
              <span
                className="text-xs px-2 py-0.5 rounded-full"
                style={{ background: dark ? '#3b2409' : '#fef3c7', color: '#d97706' }}
              >
                Not available
              </span>
            </div>
          </SettingRow>

          {diagnostics && (
            <div className="py-4">
              <p className="text-sm font-medium mb-2" style={{ color: 'var(--foreground)' }}>Voice diagnostics (aggregates)</p>
              <p className="text-xs mb-3" style={{ color: 'var(--muted-foreground)', lineHeight: 1.5 }}>
                Safe timings and failure rates only — no audio, transcripts, or credentials.
              </p>
              <div className="grid grid-cols-2 gap-2 text-xs" style={{ color: 'var(--foreground)' }}>
                <div>Sessions: {diagnostics.session_count}</div>
                <div>Avg connect: {diagnostics.avg_connection_duration_ms ?? '—'} ms</div>
                <div>Avg first delta: {diagnostics.avg_time_to_first_delta_ms ?? '—'} ms</div>
                <div>Avg refine: {diagnostics.avg_refine_duration_ms ?? '—'} ms</div>
                <div>Empty transcripts: {diagnostics.empty_transcript_count}</div>
                <div>Refine failures: {diagnostics.refinement_failure_count}</div>
                <div>Failure rate: {diagnostics.refinement_failure_rate ?? '—'}</div>
                <div>WebRTC reconnects: {diagnostics.webrtc_reconnect_count}</div>
                <div>Mic permission fails: {diagnostics.mic_permission_failure_count}</div>
                <div>Live model: {diagnostics.live_model || '—'}</div>
                <div>Final model: {diagnostics.final_model || '—'}</div>
                <div>Last device: {diagnostics.last_device_label || '—'}</div>
              </div>
            </div>
          )}
        </div>

        {/* AI settings */}
        <div
          className="rounded-xl px-5 mb-5"
          style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
        >
          <h2 className="font-semibold text-sm py-4" style={{ color: 'var(--foreground)' }}>Assessment AI</h2>

          <SettingRow label="Interview provider" hint="Use mock for local/demo. Live uses the OpenAI Responses API." dark={dark}>
            <SelectField options={['mock', 'live']} value={provider} onChange={v => setProvider(v as 'mock' | 'live')} />
          </SettingRow>

          <SettingRow label="Assessment model" hint="Configurable default is gpt-5.6-terra. Used for coverage analysis via Responses API." dark={dark}>
            <SelectField options={models} value={model} onChange={setModel} />
          </SettingRow>

          <SettingRow label="Reasoning effort" hint="Higher reasoning produces more accurate coverage mapping at the cost of latency." dark={dark}>
            <SelectField options={efforts} value={effort} onChange={setEffort} />
          </SettingRow>

          <SettingRow label="Evidence influence default" hint="Controls how tool evidence influences scores. Can be changed per assessment." dark={dark}>
            <SelectField options={['Balanced', 'Context only', 'Evidence-led']} defaultValue="Balanced" />
          </SettingRow>

          <SettingRow label="Minimum confidence threshold" hint="Below this threshold, a practice is flagged for admin review rather than scored." dark={dark}>
            <SelectField options={['Low', 'Medium', 'High']} defaultValue="Medium" />
          </SettingRow>

          <SettingRow label="Target main question count" hint="Approximate number of main questions before the AI evaluates completeness." dark={dark}>
            <NumberField defaultValue={6} min={3} max={12} />
          </SettingRow>

          <SettingRow label="Maximum main question count" hint="Hard limit. Assessment will stop regardless of coverage gaps." dark={dark}>
            <NumberField defaultValue={10} min={5} max={20} />
          </SettingRow>

          <SettingRow label="Maximum follow-ups per topic" hint="AI will ask at most this many clarifying questions on a single topic." dark={dark}>
            <NumberField defaultValue={2} min={1} max={5} />
          </SettingRow>

          <SettingRow label="Admin review required before publication" hint="If disabled, results are published immediately after the interview." dark={dark}>
            <Toggle checked={adminRequired} onChange={setAdminRequired} />
          </SettingRow>
        </div>

        <div
          className="rounded-xl p-4 flex items-start gap-3 mb-6"
          style={{ background: dark ? '#141f35' : '#f8fafc', border: `1px solid ${cardBorder}` }}
        >
          <Info size={14} style={{ color: 'var(--muted-foreground)', marginTop: 1, flexShrink: 0 }} />
          <p className="text-sm" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
            AI and voice settings apply to all new assessments. Existing in-progress assessments are not affected.
          </p>
        </div>

        {error && <div className="mb-4 text-sm" style={{ color: '#dc2626' }}>{error}</div>}

        <div className="flex items-center justify-end gap-3">
          <button
            onClick={() => onNavigate('welcome')}
            className="px-4 py-2.5 rounded-lg text-sm transition-base"
            style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
          >
            Cancel
          </button>
          <button
            onClick={() => void handleSave()}
            className="px-5 py-2.5 rounded-lg text-sm font-semibold transition-base"
            style={{ background: saved ? '#10b981' : 'var(--primary)', color: '#fff' }}
            onMouseEnter={e => { if (!saved) e.currentTarget.style.opacity = '0.88' }}
            onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
          >
            {saved ? 'Saved' : 'Save settings'}
          </button>
        </div>
      </div>
    </div>
  )
}
