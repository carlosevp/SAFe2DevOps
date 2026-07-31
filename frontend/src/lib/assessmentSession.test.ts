import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearStoredAssessment,
  formatAssessmentNotFound,
  readStoredAssessment,
  writeStoredAssessment,
} from './assessmentSession'

describe('assessmentSession storage', () => {
  beforeEach(() => {
    clearStoredAssessment()
  })

  it('round-trips assessment id and name', () => {
    writeStoredAssessment('abc-123-def', 'Payments Team')
    expect(readStoredAssessment()).toEqual({ id: 'abc-123-def', name: 'Payments Team' })
  })

  it('returns null for missing or invalid storage', () => {
    expect(readStoredAssessment()).toBeNull()
    sessionStorage.setItem('safedevops.activeAssessment', '{bad')
    expect(readStoredAssessment()).toBeNull()
  })

  it('formats not-found guidance', () => {
    const message = formatAssessmentNotFound('12345678-aaaa-bbbb-cccc-dddddddddddd')
    expect(message).toMatch(/Assessment not found/)
    expect(message).toMatch(/12345678/)
    expect(message).toMatch(/DATA_DIR/)
  })
})
