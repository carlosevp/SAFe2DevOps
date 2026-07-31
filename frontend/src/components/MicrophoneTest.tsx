import { useEffect, useRef, useState } from 'react'
import { Mic, Square } from 'lucide-react'
import { listAudioInputDevices, requestMicrophoneStream } from '../lib/realtimeTranscription'
import { createRealtimeSession, refineVoiceTranscript } from '../lib/api'

type Props = {
  dark: boolean
  onDeviceSelected?: (deviceId: string | null) => void
}

/**
 * Optional pre-workshop microphone check.
 * Does not claim distant-laptop-mic reliability for conference rooms.
 */
export default function MicrophoneTest({ dark, onDeviceSelected }: Props) {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [deviceId, setDeviceId] = useState<string>('')
  const [level, setLevel] = useState(0)
  const [clipping, setClipping] = useState(false)
  const [lowVolume, setLowVolume] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testTranscript, setTestTranscript] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const rafRef = useRef<number | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)

  useEffect(() => {
    return () => stopMeter()
  }, [])

  async function refreshDevices() {
    try {
      // Permission first so labels populate.
      const stream = await requestMicrophoneStream(deviceId || null)
      stream.getTracks().forEach(t => t.stop())
      const list = await listAudioInputDevices()
      setDevices(list)
      if (list[0] && !deviceId) {
        setDeviceId(list[0].deviceId)
        onDeviceSelected?.(list[0].deviceId)
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Could not access microphone')
    }
  }

  function stopMeter() {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
    analyserRef.current = null
    void audioCtxRef.current?.close()
    audioCtxRef.current = null
  }

  async function startMeter() {
    stopMeter()
    setMessage(null)
    try {
      const stream = await requestMicrophoneStream(deviceId || null)
      streamRef.current = stream
      const ctx = new AudioContext()
      audioCtxRef.current = ctx
      const source = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 2048
      source.connect(analyser)
      analyserRef.current = analyser
      const data = new Uint8Array(analyser.fftSize)
      let peakRecent = 0
      const tick = () => {
        analyser.getByteTimeDomainData(data)
        let sum = 0
        let peak = 0
        for (let i = 0; i < data.length; i++) {
          const v = (data[i] - 128) / 128
          sum += v * v
          peak = Math.max(peak, Math.abs(v))
        }
        const rms = Math.sqrt(sum / data.length)
        setLevel(Math.min(1, rms * 4))
        setClipping(peak > 0.95)
        peakRecent = Math.max(peakRecent * 0.98, rms)
        setLowVolume(peakRecent < 0.02)
        rafRef.current = requestAnimationFrame(tick)
      }
      tick()
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Meter failed')
    }
  }

  async function runFiveSecondTest() {
    setTesting(true)
    setTestTranscript(null)
    setMessage('Recording 5 seconds… speak at a normal workshop volume.')
    stopMeter()
    let stream: MediaStream | null = null
    try {
      stream = await requestMicrophoneStream(deviceId || null)
      const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'
      const chunks: BlobPart[] = []
      const recorder = new MediaRecorder(stream, { mimeType: mime })
      recorder.ondataavailable = e => {
        if (e.data.size) chunks.push(e.data)
      }
      const stopped = new Promise<Blob>(resolve => {
        recorder.onstop = () => resolve(new Blob(chunks, { type: mime }))
      })
      recorder.start()
      await new Promise(r => setTimeout(r, 5000))
      recorder.stop()
      const blob = await stopped
      stream.getTracks().forEach(t => t.stop())

      // Prefer final refine path for the short test; mock works without OpenAI.
      await createRealtimeSession()
      const result = await refineVoiceTranscript({
        blob,
        liveTranscript: '',
        filename: 'mic-test.webm',
      })
      setTestTranscript(result.transcript || '(empty transcript)')
      setMessage(
        'Mic test complete. For in-room workshops, place a dedicated conference microphone near participants. ' +
          'A laptop mic often misses distant speakers.',
      )
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Mic test failed')
    } finally {
      stream?.getTracks().forEach(t => t.stop())
      setTesting(false)
    }
  }

  const border = dark ? '#1e3358' : '#e2e8f0'

  return (
    <div className="rounded-xl p-4 space-y-3" style={{ border: `1px solid ${border}`, background: 'var(--card)' }}>
      <div>
        <p className="text-sm font-semibold" style={{ color: 'var(--foreground)' }}>Pre-workshop microphone test</p>
        <p className="text-xs mt-1" style={{ color: 'var(--muted-foreground)', lineHeight: 1.5 }}>
          Check input level before the session. Distant participants on a poor laptop microphone are not reliably captured.
        </p>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <button
          type="button"
          onClick={() => void refreshDevices()}
          className="text-xs px-3 py-1.5 rounded-lg"
          style={{ background: 'var(--muted)', border: `1px solid ${border}` }}
        >
          List microphones
        </button>
        <select
          value={deviceId}
          onChange={e => {
            setDeviceId(e.target.value)
            onDeviceSelected?.(e.target.value || null)
          }}
          className="text-xs px-2 py-1.5 rounded-lg flex-1 min-w-[180px]"
          style={{ background: 'var(--muted)', border: `1px solid ${border}`, color: 'var(--foreground)' }}
        >
          <option value="">Default input</option>
          {devices.map(d => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.label || `Microphone ${d.deviceId.slice(0, 6)}`}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => void startMeter()}
          className="text-xs px-3 py-1.5 rounded-lg flex items-center gap-1"
          style={{ background: 'var(--primary)', color: '#fff' }}
        >
          <Mic size={12} /> Level meter
        </button>
        <button
          type="button"
          onClick={stopMeter}
          className="text-xs px-3 py-1.5 rounded-lg flex items-center gap-1"
          style={{ background: 'var(--muted)', border: `1px solid ${border}` }}
        >
          <Square size={11} /> Stop meter
        </button>
        <button
          type="button"
          disabled={testing}
          onClick={() => void runFiveSecondTest()}
          className="text-xs px-3 py-1.5 rounded-lg"
          style={{ background: 'var(--muted)', border: `1px solid ${border}`, opacity: testing ? 0.6 : 1 }}
        >
          {testing ? 'Testing…' : '5s test recording'}
        </button>
      </div>

      <div className="h-2 rounded-full overflow-hidden" style={{ background: dark ? '#1e3358' : '#e2e8f0' }}>
        <div
          className="h-full transition-[width] duration-75"
          style={{
            width: `${Math.round(level * 100)}%`,
            background: clipping ? '#dc2626' : lowVolume ? '#f59e0b' : '#0f8b8d',
          }}
        />
      </div>
      {clipping && <p className="text-xs" style={{ color: '#dc2626' }}>Clipping detected — lower input gain or move back from the mic.</p>}
      {lowVolume && !clipping && (
        <p className="text-xs" style={{ color: '#d97706' }}>
          Low volume — move closer or choose a better microphone.
        </p>
      )}
      {message && <p className="text-xs" style={{ color: 'var(--muted-foreground)', lineHeight: 1.5 }}>{message}</p>}
      {testTranscript && (
        <div className="text-xs rounded-lg p-2" style={{ background: 'var(--muted)', color: 'var(--foreground)' }}>
          <span className="font-medium">Test transcript: </span>{testTranscript}
        </div>
      )}
    </div>
  )
}
