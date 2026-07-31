import {
  createRealtimeSession,
  refineVoiceTranscript,
  reportVoiceClientEvent,
  reportVoiceMetrics,
  type RealtimeSessionCredentials,
} from './api'
import {
  applyCompleted,
  applyDelta,
  clearItems,
  completedRealtimeText,
  createTranscriptStore,
  displayAnswerText,
  itemCount,
  liveDraftText,
  type TranscriptStore,
} from './transcriptReconciliation'
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
  onDiagnostics?: (diag: SessionDiagnostics) => void
}

export type SessionDiagnostics = {
  liveDraft: string
  completedRealtime: string
  refinedFinal: string
  connectionState: string
  itemIds: string[]
  timeToFirstDeltaMs: number | null
  refineDurationMs: number | null
  deviceLabel: string | null
  liveModel: string | null
  finalModel: string | null
}

type ActiveSession = {
  pc: RTCPeerConnection | null
  dc: RTCDataChannel | null
  stream: MediaStream | null
  recorder: MediaRecorder | null
  chunks: BlobPart[]
  mimeType: string
  credentials: RealtimeSessionCredentials | null
  mockTimer: ReturnType<typeof setInterval> | null
  elapsedTimer: ReturnType<typeof setInterval> | null
  startedAt: number | null
  connectedAt: number | null
  pausedAccumMs: number
  pauseStartedAt: number | null
  maxSeconds: number
  firstDeltaAt: number | null
  deviceLabel: string | null
  audioBlob: Blob | null
}

const MOCK_SCRIPT =
  'Jordan: We pick up a card after planning and work in a feature branch.\n\n' +
  'Sam: The pipeline runs unit tests on every pull request before merge.\n\n' +
  'Alex: After merge, CI deploys to staging and we manually promote to production while watching dashboards.'

function preferredRecorderMime(): string {
  // Prefer mp4/m4a on Apple browsers — OpenAI accepts it reliably. Chrome still
  // uses webm/opus when that is the only supported recorder type.
  const apple = typeof navigator !== 'undefined' && /Mac|iPhone|iPad|Safari/i.test(navigator.userAgent) && !/Chrom(e|ium)|Android/i.test(navigator.userAgent)
  const candidates = apple
    ? ['audio/mp4', 'audio/aac', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
    : ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  if (typeof MediaRecorder === 'undefined') return 'audio/webm'
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported(type)) return type
  }
  return ''
}

function recorderFilename(mimeType: string): string {
  const mime = (mimeType || '').toLowerCase()
  if (mime.includes('mp4') || mime.includes('m4a') || mime.includes('aac')) return 'capture.m4a'
  if (mime.includes('ogg')) return 'capture.ogg'
  if (mime.includes('wav')) return 'capture.wav'
  return 'capture.webm'
}

/** How long to keep the Realtime channel open after commit so delayed transcripts can arrive. */
export function postCommitWaitMs(liveDelay: string | undefined | null): number {
  switch ((liveDelay || 'medium').toLowerCase()) {
    case 'minimal':
      return 1500
    case 'low':
      return 2500
    case 'medium':
      return 4500
    case 'high':
      return 8000
    case 'xhigh':
      return 12000
    default:
      return 4500
  }
}

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

export async function requestMicrophoneStream(deviceId?: string | null): Promise<MediaStream> {
  if (typeof window !== 'undefined' && !window.isSecureContext) {
    throw new Error('Microphone requires HTTPS. Open the Railway URL directly in a browser tab.')
  }
  const mediaDevices = navigator.mediaDevices
  if (!mediaDevices?.getUserMedia) {
    throw new Error('Microphone API unavailable in this browser. Try Chrome/Edge/Safari over HTTPS.')
  }

  const idealConstraints: MediaStreamConstraints = {
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
      ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
    },
    video: false,
  }

  try {
    return await mediaDevices.getUserMedia(idealConstraints)
  } catch (first) {
    // Do not force sampleRate — retry without deviceId, then permissive audio.
    try {
      return await mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
        video: false,
      })
    } catch {
      try {
        return await mediaDevices.getUserMedia({ audio: true, video: false })
      } catch {
        const msg = first instanceof Error ? first.message : String(first)
        if (/invalid constraint|Overconstrained|ConstraintNotSatisfied/i.test(msg)) {
          return await mediaDevices.getUserMedia({ audio: true })
        }
        throw first
      }
    }
  }
}

export async function listAudioInputDevices(): Promise<MediaDeviceInfo[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return []
  const devices = await navigator.mediaDevices.enumerateDevices()
  return devices.filter(d => d.kind === 'audioinput')
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
    // best-effort
  })
}

export class RealtimeTranscriptionController {
  private ctx: MicContext = createMicContext()
  private store: TranscriptStore = createTranscriptStore()
  private session: ActiveSession = {
    pc: null,
    dc: null,
    stream: null,
    recorder: null,
    chunks: [],
    mimeType: 'audio/webm',
    credentials: null,
    mockTimer: null,
    elapsedTimer: null,
    startedAt: null,
    connectedAt: null,
    pausedAccumMs: 0,
    pauseStartedAt: null,
    maxSeconds: 900,
    firstDeltaAt: null,
    deviceLabel: null,
    audioBlob: null,
  }
  private callbacks: TranscriptionCallbacks
  private typedNoteBuffer = ''
  private assessmentId: string | null = null
  private topicLabel: string | null = null
  private preferredDeviceId: string | null = null
  private refinedFinal = ''
  private refineDurationMs: number | null = null
  elapsedSeconds = 0

  constructor(callbacks: TranscriptionCallbacks) {
    this.callbacks = callbacks
  }

  setAssessmentContext(assessmentId: string | null, topicLabel?: string | null) {
    this.assessmentId = assessmentId
    this.topicLabel = topicLabel || null
  }

  setPreferredDeviceId(deviceId: string | null) {
    this.preferredDeviceId = deviceId
  }

  getContext() {
    return this.ctx
  }

  getDisplayText() {
    if (
      this.ctx.state === 'ready_to_edit' ||
      this.ctx.state === 'refinement_failed' ||
      this.ctx.state === 'finishing' ||
      this.ctx.state === 'refining'
    ) {
      return displayTranscript(this.ctx)
    }
    const base = displayAnswerText(this.store)
    if (!this.typedNoteBuffer) return base
    return [base, this.typedNoteBuffer].filter(Boolean).join('\n\n')
  }

  getDiagnostics(): SessionDiagnostics {
    return {
      liveDraft: liveDraftText(this.store) || this.ctx.liveDraftFrozen,
      completedRealtime: completedRealtimeText(this.store),
      refinedFinal: this.refinedFinal || this.ctx.refinedTranscript,
      connectionState: this.session.pc?.connectionState || this.ctx.state,
      itemIds: [...this.store.items.keys()],
      timeToFirstDeltaMs:
        this.session.firstDeltaAt && this.session.connectedAt
          ? this.session.firstDeltaAt - this.session.connectedAt
          : null,
      refineDurationMs: this.refineDurationMs,
      deviceLabel: this.session.deviceLabel,
      liveModel: this.session.credentials?.live_transcription_model || null,
      finalModel: this.session.credentials?.final_transcription_model || null,
    }
  }

  dispatch(event: MicEvent) {
    this.ctx = reduceMic(this.ctx, event)
    this.callbacks.onContext(this.ctx)
    this.callbacks.onDiagnostics?.(this.getDiagnostics())
  }

  async start() {
    this.dispatch({ type: 'START' })
    this.store = clearItems(this.store, false)
    this.refinedFinal = ''
    this.refineDurationMs = null
    this.session.chunks = []
    this.session.audioBlob = null
    this.session.firstDeltaAt = null

    let stream: MediaStream
    try {
      stream = await requestMicrophoneStream(this.preferredDeviceId)
      this.session.stream = stream
      const track = stream.getAudioTracks()[0]
      this.session.deviceLabel = track?.label || null
      this.dispatch({ type: 'PERMISSION_GRANTED' })
    } catch (err) {
      reportClientFailure('getUserMedia', err)
      void reportVoiceMetrics({ mic_permission_failure: true }).catch(() => undefined)
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

    try {
      this.startLocalRecorder(stream)
      const credentials = await createRealtimeSession({
        assessment_id: this.assessmentId,
        topic_label: this.topicLabel,
      })
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
    if (this.ctx.state !== 'listening' && this.ctx.state !== 'live_draft') return
    this.session.stream?.getAudioTracks().forEach(t => {
      t.enabled = false
    })
    try {
      if (this.session.recorder?.state === 'recording') this.session.recorder.pause()
    } catch {
      // ignore
    }
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
    try {
      if (this.session.recorder?.state === 'paused') this.session.recorder.resume()
    } catch {
      // ignore
    }
    this.dispatch({ type: 'RESUME' })
  }

  async finish() {
    if (this.ctx.state !== 'listening' && this.ctx.state !== 'paused' && this.ctx.state !== 'live_draft') {
      return
    }
    const frozenBeforeCommit = displayAnswerText(this.store)
    this.dispatch({ type: 'FINISH' })
    if (frozenBeforeCommit && !this.ctx.liveDraftFrozen) {
      this.ctx = {
        ...this.ctx,
        liveDraftFrozen: frozenBeforeCommit,
        finalTranscript: frozenBeforeCommit,
      }
      this.callbacks.onContext(this.ctx)
    }

    // Keep the peer up after commit — with higher live_delay, deltas often arrive
    // only after input_audio_buffer.commit, well after 600ms.
    const liveDraft = await this.commitAndCollectLiveDraft(frozenBeforeCommit)
    this.ctx = {
      ...this.ctx,
      liveDraftFrozen: liveDraft,
      finalTranscript: liveDraft,
    }
    this.callbacks.onContext(this.ctx)

    const blob = await this.stopLocalRecorder()
    this.stopTimers()
    this.teardownPeerOnly()
    this.dispatch({ type: 'FINISHING_DONE' })
    this.dispatch({ type: 'REFINING' })

    const recordingMs = this.elapsedSeconds * 1000
    const connectionMs =
      this.session.connectedAt != null ? Date.now() - this.session.connectedAt : undefined
    const ttfd =
      this.session.firstDeltaAt && this.session.connectedAt
        ? this.session.firstDeltaAt - this.session.connectedAt
        : undefined

    const refineEnabled = this.session.credentials?.final_refinement_enabled !== false
    if (!refineEnabled || !blob || blob.size < 64) {
      if (liveDraft.trim()) {
        this.refinedFinal = liveDraft
        this.dispatch({ type: 'REFINED', text: liveDraft })
      } else {
        this.refinedFinal = ''
        this.dispatch({
          type: 'REFINE_FAILED',
          message:
            'No speech was transcribed. Check the microphone, record again, or type the answer.',
        })
      }
      void reportVoiceMetrics({
        connection_duration_ms: connectionMs,
        time_to_first_delta_ms: ttfd,
        recording_duration_ms: recordingMs,
        transcript_item_count: itemCount(this.store),
        empty_transcript: !liveDraft.trim(),
        device_label: this.session.deviceLabel,
        live_model: this.session.credentials?.live_transcription_model,
        final_model: this.session.credentials?.final_transcription_model,
      }).catch(() => undefined)
      this.releaseAudioBlob()
      this.teardownMedia()
      return
    }

    const refineStarted = Date.now()
    try {
      const result = await refineVoiceTranscript({
        blob,
        filename: recorderFilename(this.session.mimeType),
        assessmentId: this.assessmentId,
        liveTranscript: liveDraft,
      })
      this.refineDurationMs = result.duration_ms ?? Date.now() - refineStarted
      if (result.refined && result.transcript.trim()) {
        this.refinedFinal = result.transcript.trim()
        this.dispatch({ type: 'REFINED', text: this.refinedFinal })
        this.releaseAudioBlob()
      } else if (liveDraft.trim()) {
        this.refinedFinal = liveDraft
        this.dispatch({
          type: 'REFINE_FAILED',
          message:
            result.warning ||
            'Using the live transcript. The optional accuracy pass was unavailable — edit if needed, then submit.',
        })
      } else {
        this.refinedFinal = ''
        this.dispatch({
          type: 'REFINE_FAILED',
          message:
            result.warning ||
            'No speech was transcribed from the recording. Record again or type the answer.',
        })
      }
      void reportVoiceMetrics({
        connection_duration_ms: connectionMs,
        time_to_first_delta_ms: ttfd,
        recording_duration_ms: recordingMs,
        refine_duration_ms: this.refineDurationMs ?? undefined,
        transcript_item_count: itemCount(this.store),
        empty_transcript: !this.refinedFinal.trim(),
        refinement_failed: !result.refined,
        device_label: this.session.deviceLabel,
        live_model: this.session.credentials?.live_transcription_model,
        final_model: result.model,
      }).catch(() => undefined)
    } catch (err) {
      reportClientFailure('refine', err)
      if (liveDraft.trim()) {
        this.refinedFinal = liveDraft
        this.dispatch({
          type: 'REFINE_FAILED',
          message:
            'Using the live transcript. The optional accuracy pass was unavailable — edit if needed, then submit.',
        })
      } else {
        this.refinedFinal = ''
        this.dispatch({
          type: 'REFINE_FAILED',
          message: 'No speech was transcribed. Record again or type the answer.',
        })
      }
      void reportVoiceMetrics({
        refinement_failed: true,
        recording_duration_ms: recordingMs,
        transcript_item_count: itemCount(this.store),
        empty_transcript: !liveDraft.trim(),
        device_label: this.session.deviceLabel,
      }).catch(() => undefined)
    } finally {
      this.teardownMedia()
    }
  }

  /**
   * Commit the Realtime audio buffer and wait for delayed transcript events.
   * Higher live_delay values need a longer wait before the peer is closed.
   */
  private async commitAndCollectLiveDraft(frozenBeforeCommit: string): Promise<string> {
    const before = (displayAnswerText(this.store) || frozenBeforeCommit || '').trim()
    try {
      if (this.session.dc && this.session.dc.readyState === 'open') {
        this.session.dc.send(JSON.stringify({ type: 'input_audio_buffer.commit' }))
      }
    } catch {
      // ignore
    }

    const timeoutMs = postCommitWaitMs(this.session.credentials?.live_delay)
    const started = Date.now()
    while (Date.now() - started < timeoutMs) {
      const current = (displayAnswerText(this.store) || '').trim()
      // Prefer a completed/longer draft after commit; settle briefly once text appears.
      if (current && (current !== before || current.length > before.length + 8)) {
        await new Promise(r => setTimeout(r, 400))
        return displayAnswerText(this.store) || current
      }
      if (current && Date.now() - started > Math.min(timeoutMs, 2000) && before && current === before) {
        // Already had a live draft and nothing new arrived — keep it.
        return current
      }
      await new Promise(r => setTimeout(r, 150))
    }
    return displayAnswerText(this.store) || frozenBeforeCommit || ''
  }

  async retryRefine() {
    if (this.ctx.state !== 'refinement_failed') return
    const liveDraft = this.ctx.liveDraftFrozen || this.ctx.finalTranscript
    if (!this.session.audioBlob) {
      this.dispatch({
        type: 'REFINE_FAILED',
        message: 'Audio is no longer available. Edit the live draft or record again.',
      })
      return
    }
    this.dispatch({ type: 'REFINING' })
    try {
      const result = await refineVoiceTranscript({
        blob: this.session.audioBlob,
        assessmentId: this.assessmentId,
        liveTranscript: liveDraft,
      })
      if (result.refined && result.transcript.trim()) {
        this.refinedFinal = result.transcript.trim()
        this.dispatch({ type: 'REFINED', text: this.refinedFinal })
        this.releaseAudioBlob()
      } else {
        this.dispatch({
          type: 'REFINE_FAILED',
          message:
            result.warning ||
            'Using the live transcript. The optional accuracy pass was unavailable — edit if needed, then submit.',
        })
      }
    } catch {
      this.dispatch({
        type: 'REFINE_FAILED',
        message:
          'Using the live transcript. The optional accuracy pass was unavailable — edit if needed, then submit.',
      })
    }
  }

  discard() {
    this.stopTimers()
    void this.stopLocalRecorder().catch(() => undefined)
    this.teardownMedia()
    this.releaseAudioBlob()
    this.typedNoteBuffer = ''
    this.elapsedSeconds = 0
    this.store = createTranscriptStore()
    this.refinedFinal = ''
    this.dispatch({ type: 'DISCARD' })
  }

  appendTypedNote(note: string) {
    const cleaned = note.trim()
    if (!cleaned) return
    this.typedNoteBuffer = [this.typedNoteBuffer, cleaned].filter(Boolean).join('\n')
    if (
      this.ctx.state === 'ready_to_edit' ||
      this.ctx.state === 'refinement_failed' ||
      this.ctx.state === 'fallback_text' ||
      this.ctx.state === 'idle'
    ) {
      const merged = [this.ctx.finalTranscript, cleaned].filter(Boolean).join('\n\n')
      this.ctx = { ...this.ctx, finalTranscript: merged }
      this.callbacks.onContext(this.ctx)
    }
  }

  async recover() {
    if (this.ctx.state !== 'reconnecting') return
    void reportVoiceMetrics({ webrtc_reconnect: true }).catch(() => undefined)
    if (this.ctx.reconnectAttempts > 2) {
      this.dispatch({ type: 'RECONNECT_FAILED' })
      this.teardownPeerOnly()
      return
    }
    try {
      this.teardownPeerOnly()
      const stream = this.session.stream || (await requestMicrophoneStream(this.preferredDeviceId))
      this.session.stream = stream
      this.dispatch({ type: 'PERMISSION_GRANTED' })
      const credentials = await createRealtimeSession({
        assessment_id: this.assessmentId,
        topic_label: this.topicLabel,
      })
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
      this.teardownPeerOnly()
    }
  }

  private startLocalRecorder(stream: MediaStream) {
    if (typeof MediaRecorder === 'undefined') return
    const mimeType = preferredRecorderMime()
    try {
      // Clone so WebRTC teardown cannot corrupt the accuracy-pass recording.
      const recordStream = stream.clone()
      const recorder = mimeType
        ? new MediaRecorder(recordStream, { mimeType })
        : new MediaRecorder(recordStream)
      this.session.mimeType = recorder.mimeType || mimeType || 'audio/webm'
      this.session.chunks = []
      recorder.ondataavailable = event => {
        if (event.data && event.data.size > 0) this.session.chunks.push(event.data)
      }
      recorder.start(250)
      this.session.recorder = recorder
      recorder.addEventListener('stop', () => {
        for (const track of recordStream.getTracks()) track.stop()
      })
    } catch (err) {
      reportClientFailure('media_recorder', err)
      this.session.recorder = null
    }
  }

  private stopLocalRecorder(): Promise<Blob | null> {
    const recorder = this.session.recorder
    if (!recorder) {
      if (this.session.chunks.length) {
        const blob = new Blob(this.session.chunks, { type: this.session.mimeType || 'audio/webm' })
        this.session.audioBlob = blob
        return Promise.resolve(blob)
      }
      return Promise.resolve(null)
    }
    return new Promise(resolve => {
      const finish = () => {
        const blob = new Blob(this.session.chunks, { type: this.session.mimeType || 'audio/webm' })
        this.session.audioBlob = blob
        this.session.recorder = null
        resolve(blob.size > 0 ? blob : null)
      }
      if (recorder.state === 'inactive') {
        finish()
        return
      }
      recorder.onstop = finish
      try {
        recorder.stop()
      } catch {
        finish()
      }
    })
  }

  private releaseAudioBlob() {
    this.session.audioBlob = null
    this.session.chunks = []
  }

  private async startMock(stream: MediaStream) {
    this.dispatch({ type: 'CONNECTED' })
    this.session.connectedAt = Date.now()
    let idx = 0
    this.session.mockTimer = setInterval(() => {
      if (this.ctx.state !== 'listening' && this.ctx.state !== 'live_draft' && this.ctx.state !== 'paused') {
        return
      }
      idx = Math.min(idx + 12, MOCK_SCRIPT.length)
      if (!this.session.firstDeltaAt) this.session.firstDeltaAt = Date.now()
      this.store = applyDelta(this.store, 'mock-item-1', MOCK_SCRIPT.slice(Math.max(0, idx - 12), idx))
      // Mock accumulates via slice replace for simplicity
      this.store = createTranscriptStore()
      this.store = applyDelta(this.store, 'mock-item-1', MOCK_SCRIPT.slice(0, idx))
      this.emitReconciled()
      if (idx >= MOCK_SCRIPT.length && this.session.mockTimer) {
        clearInterval(this.session.mockTimer)
        this.session.mockTimer = null
        this.store = applyCompleted(this.store, 'mock-item-1', MOCK_SCRIPT)
        this.emitReconciled(true)
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
    dc.addEventListener('open', () => {
      this.applyLiveTranscriptionContext(credentials, dc)
    })
    dc.addEventListener('message', event => {
      this.handleServerEvent(String(event.data))
    })
    pc.addEventListener('connectionstatechange', () => {
      if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
        if (this.ctx.state === 'finishing' || this.ctx.state === 'refining' || this.ctx.state === 'ready_to_edit') {
          return
        }
        this.dispatch({ type: 'DISCONNECT' })
        void this.recover()
      }
    })

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
          // plain text
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
    this.session.connectedAt = Date.now()
    this.dispatch({ type: 'CONNECTED' })
    // If the data channel opened before we attached the listener, apply now.
    if (dc.readyState === 'open') {
      this.applyLiveTranscriptionContext(credentials, dc)
    }
  }

  /**
   * Apply assessment prompt/keywords after connect. Only gpt-live-transcribe
   * supports these fields; other models reject prompt on session mint/update.
   */
  private applyLiveTranscriptionContext(credentials: RealtimeSessionCredentials, dc: RTCDataChannel) {
    const model = credentials.live_transcription_model || credentials.transcription_model
    if (model !== 'gpt-live-transcribe') return
    if (dc.readyState !== 'open') return
    const ctx = credentials.transcription_context
    if (!ctx?.prompt && !ctx?.keywords?.length) return

    const transcription: Record<string, unknown> = {
      model: 'gpt-live-transcribe',
      languages: ctx.languages?.length ? ctx.languages : credentials.languages?.length ? credentials.languages : ['en'],
      delay: credentials.live_delay || 'medium',
    }
    if (ctx.prompt) transcription.prompt = ctx.prompt.slice(0, 900)
    if (ctx.keywords?.length) transcription.keywords = ctx.keywords.slice(0, 40)

    try {
      dc.send(
        JSON.stringify({
          type: 'session.update',
          session: {
            type: 'transcription',
            audio: {
              input: {
                transcription,
                turn_detection: null,
              },
            },
          },
        }),
      )
    } catch (err) {
      reportClientFailure('session_update_context', err)
    }
  }

  private handleServerEvent(raw: string) {
    try {
      const event = JSON.parse(raw) as {
        type?: string
        delta?: string
        transcript?: string
        item_id?: string
        itemId?: string
        error?: { message?: string; code?: string }
      }
      const type = event.type || ''
      const itemId = event.item_id || event.itemId || ''

      if (type.includes('transcription.delta') && typeof event.delta === 'string') {
        if (!this.session.firstDeltaAt) this.session.firstDeltaAt = Date.now()
        const id = itemId || 'pending'
        this.store = applyDelta(this.store, id, event.delta)
        this.emitReconciled()
      }
      if (type.includes('transcription.completed') && typeof event.transcript === 'string') {
        const id = itemId || `completed-${this.store.nextOrder}`
        this.store = applyCompleted(this.store, id, event.transcript)
        this.emitReconciled(true)
      }
      if (type === 'error') {
        const message = event.error?.message || 'Realtime transcription error'
        reportClientFailure('realtime_event', new Error(message))
        // Context / delay hints are best-effort; keep recording.
        if (/prompt.*not supported|keywords.*not supported|delay.*not supported/i.test(message)) {
          return
        }
        const hasDraft = Boolean(liveDraftText(this.store))
        const stillCapturing =
          this.ctx.state === 'listening' ||
          this.ctx.state === 'live_draft' ||
          this.ctx.state === 'paused' ||
          this.ctx.state === 'connecting' ||
          this.ctx.state === 'finishing'
        // With higher live_delay, draft text may not exist yet — do not abandon the take.
        if (stillCapturing && !hasDraft) {
          return
        }
        this.dispatch({ type: 'ERROR', message })
        if (!hasDraft) {
          this.dispatch({ type: 'FALLBACK_TEXT' })
          this.teardownMedia()
        }
      }
    } catch {
      // ignore malformed events
    }
  }

  private emitReconciled(isCompleted = false) {
    const text = displayAnswerText(this.store)
    if (isCompleted) {
      this.dispatch({ type: 'FINAL_SEGMENT', text })
    } else {
      this.dispatch({ type: 'PARTIAL', text })
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

  private teardownPeerOnly() {
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
    this.session.pc = null
    this.session.dc = null
  }

  private teardownMedia(clearStream = true) {
    this.teardownPeerOnly()
    try {
      if (this.session.recorder && this.session.recorder.state !== 'inactive') {
        this.session.recorder.stop()
      }
    } catch {
      // ignore
    }
    this.session.recorder = null
    if (clearStream) {
      this.session.stream?.getTracks().forEach(t => t.stop())
      this.session.stream = null
    }
  }
}
