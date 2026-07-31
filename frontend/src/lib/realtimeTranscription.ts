import { createRealtimeSession, exchangeRealtimeCall, type RealtimeSessionCredentials } from './api'
import {
  createMicContext,
  displayTranscript,
  reduceMic,
  type MicContext,
  type MicEvent,
} from './voiceStateMachine'

export type TranscriptionCallbacks = {
  onContext: (ctx: MicContext) => void
  onPrivacyNotice?: (notice: string) => void
}

type ActiveSession = {
  pc: RTCPeerConnection | null
  dc: RTCDataChannel | null
  stream: MediaStream | null
  credentials: RealtimeSessionCredentials | null
  mockTimer: ReturnType<typeof setInterval> | null
  elapsedTimer: ReturnType<typeof setInterval> | null
  startedAt: number | null
  pausedAccumMs: number
  pauseStartedAt: number | null
  maxSeconds: number
}

const MOCK_SCRIPT =
  'Jordan: We pick up a card after planning and work in a feature branch.\n\n' +
  'Sam: The pipeline runs unit tests on every pull request before merge.\n\n' +
  'Alex: After merge, CI deploys to staging and we manually promote to production while watching dashboards.'

function mediaErrorMessage(err: unknown): string {
  if (err instanceof DOMException) {
    if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
      return 'Microphone permission denied. Continue with typed response.'
    }
    if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
      return 'No microphone found. Continue with typed response.'
    }
    if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
      return 'Microphone is already in use by another application.'
    }
    if (err.name === 'OverconstrainedError' || err.name === 'ConstraintNotSatisfiedError') {
      return 'Microphone constraints are not supported on this device. Try typed response.'
    }
    return err.message || err.name
  }
  if (err instanceof Error) return err.message
  return 'Failed to start voice capture'
}

export class RealtimeTranscriptionController {
  private ctx: MicContext = createMicContext()
  private session: ActiveSession = {
    pc: null,
    dc: null,
    stream: null,
    credentials: null,
    mockTimer: null,
    elapsedTimer: null,
    startedAt: null,
    pausedAccumMs: 0,
    pauseStartedAt: null,
    maxSeconds: 900,
  }
  private callbacks: TranscriptionCallbacks
  private typedNoteBuffer = ''
  elapsedSeconds = 0

  constructor(callbacks: TranscriptionCallbacks) {
    this.callbacks = callbacks
  }

  getContext() {
    return this.ctx
  }

  getDisplayText() {
    const base = displayTranscript(this.ctx)
    if (!this.typedNoteBuffer) return base
    return [base, this.typedNoteBuffer].filter(Boolean).join('\n\n')
  }

  dispatch(event: MicEvent) {
    this.ctx = reduceMic(this.ctx, event)
    this.callbacks.onContext(this.ctx)
  }

  async start() {
    this.dispatch({ type: 'START' })
    try {
      const credentials = await createRealtimeSession()
      this.session.credentials = credentials
      this.session.maxSeconds = credentials.max_recording_seconds
      this.callbacks.onPrivacyNotice?.(credentials.privacy.privacy_notice)

      if (!credentials.voice_enabled) {
        this.dispatch({ type: 'FALLBACK_TEXT' })
        this.dispatch({ type: 'ERROR', message: 'Voice is disabled in admin settings. Use typed response.' })
        return
      }

      // Keep constraints minimal — object constraints are a common "Invalid constraint" source.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      this.session.stream = stream
      this.dispatch({ type: 'PERMISSION_GRANTED' })

      if (credentials.provider === 'mock' || credentials.client_secret.startsWith('ek_mock_')) {
        await this.startMock(stream)
      } else {
        await this.startLive(credentials, stream)
      }
      this.beginTimers()
    } catch (err) {
      const message = mediaErrorMessage(err)
      if (/Permission|NotAllowed|Denied/i.test(message)) {
        this.dispatch({ type: 'PERMISSION_DENIED', message })
      } else {
        this.dispatch({ type: 'ERROR', message })
        this.dispatch({ type: 'FALLBACK_TEXT' })
      }
      this.teardownMedia()
    }
  }

  pause() {
    if (this.ctx.state !== 'listening') return
    this.session.stream?.getAudioTracks().forEach(t => {
      t.enabled = false
    })
    this.session.pauseStartedAt = Date.now()
    this.dispatch({ type: 'PAUSE' })
  }

  resume() {
    if (this.ctx.state !== 'paused') return
    if (this.session.pauseStartedAt) {
      this.session.pausedAccumMs += Date.now() - this.session.pauseStartedAt
      this.session.pauseStartedAt = null
    }
    this.session.stream?.getAudioTracks().forEach(t => {
      t.enabled = true
    })
    this.dispatch({ type: 'RESUME' })
  }

  async finish() {
    if (this.ctx.state !== 'listening' && this.ctx.state !== 'paused') return
    this.dispatch({ type: 'FINISH' })
    try {
      if (this.session.dc && this.session.dc.readyState === 'open') {
        this.session.dc.send(JSON.stringify({ type: 'input_audio_buffer.commit' }))
      }
    } catch {
      // ignore commit failures; transcript already buffered
    }
    this.stopTimers()
    this.teardownMedia()
  }

  discard() {
    this.stopTimers()
    this.teardownMedia()
    this.typedNoteBuffer = ''
    this.elapsedSeconds = 0
    this.dispatch({ type: 'DISCARD' })
  }

  appendTypedNote(note: string) {
    const cleaned = note.trim()
    if (!cleaned) return
    this.typedNoteBuffer = [this.typedNoteBuffer, cleaned].filter(Boolean).join('\n')
    if (this.ctx.state === 'ready_to_edit' || this.ctx.state === 'fallback_text' || this.ctx.state === 'idle') {
      const merged = [this.ctx.finalTranscript, cleaned].filter(Boolean).join('\n\n')
      this.ctx = { ...this.ctx, finalTranscript: merged }
      this.callbacks.onContext(this.ctx)
    }
  }

  async recover() {
    if (this.ctx.state !== 'reconnecting') return
    if (this.ctx.reconnectAttempts > 2) {
      this.dispatch({ type: 'RECONNECT_FAILED' })
      this.teardownMedia()
      return
    }
    try {
      this.teardownMedia(false)
      const credentials = await createRealtimeSession()
      this.session.credentials = credentials
      const stream = this.session.stream || (await navigator.mediaDevices.getUserMedia({ audio: true }))
      this.session.stream = stream
      this.dispatch({ type: 'PERMISSION_GRANTED' })
      if (credentials.provider === 'mock' || credentials.client_secret.startsWith('ek_mock_')) {
        await this.startMock(stream)
      } else {
        await this.startLive(credentials, stream)
      }
      this.dispatch({ type: 'RECONNECTED' })
    } catch {
      this.dispatch({ type: 'RECONNECT_FAILED' })
      this.teardownMedia()
    }
  }

  private async startMock(stream: MediaStream) {
    this.dispatch({ type: 'CONNECTED' })
    let idx = 0
    this.session.mockTimer = setInterval(() => {
      if (this.ctx.state !== 'listening') return
      idx = Math.min(idx + 12, MOCK_SCRIPT.length)
      this.dispatch({ type: 'PARTIAL', text: MOCK_SCRIPT.slice(0, idx) })
      if (idx >= MOCK_SCRIPT.length && this.session.mockTimer) {
        clearInterval(this.session.mockTimer)
        this.session.mockTimer = null
        this.dispatch({ type: 'FINAL_SEGMENT', text: MOCK_SCRIPT })
      }
    }, 80)
    void stream
  }

  private async startLive(credentials: RealtimeSessionCredentials, stream: MediaStream) {
    const pc = new RTCPeerConnection()
    this.session.pc = pc
    const audioTrack = stream.getAudioTracks()[0]
    if (!audioTrack) {
      throw new Error('No audio track available from the microphone')
    }
    pc.addTrack(audioTrack, stream)

    const dc = pc.createDataChannel('oai-events')
    this.session.dc = dc
    dc.addEventListener('message', event => {
      this.handleServerEvent(String(event.data))
    })
    pc.addEventListener('connectionstatechange', () => {
      if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
        this.dispatch({ type: 'DISCONNECT' })
        void this.recover()
      }
    })

    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    // Server-mediated SDP exchange keeps the OpenAI key off the browser and logs failures.
    const answerSdp = await exchangeRealtimeCall(offer.sdp || '')
    await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp })
    this.dispatch({ type: 'CONNECTED' })
    void credentials
  }

  private handleServerEvent(raw: string) {
    try {
      const event = JSON.parse(raw) as {
        type?: string
        delta?: string
        transcript?: string
        error?: { message?: string; code?: string }
      }
      const type = event.type || ''
      if (type.includes('transcription.delta') && typeof event.delta === 'string') {
        const next = `${this.ctx.partialTranscript}${event.delta}`
        this.dispatch({ type: 'PARTIAL', text: next })
      }
      if (type.includes('transcription.completed') && typeof event.transcript === 'string') {
        this.dispatch({ type: 'FINAL_SEGMENT', text: event.transcript })
      }
      if (type === 'error') {
        const message = event.error?.message || 'Realtime transcription error'
        this.dispatch({ type: 'ERROR', message })
        this.dispatch({ type: 'FALLBACK_TEXT' })
        this.teardownMedia()
      }
    } catch {
      // ignore malformed events
    }
  }

  private beginTimers() {
    this.session.startedAt = Date.now()
    this.session.pausedAccumMs = 0
    this.session.pauseStartedAt = null
    this.elapsedSeconds = 0
    this.session.elapsedTimer = setInterval(() => {
      if (!this.session.startedAt) return
      if (this.ctx.state === 'paused' && this.session.pauseStartedAt) {
        return
      }
      const pausedExtra = this.session.pauseStartedAt ? Date.now() - this.session.pauseStartedAt : 0
      const ms = Date.now() - this.session.startedAt - this.session.pausedAccumMs - pausedExtra
      this.elapsedSeconds = Math.max(0, Math.floor(ms / 1000))
      if (this.elapsedSeconds >= this.session.maxSeconds) {
        void this.finish()
      }
    }, 250)
  }

  private stopTimers() {
    if (this.session.mockTimer) clearInterval(this.session.mockTimer)
    if (this.session.elapsedTimer) clearInterval(this.session.elapsedTimer)
    this.session.mockTimer = null
    this.session.elapsedTimer = null
  }

  private teardownMedia(clearStream = true) {
    try {
      this.session.dc?.close()
    } catch {
      // ignore
    }
    try {
      this.session.pc?.close()
    } catch {
      // ignore
    }
    if (clearStream) {
      this.session.stream?.getTracks().forEach(t => t.stop())
      this.session.stream = null
    }
    this.session.pc = null
    this.session.dc = null
  }
}
