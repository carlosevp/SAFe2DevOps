const STORAGE_KEY = 'safedevops.activeAssessment'

export type StoredAssessment = {
  id: string
  name: string
}

export function readStoredAssessment(): StoredAssessment | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredAssessment
    if (!parsed?.id || typeof parsed.id !== 'string') return null
    return {
      id: parsed.id,
      name: typeof parsed.name === 'string' && parsed.name.trim() ? parsed.name : 'Assessment',
    }
  } catch {
    return null
  }
}

export function writeStoredAssessment(id: string, name: string) {
  if (!id) return
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ id, name: name || 'Assessment' }))
  } catch {
    // private mode / quota — in-memory App state still works for the tab session
  }
}

export function clearStoredAssessment() {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

export function formatAssessmentNotFound(assessmentId: string | null | undefined): string {
  const id = assessmentId?.trim()
  return (
    'Assessment not found on the server' +
    (id ? ` (id ${id.slice(0, 8)}…)` : '') +
    '. The browser may be using a stale id after a redeploy, or the database volume is empty. ' +
    'Use Resume on the welcome screen to pick a saved assessment, or start a new one. ' +
    'On Railway, confirm a persistent volume is mounted at /data with DATA_DIR=/data.'
  )
}
