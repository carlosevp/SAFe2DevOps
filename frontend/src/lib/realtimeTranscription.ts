import {
  createRealtimeSession,
  reportVoiceClientEvent,
  type RealtimeSessionCredentials,
} from './api'
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
  if (typeof window !== 'undefined' && !window.isSecureContext) {
    return 'Microphone requires HTTPS. Open the Railway URL directly in a browser tab.'
  }
  if (err instanceof DOMException || err instanceof Error) {
    const name = 'name' in err ? String(err.name) : ''
    const message = err.message || name || 'Microphone error'
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
      return 'Microphone permission denied. Continue with typed response.'
    }
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      return 'No microphone found. Continue with typed response.'
    }
    if (name === 'NotReadableError' || name === 'TrackStartError') {
      return 'Microphone is already in use by another application.'
    }
    if (
      name === 'OverconstrainedError' ||
      name === 'ConstraintNotSatisfiedError' ||
      name === 'InvalidConstraintError' ||
      /invalid constraint/i.test(message)
    ) {
      return (
        'Browser blocked microphone access (Invalid constraint). ' +
        'Open the app in a normal browser tab (not an embedded preview) over HTTPS, then allow the mic.'
      )
    }
    if (name === 'TypeError' && /mediaDevices|getUserMedia|undefined/i.test(message)) {
      return 'Microphone API unavailable. Use HTTPS in a full browser tab.'
    }
    return message
  }
  return 'Failed to start voice capture'
}

/** Request mic access immediately (must stay in the click/user-gesture stack). */
async function requestMicrophoneStream(): Promise<MediaStream> {
  if (typeof window !== 'undefined' && !window.isSecureContext) {
    throw new Error('Microphone requires HTTPS. Open the Railway URL directly in a browser tab.')
  }
  const mediaDevices = navigator.mediaDevices
  if (!mediaDevices?.getUserMedia) {
    throw new Error('Microphone API unavailable in this browser. Try Chrome/Edge/Safari over HTTPS.')
  }

  // Use the most permissive constraint forms. Object constraints are a common
  // "Invalid constraint" source on some browsers / embedded webviews.
  try {
    return await mediaDevices.getUserMedia({ audio: true, video: false })
  } catch (first) {
    const msg = first instanceof Error ? first.message : ''
    if (!/invalid constraint|Overconstrained|ConstraintNotSatisfied/i.test(msg) && !(first instanceof DOMException && /Constraint/i.test(first.name))) {
      throw first
    }
    try {
      return await mediaDevices.getUserMedia({ audio: true })
    } catch {
      return await mediaDevices.getUserMedia({ audio: {} })
    }
  }
}

async function waitForIceGathering(pc: RTCPeerConnection, timeoutMs = 2500): Promise<void> {
  if (pc.iceGatheringState === 'complete') return
  await new Promise<void>(resolve => {
    const done = () => {
      if (pc.iceGatheringState === 'complete') {
        pc.removeEventListener('icegatheringstatechange', done)
        resolve()
      }
    }
    pc.addEventListener('icegatheringstatechange', done)
    setTimeout(() => {
      pc.removeEventListener('icegatheringstatechange', done)
      resolve()
    }, timeoutMs)
  })
}

function reportClientFailure(stage: string, err: unknown) {
  const name = err instanceof Error ? err.name : typeof err
  const message = err instanceof Error ? err.message : String(err)
  void reportVoiceClientEvent({
    stage,
    name,
    message: message.slice(0, 300),
    secure_context: typeof window !== 'undefined' ? window.isSecureContext : null,
    in_iframe: typeof window !== 'undefined' ? window.self !== window.top : null,
    user_agent: typeof navigator !== 'undefined' ? navigator.userAgent.slice(0, 180) : null,
  }).catch(() => {
    // best-effort diagnostics only
  })
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

    // 1) Mic first — must run before any await that leaves the user-gesture stack,
    // otherwise browsers often skip the permission prompt and fail oddly.
    let stream: MediaStream
    try {
      stream = await requestMicrophoneStream()
      this.session.stream = stream
      this.dispatch({ type: 'PERMISSION_GRANTED' })
    } catch (err) {
      reportClientFailure('getUserMedia', err)
      const message = mediaErrorMessage(err)
      if (/Permission|NotAllowed|Denied/i.test(message)) {
        this.dispatch({ type: 'PERMISSION_DENIED', message })
      } else {
        this.dispatch({ type: 'ERROR', message })
        this.dispatch({ type: 'FALLBACK_TEXT' })
      }
      this.teardownMedia()
      return
    }

    // 2) Then mint/session metadata + live/mock connection.
    try {
      const credentials = await createRealtimeSession()
      this.session.credentials = credentials
      this.session.maxSeconds = credentials.max_recording_seconds
      this.callbacks.onPrivacyNotice?.(credentials.privacy.privacy_notice)

      if (!credentials.voice_enabled) {
        this.dispatch({ type: 'FALLBACK_TEXT' })
        this.dispatch({ type: 'ERROR', message: 'Voice is disabled in admin settings. Use typed response.' })
        this.teardownMedia()
        return
      }

      if (credentials.provider === 'mock' || credentials.client_secret.startsWith('ek_mock_')) {
        await this.startMock(stream)
      } else {
        await this.startLive(credentials, stream)
      }
      this.beginTimers()
    } catch (err) {
      reportClientFailure('realtime_session', err)
      const message = mediaErrorMessage(err)
      this.dispatch({ type: 'ERROR', message })
      this.dispatch({ type: 'FALLBACK_TEXT' })
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
      const stream = this.session.stream || (await requestMicrophoneStream())
      this.session.stream = stream
      this.dispatch({ type: 'PERMISSION_GRANTED' })
      const credentials = await createRealtimeSession()
      this.session.credentials = credentials
      if (credentials.provider === 'mock' || credentials.client_secret.startsWith('ek_mock_')) {
        await this.startMock(stream)
      } else {
        await this.startLive(credentials, stream)
      }
      this.dispatch({ type: 'RECONNECTED' })
    } catch (err) {
      reportClientFailure('recover', err)
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

    // Build a complete WHIP-style offer (wait briefly for ICE), then POST SDP
    // directly to OpenAI with the ephemeral key — not through our multipart proxy.
    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    await waitForIceGathering(pc)
    const sdp = pc.localDescription?.sdp || offer.sdp || ''
    if (!sdp.includes('v=0') || sdp.trim().length < 32) {
      throw new Error('Failed to build a WebRTC SDP offer for Realtime transcription')
    }

    try {
      const sdpResponse = await fetch(credentials.realtime_calls_url, {
        method: 'POST',
        body: sdp,
        headers: {
          Authorization: `Bearer ${credentials.client_secret}`,
          'Content-Type': 'application/sdp',
        },
      })
      const answerBody = await sdpResponse.text()
      if (!sdpResponse.ok) {
        let message = answerBody.slice(0, 240) || `Realtime call failed (${sdpResponse.status})`
        try {
          const payload = JSON.parse(answerBody) as { error?: { message?: string } }
          if (payload.error?.message) message = payload.error.message
        } catch {
          // plain text / SDP error body
        }
        if (sdpResponse.status === 401 || sdpResponse.status === 403) {
          this.dispatch({ type: 'SESSION_EXPIRED' })
          void this.recover()
          return
        }
        throw new Error(message)
      }
      if (!answerBody.includes('v=0')) {
        throw new Error('Realtime API returned an invalid SDP answer')
      }
      await pc.setRemoteDescription({ type: 'answer', sdp: answerBody })
    } catch (err) {
      reportClientFailure('realtime_call', err)
      throw err
    }
    this.dispatch({ type: 'CONNECTED' })
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
        reportClientFailure('realtime_event', new Error(message))
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
