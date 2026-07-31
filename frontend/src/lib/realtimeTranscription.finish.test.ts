import { describe, expect, it } from 'vitest'
import { postCommitWaitMs } from './realtimeTranscription'

describe('post-commit wait scales with live delay', () => {
  it('waits longer for high/xhigh than for low', () => {
    expect(postCommitWaitMs('low')).toBeLessThan(postCommitWaitMs('high'))
    expect(postCommitWaitMs('high')).toBeLessThan(postCommitWaitMs('xhigh'))
    expect(postCommitWaitMs('high')).toBeGreaterThanOrEqual(8000)
  })
})
