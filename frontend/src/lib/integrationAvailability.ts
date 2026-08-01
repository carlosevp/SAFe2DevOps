import type { ProviderAvailability, ProviderSetupState } from './api'

export const AVAILABILITY_LABELS: Record<string, string> = {
  not_configured: 'Not configured',
  configured_loading_catalog: 'Configured — loading catalog',
  ready: 'Ready',
  ready_cached: 'Ready using cached catalog',
  refresh_failed_cached_available: 'Refresh failed — cached catalog available',
  credentials_accepted_no_projects: 'Credentials accepted but no projects visible',
  additional_permission_required: 'Additional permission required',
  temporarily_unavailable: 'Temporarily unavailable',
  administratively_disabled: 'Administratively disabled',
  credentials_undecryptable: 'Credentials cannot be decrypted',
}

export function availabilityLabel(value: string | undefined | null): string {
  if (!value) return 'Unknown'
  return AVAILABILITY_LABELS[value] || value
}

export function isProviderSelectable(state: ProviderSetupState | undefined | null): boolean {
  if (!state) return false
  if (state.selectable) return true
  return (
    state.catalog_count > 0 &&
    state.availability !== 'administratively_disabled' &&
    state.availability !== 'not_configured' &&
    state.availability !== 'credentials_undecryptable'
  )
}

export function shouldShowRetry(availability: ProviderAvailability | string | undefined): boolean {
  return (
    availability === 'refresh_failed_cached_available' ||
    availability === 'temporarily_unavailable' ||
    availability === 'configured_loading_catalog' ||
    availability === 'credentials_accepted_no_projects' ||
    availability === 'additional_permission_required'
  )
}

export function permissionHint(availability: string | undefined, category?: string | null): string | null {
  if (availability === 'credentials_accepted_no_projects') {
    return 'Jira accepted the credentials, but this account cannot see any projects. Verify Browse Projects permission for the Jira service account.'
  }
  if (category === 'missing_code_scope') {
    return 'Projects are visible, but Code (Read) appears missing for repositories.'
  }
  if (category === 'missing_build_scope') {
    return 'Repositories are visible, but Build (Read) appears missing for pipelines.'
  }
  if (category === 'secret_decrypt_failed') {
    return 'Stored credentials cannot be decrypted. Verify DATA_ENCRYPTION_KEY is stable in the OpenShift Secret.'
  }
  return null
}
