import { useState, useEffect, useCallback } from 'react'
import Header from './components/Header'
import Welcome from './screens/Welcome'
import Integrations from './screens/Integrations'
import SetupWizard from './screens/SetupWizard'
import EvidencePreview from './screens/EvidencePreview'
import WorkshopRoom from './screens/WorkshopRoom'
import Checkpoint from './screens/Checkpoint'
import RemoteContributor from './screens/RemoteContributor'
import AdminReview from './screens/AdminReview'
import Results from './screens/Results'
import AISettings from './screens/AISettings'
import EnterpriseStandards from './screens/EnterpriseStandards'
import AdminLogin from './screens/AdminLogin'
import { adminLogout, getAdminMe } from './lib/api'
import { readStoredAssessment, writeStoredAssessment } from './lib/assessmentSession'
import type { Screen } from './types'

const ASSESSMENT_SCREENS: Screen[] = ['setup', 'evidence', 'workshop', 'checkpoint', 'admin-review', 'results']

/** Screens that require an authenticated admin session. */
const ADMIN_PROTECTED_SCREENS: Screen[] = [
  'welcome',
  'integrations',
  'setup',
  'evidence',
  'workshop',
  'checkpoint',
  'admin-review',
  'results',
  'ai-settings',
  'enterprise-standards',
]

function readInviteToken(): string | null {
  const params = new URLSearchParams(window.location.search)
  return params.get('invite')
}

export default function App() {
  const [inviteToken] = useState<string | null>(() => readInviteToken())
  const [screen, setScreen] = useState<Screen>(() => (readInviteToken() ? 'remote-contributor' : 'welcome'))
  const [dark, setDark] = useState(false)
  const stored = readStoredAssessment()
  const [assessmentId, setAssessmentId] = useState<string | null>(() => stored?.id ?? null)
  const [assessmentName, setAssessmentName] = useState(() => stored?.name ?? 'Assessment')
  const [authChecked, setAuthChecked] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)
  const [pendingScreen, setPendingScreen] = useState<Screen | null>(null)

  const bindAssessment = useCallback((id: string, name: string) => {
    setAssessmentId(id)
    setAssessmentName(name || 'Assessment')
    writeStoredAssessment(id, name || 'Assessment')
  }, [])

  useEffect(() => {
    if (dark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [dark])

  useEffect(() => {
    if (inviteToken) {
      setAuthChecked(true)
      return
    }
    getAdminMe()
      .then(me => setAuthenticated(Boolean(me.authenticated)))
      .catch(() => setAuthenticated(false))
      .finally(() => setAuthChecked(true))
  }, [inviteToken])

  const navigateProtected = useCallback((next: Screen) => {
    if (ADMIN_PROTECTED_SCREENS.includes(next) && !authenticated) {
      setPendingScreen(next)
      return
    }
    setScreen(next)
  }, [authenticated])

  async function handleLogout() {
    try {
      await adminLogout()
    } catch {
      // Still clear local auth state.
    }
    setAuthenticated(false)
    setPendingScreen(null)
    setScreen('welcome')
  }

  const headerAssessmentName = ASSESSMENT_SCREENS.includes(screen) ? assessmentName : undefined
  const isRemote = screen === 'remote-contributor' || Boolean(inviteToken)

  if (isRemote) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--background)', color: 'var(--foreground)' }}>
        <RemoteContributor dark={dark} inviteToken={inviteToken} />
      </div>
    )
  }

  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--background)', color: 'var(--muted-foreground)' }}>
        Checking admin session…
      </div>
    )
  }

  if (!authenticated) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--background)', color: 'var(--foreground)' }}>
        <AdminLogin
          dark={dark}
          onAuthenticated={() => {
            setAuthenticated(true)
            setScreen(pendingScreen || 'welcome')
            setPendingScreen(null)
          }}
        />
      </div>
    )
  }

  const showCheckpoint = screen === 'checkpoint'

  return (
    <div style={{ minHeight: '100vh', background: 'var(--background)', color: 'var(--foreground)' }}>
      <Header
        dark={dark}
        onToggleDark={() => setDark(d => !d)}
        screen={screen}
        assessmentName={headerAssessmentName}
        onNavigate={navigateProtected}
        onSaveExit={() => setScreen('welcome')}
        onLogout={() => void handleLogout()}
      />

      {screen === 'welcome' && (
        <Welcome
          dark={dark}
          onNavigate={navigateProtected}
          onResumeAssessment={(id, name, next) => {
            bindAssessment(id, name)
            navigateProtected(next)
          }}
        />
      )}
      {screen === 'integrations' && (
        <Integrations dark={dark} onNavigate={navigateProtected} />
      )}
      {screen === 'setup' && (
        <SetupWizard
          dark={dark}
          onNavigate={navigateProtected}
          onAssessmentReady={(id, name) => {
            bindAssessment(id, name)
          }}
        />
      )}
      {screen === 'evidence' && (
        <EvidencePreview
          dark={dark}
          onNavigate={navigateProtected}
          assessmentId={assessmentId}
          assessmentName={assessmentName}
        />
      )}
      {(screen === 'workshop' || screen === 'checkpoint') && (
        <div style={{ position: 'relative' }}>
          <WorkshopRoom
            dark={dark}
            onNavigate={navigateProtected}
            assessmentId={assessmentId}
            onAssessmentBound={(id, name) => bindAssessment(id, name)}
          />
          {showCheckpoint && (
            <Checkpoint dark={dark} onNavigate={navigateProtected} assessmentId={assessmentId} />
          )}
        </div>
      )}
      {screen === 'admin-review' && (
        <AdminReview dark={dark} onNavigate={navigateProtected} assessmentId={assessmentId} />
      )}
      {screen === 'results' && (
        <Results dark={dark} onNavigate={navigateProtected} assessmentId={assessmentId} />
      )}
      {screen === 'ai-settings' && (
        <AISettings dark={dark} onNavigate={navigateProtected} />
      )}
      {screen === 'enterprise-standards' && (
        <EnterpriseStandards dark={dark} onNavigate={navigateProtected} />
      )}
    </div>
  )
}
