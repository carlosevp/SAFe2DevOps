export type MicState =
  | 'idle'
  | 'requesting_permission'
  | 'connecting'
  | 'listening'
  | 'paused'
  | 'reconnecting'
  | 'finalizing'
  | 'ready_to_edit'
  | 'error'
  | 'fallback_text'

export type MicEvent =
  | { type: 'START' }
  | { type: 'PERMISSION_GRANTED' }
  | { type: 'PERMISSION_DENIED'; message?: string }
  | { type: 'CONNECTED' }
  | { type: 'PARTIAL'; text: string }
  | { type: 'FINAL_SEGMENT'; text: string }
  | { type: 'PAUSE' }
  | { type: 'RESUME' }
  | { type: 'FINISH' }
  | { type: 'DISCARD' }
  | { type: 'DISCONNECT' }
  | { type: 'SESSION_EXPIRED' }
  | { type: 'RECONNECTED' }
  | { type: 'RECONNECT_FAILED' }
  | { type: 'FALLBACK_TEXT' }
  | { type: 'ERROR'; message: string }

export type MicContext = {
  state: MicState
  partialTranscript: string
  finalTranscript: string
  errorMessage: string | null
  reconnectAttempts: number
}

export function createMicContext(): MicContext {
  return {
    state: 'idle',
    partialTranscript: '',
    finalTranscript: '',
    errorMessage: null,
    reconnectAttempts: 0,
  }
}

export function reduceMic(ctx: MicContext, event: MicEvent): MicContext {
  switch (event.type) {
    case 'START':
      if (ctx.state === 'idle' || ctx.state === 'error' || ctx.state === 'fallback_text' || ctx.state === 'ready_to_edit') {
        return {
          ...ctx,
          state: 'requesting_permission',
          errorMessage: null,
          partialTranscript: '',
          // Preserve existing finalized text across restart only on explicit discard.
          reconnectAttempts: 0,
        }
      }
      return ctx
    case 'PERMISSION_GRANTED':
      if (ctx.state === 'requesting_permission' || ctx.state === 'reconnecting') {
        return { ...ctx, state: 'connecting', errorMessage: null }
      }
      return ctx
    case 'PERMISSION_DENIED':
      return {
        ...ctx,
        state: 'fallback_text',
        errorMessage: event.message || 'Microphone permission denied. Continue with typed response.',
      }
    case 'CONNECTED':
      if (ctx.state === 'connecting' || ctx.state === 'reconnecting') {
        return { ...ctx, state: 'listening', errorMessage: null, reconnectAttempts: 0 }
      }
      return ctx
    case 'PARTIAL':
      if (ctx.state === 'listening' || ctx.state === 'paused') {
        return { ...ctx, partialTranscript: event.text }
      }
      return ctx
    case 'FINAL_SEGMENT': {
      if (ctx.state !== 'listening' && ctx.state !== 'paused' && ctx.state !== 'finalizing') return ctx
      const merged = [ctx.finalTranscript, event.text].filter(Boolean).join('\n\n').trim()
      return { ...ctx, finalTranscript: merged, partialTranscript: '' }
    }
    case 'PAUSE':
      if (ctx.state === 'listening') return { ...ctx, state: 'paused' }
      return ctx
    case 'RESUME':
      if (ctx.state === 'paused') return { ...ctx, state: 'listening' }
      return ctx
    case 'FINISH':
      if (ctx.state === 'listening' || ctx.state === 'paused') {
        const merged = [ctx.finalTranscript, ctx.partialTranscript].filter(Boolean).join('\n\n').trim()
        return {
          ...ctx,
          state: 'ready_to_edit',
          finalTranscript: merged,
          partialTranscript: '',
        }
      }
      return ctx
    case 'DISCARD':
      return createMicContext()
    case 'DISCONNECT':
    case 'SESSION_EXPIRED':
      if (ctx.state === 'listening' || ctx.state === 'paused' || ctx.state === 'connecting') {
        // Preserve transcript text across disconnect.
        return {
          ...ctx,
          state: 'reconnecting',
          reconnectAttempts: ctx.reconnectAttempts + 1,
          errorMessage: event.type === 'SESSION_EXPIRED' ? 'Voice session expired. Reconnecting…' : 'Connection lost. Reconnecting…',
        }
      }
      return ctx
    case 'RECONNECTED':
      if (ctx.state === 'reconnecting') {
        return { ...ctx, state: 'listening', errorMessage: null }
      }
      return ctx
    case 'RECONNECT_FAILED':
      return {
        ...ctx,
        state: 'fallback_text',
        errorMessage: 'Could not restore voice connection. Your transcript was preserved — continue by typing.',
      }
    case 'FALLBACK_TEXT':
      return {
        ...ctx,
        state: 'fallback_text',
        errorMessage: ctx.errorMessage || 'Using typed response fallback.',
      }
    case 'ERROR':
      return { ...ctx, state: 'error', errorMessage: event.message }
    default:
      return ctx
  }
}

export function displayTranscript(ctx: MicContext): string {
  if (ctx.partialTranscript) {
    return [ctx.finalTranscript, ctx.partialTranscript].filter(Boolean).join('\n\n')
  }
  return ctx.finalTranscript
}
