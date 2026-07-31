import { describe, expect, it } from 'vitest'
import { createMicContext, displayTranscript, reduceMic } from './voiceStateMachine'

describe('voice state machine', () => {
  it('moves through start → permission → connect → listening', () => {
    let ctx = createMicContext()
    ctx = reduceMic(ctx, { type: 'START' })
    expect(ctx.state).toBe('requesting_permission')
    ctx = reduceMic(ctx, { type: 'PERMISSION_GRANTED' })
    expect(ctx.state).toBe('connecting')
    ctx = reduceMic(ctx, { type: 'CONNECTED' })
    expect(ctx.state).toBe('listening')
  })

  it('handles partial and final transcript editing path', () => {
    let ctx = createMicContext()
    ctx = reduceMic(ctx, { type: 'START' })
    ctx = reduceMic(ctx, { type: 'PERMISSION_GRANTED' })
    ctx = reduceMic(ctx, { type: 'CONNECTED' })
    ctx = reduceMic(ctx, { type: 'PARTIAL', text: 'Hello team' })
    expect(displayTranscript(ctx)).toContain('Hello team')
    ctx = reduceMic(ctx, { type: 'FINAL_SEGMENT', text: 'Hello team from the room.' })
    ctx = reduceMic(ctx, { type: 'FINISH' })
    expect(ctx.state).toBe('ready_to_edit')
    expect(ctx.finalTranscript).toContain('Hello team from the room.')
    expect(ctx.partialTranscript).toBe('')
  })

  it('supports pause/resume and discard', () => {
    let ctx = createMicContext()
    ctx = reduceMic(ctx, { type: 'START' })
    ctx = reduceMic(ctx, { type: 'PERMISSION_GRANTED' })
    ctx = reduceMic(ctx, { type: 'CONNECTED' })
    ctx = reduceMic(ctx, { type: 'PAUSE' })
    expect(ctx.state).toBe('paused')
    ctx = reduceMic(ctx, { type: 'RESUME' })
    expect(ctx.state).toBe('listening')
    ctx = reduceMic(ctx, { type: 'DISCARD' })
    expect(ctx.state).toBe('idle')
    expect(ctx.finalTranscript).toBe('')
  })

  it('preserves transcript on disconnect and falls back after failed reconnect', () => {
    let ctx = createMicContext()
    ctx = reduceMic(ctx, { type: 'START' })
    ctx = reduceMic(ctx, { type: 'PERMISSION_GRANTED' })
    ctx = reduceMic(ctx, { type: 'CONNECTED' })
    ctx = reduceMic(ctx, { type: 'FINAL_SEGMENT', text: 'Preserved answer' })
    ctx = reduceMic(ctx, { type: 'DISCONNECT' })
    expect(ctx.state).toBe('reconnecting')
    expect(ctx.finalTranscript).toContain('Preserved answer')
    ctx = reduceMic(ctx, { type: 'RECONNECT_FAILED' })
    expect(ctx.state).toBe('fallback_text')
    expect(ctx.finalTranscript).toContain('Preserved answer')
  })

  it('falls back on permission denial', () => {
    let ctx = createMicContext()
    ctx = reduceMic(ctx, { type: 'START' })
    ctx = reduceMic(ctx, { type: 'PERMISSION_DENIED', message: 'Denied' })
    expect(ctx.state).toBe('fallback_text')
    expect(ctx.errorMessage).toMatch(/Denied|permission/i)
  })
})
