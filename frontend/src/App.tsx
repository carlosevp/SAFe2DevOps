import { useState, useEffect } from 'react'
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
import type { Screen } from './types'

const ASSESSMENT_SCREENS: Screen[] = ['setup', 'evidence', 'workshop', 'checkpoint', 'admin-review', 'results']

export default function App() {
  const [screen, setScreen] = useState<Screen>('welcome')
  const [dark, setDark] = useState(false)
  const [assessmentId, setAssessmentId] = useState<string | null>(null)
  const [assessmentName, setAssessmentName] = useState('Claims Integration')

  useEffect(() => {
    if (dark) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [dark])

  const headerAssessmentName = ASSESSMENT_SCREENS.includes(screen) ? assessmentName : undefined
  const isRemote = screen === 'remote-contributor'

  // Remote contributor has its own minimal layout
  if (isRemote) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--background)', color: 'var(--foreground)' }}>
        <RemoteContributor dark={dark} />
      </div>
    )
  }

  // Checkpoint renders as an overlay on top of workshop
  const showCheckpoint = screen === 'checkpoint'

  return (
    <div style={{ minHeight: '100vh', background: 'var(--background)', color: 'var(--foreground)' }}>
      <Header
        dark={dark}
        onToggleDark={() => setDark(d => !d)}
        screen={screen}
        assessmentName={headerAssessmentName}
        onNavigate={setScreen}
        onSaveExit={() => setScreen('welcome')}
      />

      {screen === 'welcome' && (
        <Welcome dark={dark} onNavigate={setScreen} />
      )}
      {screen === 'integrations' && (
        <Integrations dark={dark} onNavigate={setScreen} />
      )}
      {screen === 'setup' && (
        <SetupWizard
          dark={dark}
          onNavigate={setScreen}
          onAssessmentReady={(id, name) => {
            setAssessmentId(id)
            setAssessmentName(name)
          }}
        />
      )}
      {screen === 'evidence' && (
        <EvidencePreview
          dark={dark}
          onNavigate={setScreen}
          assessmentId={assessmentId}
          assessmentName={assessmentName}
        />
      )}
      {(screen === 'workshop' || screen === 'checkpoint') && (
        <div style={{ position: 'relative' }}>
          <WorkshopRoom dark={dark} onNavigate={setScreen} assessmentId={assessmentId} />
          {showCheckpoint && (
            <Checkpoint dark={dark} onNavigate={setScreen} assessmentId={assessmentId} />
          )}
        </div>
      )}
      {screen === 'admin-review' && (
        <AdminReview dark={dark} onNavigate={setScreen} />
      )}
      {screen === 'results' && (
        <Results dark={dark} onNavigate={setScreen} />
      )}
      {screen === 'ai-settings' && (
        <AISettings dark={dark} onNavigate={setScreen} />
      )}

      {/* Toast for dark mode indication */}
      <div
        className="fixed bottom-5 right-5 z-50 pointer-events-none"
        style={{ display: 'none' }}
      >
        <div
          className="rounded-xl px-4 py-3 text-sm font-medium shadow-lg"
          style={{ background: 'var(--card)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
        >
          {dark ? 'Dark mode enabled' : 'Light mode enabled'}
        </div>
      </div>
    </div>
  )
}
