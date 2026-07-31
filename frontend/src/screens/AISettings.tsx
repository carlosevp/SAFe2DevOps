import { useEffect, useState } from 'react'
import { Info } from 'lucide-react'
import { getAiSettings, updateAiSettings } from '../lib/api'
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

function NumberField({ defaultValue, min, max, suffix }: { defaultValue: number; min: number; max: number; suffix?: string }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        defaultValue={defaultValue}
        min={min}
        max={max}
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
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [retainAudio, setRetainAudio] = useState(false)
  const [retainTranscript, setRetainTranscript] = useState(true)
  const [remoteVoice, setRemoteVoice] = useState(false)
  const [adminRequired, setAdminRequired] = useState(true)
  const [vadEnabled, setVadEnabled] = useState(true)
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
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load AI settings'))
  }, [])

  async function handleSave() {
    setError(null)
    try {
      await updateAiSettings({
        assessment_model: model,
        reasoning_effort: effort,
        interview_provider: provider,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
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

          <SettingRow label="Transcription model" hint="Higher accuracy models have longer latency." dark={dark}>
            <SelectField options={['Whisper large-v3', 'Whisper medium', 'Whisper small (fast)']} defaultValue="Whisper large-v3" />
          </SettingRow>

          <SettingRow label="Language" hint="Auto-detect works well for English-primary sessions." dark={dark}>
            <SelectField options={['Auto-detect', 'English', 'German', 'Spanish', 'French']} />
          </SettingRow>

          <SettingRow label="Stop detection" hint="Voice-activity detection ends recording automatically on silence." dark={dark}>
            <div className="flex items-center gap-3">
              <span className="text-xs" style={{ color: 'var(--muted-foreground)' }}>VAD</span>
              <Toggle checked={vadEnabled} onChange={setVadEnabled} />
            </div>
          </SettingRow>

          <SettingRow label="Silence timeout" hint="Seconds of silence before VAD stops recording." dark={dark}>
            <NumberField defaultValue={4} min={2} max={30} suffix="sec" />
          </SettingRow>

          <SettingRow label="Maximum recording length" hint="Hard limit per response." dark={dark}>
            <NumberField defaultValue={15} min={3} max={60} suffix="min" />
          </SettingRow>

          <SettingRow label="Retain audio after transcription" hint="Disabled by default. Enable only if required for audit purposes." dark={dark}>
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
