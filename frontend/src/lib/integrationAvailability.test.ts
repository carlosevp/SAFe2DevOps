import { describe, expect, it } from 'vitest'
import {
  availabilityLabel,
  isProviderSelectable,
  permissionHint,
  shouldShowRetry,
} from './integrationAvailability'
import type { ProviderSetupState } from './api'

function state(partial: Partial<ProviderSetupState>): ProviderSetupState {
  return {
    availability: 'ready',
    capabilities: {},
    catalog_stale: false,
    catalog_count: 1,
    selectable: true,
    ...partial,
  }
}

describe('integrationAvailability', () => {
  it('does not treat configured integrations as disabled', () => {
    expect(isProviderSelectable(state({ availability: 'ready' }))).toBe(true)
    expect(isProviderSelectable(state({ availability: 'ready_cached', catalog_stale: true }))).toBe(true)
    expect(
      isProviderSelectable(
        state({
          availability: 'refresh_failed_cached_available',
          catalog_stale: true,
          selectable: true,
          catalog_count: 3,
        }),
      ),
    ).toBe(true)
    expect(availabilityLabel('administratively_disabled')).toBe('Administratively disabled')
    expect(availabilityLabel('ready')).not.toBe('Disabled')
  })

  it('keeps stale catalog selectable and shows retry', () => {
    const stale = state({
      availability: 'refresh_failed_cached_available',
      catalog_stale: true,
      catalog_count: 2,
      selectable: true,
    })
    expect(isProviderSelectable(stale)).toBe(true)
    expect(shouldShowRetry(stale.availability)).toBe(true)
  })

  it('shows Browse Projects permission message for zero projects', () => {
    const hint = permissionHint('credentials_accepted_no_projects')
    expect(hint).toContain('Browse Projects')
  })

  it('disables only when not configured, admin disabled, or undecryptable', () => {
    expect(isProviderSelectable(state({ availability: 'not_configured', selectable: false, catalog_count: 0 }))).toBe(
      false,
    )
    expect(
      isProviderSelectable(
        state({ availability: 'administratively_disabled', selectable: false, catalog_count: 5 }),
      ),
    ).toBe(false)
    expect(
      isProviderSelectable(
        state({ availability: 'credentials_undecryptable', selectable: false, catalog_count: 0 }),
      ),
    ).toBe(false)
  })
})
