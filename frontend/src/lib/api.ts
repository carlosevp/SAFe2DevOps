const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  status: number
  code: string
  details: unknown

  constructor(status: number, code: string, message: string, details: unknown = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {})
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...init,
    headers,
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    const error = typeof payload === 'object' && payload && 'error' in payload
      ? (payload as { error: { code?: string; message?: string; details?: unknown } }).error
      : undefined
    throw new ApiError(
      response.status,
      error?.code || `http_${response.status}`,
      error?.message || 'Request failed',
      error?.details || {},
    )
  }

  return payload as T
}

export function getLiveHealth() {
  return apiFetch<{ status: string }>('/api/health/live')
}

export function getReadyHealth() {
  return apiFetch<{ status: string; checks: Record<string, unknown> }>('/api/health/ready')
}

export function adminLogin(password: string) {
  return apiFetch<{ status: string; role?: string }>('/api/auth/admin/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })
}

export function adminLogout() {
  return apiFetch<{ status: string }>('/api/auth/admin/logout', {
    method: 'POST',
  })
}

export function adminMe() {
  return apiFetch<{ authenticated: boolean; role?: string; subject?: string }>('/api/auth/admin/me')
}
