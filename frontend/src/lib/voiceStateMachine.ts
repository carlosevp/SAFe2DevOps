export type MicState =
  | 'idle'
  | 'requesting_permission'
  | 'ready'
  | 'connecting'
  | 'listening'
  | 'paused'
  | 'live_draft'
  | 'finishing'
  | 'refining'
  | 'ready_to_edit'
  | 'refinement_failed'
  | 'reconnecting'
  | 'disconnected'
  | 'permission_denied'
  | 'error'
  | 'fallback_text'

export type MicEvent =
  | { type: 'START' }
  | { type: 'PERMISSION_GRANTED' }
  | { type: 'PERMISSION_DENIED'; message?: string }
  | { type: 'READY' }
  | { type: 'CONNECTED' }
  | { type: 'PARTIAL'; text: string }
  | { type: 'FINAL_SEGMENT'; text: string }
  | { type: 'PAUSE' }
  | { type: 'RESUME' }
  | { type: 'FINISH' }
  | { type: 'FINISHING_DONE' }
  | { type: 'REFINING' }
  | { type: 'REFINED'; text: string }
  | { type: 'REFINE_FAILED'; message?: string }
  | { type: 'DISCARD' }
  | { type: 'DISCONNECT' }
  | { type: 'SESSION_EXPIRED' }
  | { type: 'RECONNECTED' }
  | { type: 'RECONNECT_FAILED' }
  | { type: 'FALLBACK_TEXT' }
  | { type: 'ERROR'; message: string }

export type MicContext = {
  state: MicState
  /** Combined display text for live draft (reconciled externally, mirrored here). */
  partialTranscript: string
  finalTranscript: string
  liveDraftFrozen: string
  refinedTranscript: string
  errorMessage: string | null
  statusLabel: string
  reconnectAttempts: number
  refinementWarning: string | null
}

const LABELS: Record<MicState, string> = {
  idle: 'Ready',
  requesting_permission: 'Connecting microphone',
  ready: 'Ready',
  connecting: 'Connecting microphone',
  listening: 'Listening',
  paused: 'Paused',
  live_draft: 'Live draft',
  finishing: 'Finishing recording',
  refining: 'Refining transcript',
  ready_to_edit: 'Transcript ready',
  refinement_failed: 'Refinement failed — live draft retained',
  reconnecting: 'Disconnected',
  disconnected: 'Disconnected',
  permission_denied: 'Permission denied',
  error: 'Disconnected',
  fallback_text: 'Ready',
}

export function createMicContext(): MicContext {
  return {
    state: 'idle',
    partialTranscript: '',
    finalTranscript: '',
    liveDraftFrozen: '',
    refinedTranscript: '',
    errorMessage: null,
    statusLabel: LABELS.idle,
    reconnectAttempts: 0,
    refinementWarning: null,
  }
}

function withLabel(ctx: MicContext): MicContext {
  return { ...ctx, statusLabel: LABELS[ctx.state] || ctx.state }
}

export function reduceMic(ctx: MicContext, event: MicEvent): MicContext {
  switch (event.type) {
    case 'START':
      if (
        ctx.state === 'idle' ||
        ctx.state === 'error' ||
        ctx.state === 'fallback_text' ||
        ctx.state === 'ready_to_edit' ||
        ctx.state === 'refinement_failed' ||
        ctx.state === 'permission_denied' ||
        ctx.state === 'disconnected'
      ) {
        return withLabel({
          ...ctx,
          state: 'requesting_permission',
          errorMessage: null,
          partialTranscript: '',
          liveDraftFrozen: '',
          refinedTranscript: '',
          refinementWarning: null,
          reconnectAttempts: 0,
        })
      }
      return ctx
    case 'PERMISSION_GRANTED':
      if (ctx.state === 'requesting_permission' || ctx.state === 'reconnecting') {
        return withLabel({ ...ctx, state: 'connecting', errorMessage: null })
      }
      return ctx
    case 'PERMISSION_DENIED':
      return withLabel({
        ...ctx,
        state: 'permission_denied',
        errorMessage: event.message || 'Microphone permission denied. Continue with typed response.',
      })
    case 'READY':
      if (ctx.state === 'connecting') {
        return withLabel({ ...ctx, state: 'ready', errorMessage: null })
      }
      return ctx
    case 'CONNECTED':
      if (ctx.state === 'connecting' || ctx.state === 'reconnecting' || ctx.state === 'ready') {
        return withLabel({ ...ctx, state: 'listening', errorMessage: null, reconnectAttempts: 0 })
      }
      return ctx
    case 'PARTIAL':
      if (ctx.state === 'listening' || ctx.state === 'paused' || ctx.state === 'live_draft') {
        return withLabel({
          ...ctx,
          state: ctx.state === 'paused' ? 'paused' : 'live_draft',
          partialTranscript: event.text,
        })
      }
      return ctx
    case 'FINAL_SEGMENT': {
      if (
        ctx.state !== 'listening' &&
        ctx.state !== 'paused' &&
        ctx.state !== 'live_draft' &&
        ctx.state !== 'finishing'
      ) {
        return ctx
      }
      // Controller owns item_id merge; event.text is the full reconciled display.
      return withLabel({
        ...ctx,
        state: ctx.state === 'finishing' ? 'finishing' : ctx.state === 'paused' ? 'paused' : 'live_draft',
        partialTranscript: event.text,
        finalTranscript: event.text,
      })
    }
    case 'PAUSE':
      if (ctx.state === 'listening' || ctx.state === 'live_draft') {
        return withLabel({ ...ctx, state: 'paused' })
      }
      return ctx
    case 'RESUME':
      if (ctx.state === 'paused') {
        return withLabel({ ...ctx, state: ctx.partialTranscript ? 'live_draft' : 'listening' })
      }
      return ctx
    case 'FINISH': {
      if (ctx.state === 'listening' || ctx.state === 'paused' || ctx.state === 'live_draft') {
        const frozen = [ctx.finalTranscript, ctx.partialTranscript].filter(Boolean).join('\n\n').trim()
          || ctx.partialTranscript
          || ctx.finalTranscript
        return withLabel({
          ...ctx,
          state: 'finishing',
          liveDraftFrozen: frozen,
          finalTranscript: frozen,
          partialTranscript: '',
        })
      }
      return ctx
    }
    case 'FINISHING_DONE':
      if (ctx.state === 'finishing') {
        return withLabel({ ...ctx, state: 'refining' })
      }
      return ctx
    case 'REFINING':
      if (ctx.state === 'finishing' || ctx.state === 'refining' || ctx.state === 'refinement_failed') {
        return withLabel({ ...ctx, state: 'refining', refinementWarning: null })
      }
      return ctx
    case 'REFINED':
      if (ctx.state === 'refining' || ctx.state === 'finishing') {
        return withLabel({
          ...ctx,
          state: 'ready_to_edit',
          refinedTranscript: event.text,
          finalTranscript: event.text,
          refinementWarning: null,
        })
      }
      return ctx
    case 'REFINE_FAILED':
      if (ctx.state === 'refining' || ctx.state === 'finishing') {
        const fallback = ctx.liveDraftFrozen || ctx.finalTranscript
        return withLabel({
          ...ctx,
          state: 'refinement_failed',
          finalTranscript: fallback,
          refinementWarning:
            event.message || 'Refinement failed — live draft retained. You can edit or retry.',
        })
      }
      return ctx
    case 'DISCARD':
      return createMicContext()
    case 'DISCONNECT':
    case 'SESSION_EXPIRED':
      if (
        ctx.state === 'listening' ||
        ctx.state === 'paused' ||
        ctx.state === 'live_draft' ||
        ctx.state === 'connecting'
      ) {
        return withLabel({
          ...ctx,
          state: 'reconnecting',
          reconnectAttempts: ctx.reconnectAttempts + 1,
          errorMessage:
            event.type === 'SESSION_EXPIRED'
              ? 'Voice session expired. Reconnecting…'
              : 'Connection lost. Reconnecting…',
        })
      }
      return ctx
    case 'RECONNECTED':
      if (ctx.state === 'reconnecting') {
        return withLabel({ ...ctx, state: 'listening', errorMessage: null })
      }
      return ctx
    case 'RECONNECT_FAILED':
      return withLabel({
        ...ctx,
        state: 'fallback_text',
        errorMessage:
          'Could not restore voice connection. Your transcript was preserved — continue by typing.',
      })
    case 'FALLBACK_TEXT':
      return withLabel({
        ...ctx,
        state: 'fallback_text',
        errorMessage: ctx.errorMessage || 'Using typed response fallback.',
      })
    case 'ERROR':
      return withLabel({ ...ctx, state: 'error', errorMessage: event.message })
    default:
      return ctx
  }
}

export function displayTranscript(ctx: MicContext): string {
  if (ctx.state === 'ready_to_edit' || ctx.state === 'refinement_failed') {
    return ctx.finalTranscript
  }
  if (ctx.state === 'finishing' || ctx.state === 'refining') {
    return ctx.liveDraftFrozen || ctx.finalTranscript
  }
  if (ctx.partialTranscript) {
    return [ctx.finalTranscript && ctx.finalTranscript !== ctx.partialTranscript ? '' : '', ctx.partialTranscript]
      .filter(Boolean)
      .join('')
      || ctx.partialTranscript
  }
  return ctx.finalTranscript
}

export function isLiveSpeakingState(state: MicState): boolean {
  return state === 'listening' || state === 'paused' || state === 'live_draft'
}

export function isEditableAnswerState(state: MicState): boolean {
  return (
    state === 'ready_to_edit' ||
    state === 'refinement_failed' ||
    state === 'fallback_text' ||
    state === 'error' ||
    state === 'permission_denied' ||
    state === 'idle'
  )
}
