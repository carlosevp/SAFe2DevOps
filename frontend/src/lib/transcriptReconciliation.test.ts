import { describe, expect, it } from 'vitest'
import {
  applyCompleted,
  applyDelta,
  createTranscriptStore,
  displayAnswerText,
  liveDraftText,
} from './transcriptReconciliation'

describe('transcript reconciliation by item_id', () => {
  it('accumulates deltas per item and replaces with completed (no double text)', () => {
    let store = createTranscriptStore()
    store = applyDelta(store, 'item-a', 'Hello ')
    store = applyDelta(store, 'item-a', 'team')
    expect(liveDraftText(store)).toBe('Hello team')
    store = applyCompleted(store, 'item-a', 'Hello team from the room.')
    expect(liveDraftText(store)).toBe('Hello team from the room.')
    expect(liveDraftText(store)).not.toContain('Hello teamHello')
  })

  it('handles out-of-order completion events without scrambling first-seen order', () => {
    let store = createTranscriptStore()
    store = applyDelta(store, 'item-1', 'First draft')
    store = applyDelta(store, 'item-2', 'Second draft')
    // item-2 completes before item-1
    store = applyCompleted(store, 'item-2', 'Second final.')
    store = applyCompleted(store, 'item-1', 'First final.')
    expect(displayAnswerText(store)).toBe('First final.\n\nSecond final.')
  })

  it('ignores deltas after an item is completed', () => {
    let store = createTranscriptStore()
    store = applyCompleted(store, 'item-x', 'Done.')
    store = applyDelta(store, 'item-x', ' stray')
    expect(liveDraftText(store)).toBe('Done.')
  })

  it('preserves finalized previous text across items', () => {
    let store = createTranscriptStore('Prior note')
    store = applyDelta(store, 'n1', 'New speech')
    expect(displayAnswerText(store)).toContain('Prior note')
    expect(displayAnswerText(store)).toContain('New speech')
  })
})
