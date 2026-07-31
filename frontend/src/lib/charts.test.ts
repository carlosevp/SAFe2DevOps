import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('chart accessibility contract', () => {
  it('provides screen-reader summaries and responsive/print-friendly markup', () => {
    const source = readFileSync(resolve(__dirname, '../components/Charts.tsx'), 'utf8')
    expect(source).toContain('aria-label')
    expect(source).toContain('sr-only')
    expect(source).toContain('role="img"')
    expect(source).toContain('print:')
    expect(source).toContain('sm:grid-cols-4')
  })
})
