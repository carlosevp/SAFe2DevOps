import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('remote contributor mobile layout', () => {
  it('keeps a single-column responsive shell suitable for phones', () => {
    const source = readFileSync(resolve(__dirname, '../screens/RemoteContributor.tsx'), 'utf8')
    expect(source).toContain('max-w-lg')
    expect(source).toContain('px-4')
    expect(source).toContain('sm:p-7')
    expect(source).toContain('min-h-screen')
    // No multi-column workshop chrome on the remote path.
    expect(source).not.toContain('grid-cols-12')
  })
})

describe('remote invite deep link', () => {
  it('App boots into remote contributor when invite query is present', () => {
    const source = readFileSync(resolve(__dirname, '../App.tsx'), 'utf8')
    expect(source).toContain("params.get('invite')")
    expect(source).toContain('remote-contributor')
    expect(source).toContain('inviteToken')
  })
})
