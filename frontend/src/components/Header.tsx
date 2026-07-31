import { Sun, Moon, HelpCircle, LogOut, Save } from 'lucide-react'
import type { Screen } from '../types'

interface HeaderProps {
  dark: boolean
  onToggleDark: () => void
  screen: Screen
  assessmentName?: string
  onNavigate: (s: Screen) => void
  onSaveExit?: () => void
  onLogout?: () => void
}

const statusLabels: Partial<Record<Screen, string>> = {
  workshop: 'In Progress',
  'admin-review': 'Awaiting Review',
  results: 'Published',
  setup: 'Setup',
  evidence: 'Setup',
}

export default function Header({ dark, onToggleDark, screen, assessmentName, onNavigate, onSaveExit, onLogout }: HeaderProps) {
  const showAssessment = assessmentName && !['welcome', 'integrations', 'ai-settings', 'enterprise-standards'].includes(screen)
  const statusLabel = statusLabels[screen]

  return (
    <header
      className="sticky top-0 z-50 w-full border-b flex items-center"
      style={{
        background: dark ? 'var(--card)' : '#fff',
        borderColor: 'var(--border)',
        height: 56,
        paddingLeft: 24,
        paddingRight: 24,
        gap: 0,
      }}
    >
      {/* Logo */}
      <button
        onClick={() => onNavigate('welcome')}
        className="flex items-center gap-2.5 mr-6 shrink-0"
        style={{ textDecoration: 'none' }}
      >
        <div
          className="rounded flex items-center justify-center text-xs font-bold tracking-wider"
          style={{
            width: 32,
            height: 32,
            background: 'var(--primary)',
            color: '#fff',
            fontFamily: 'Inter, sans-serif',
          }}
        >
          SD
        </div>
        <span
          className="font-semibold text-sm hidden md:block"
          style={{ color: 'var(--foreground)', letterSpacing: '-0.01em' }}
        >
          SAFe DevOps
        </span>
      </button>

      {/* Divider */}
      {showAssessment && (
        <>
          <div style={{ width: 1, height: 20, background: 'var(--border)', marginRight: 16 }} />
          <div className="flex items-center gap-2 mr-auto">
            <span className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>
              {assessmentName}
            </span>
            {statusLabel && (
              <span
                className="text-xs px-2 py-0.5 rounded-full font-medium"
                style={{
                  background: screen === 'workshop' ? '#dcfce7' : screen === 'results' ? '#dbeafe' : 'var(--muted)',
                  color: screen === 'workshop' ? '#166534' : screen === 'results' ? '#1e40af' : 'var(--muted-foreground)',
                }}
              >
                {statusLabel}
              </span>
            )}
          </div>
        </>
      )}

      {!showAssessment && <div className="mr-auto" />}

      {/* Right actions */}
      <div className="flex items-center gap-1">
        {(screen === 'workshop' || screen === 'setup' || screen === 'evidence') && (
          <button
            onClick={onSaveExit}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded transition-base mr-1"
            style={{ color: 'var(--muted-foreground)' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--muted)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            <Save size={14} />
            <span className="hidden sm:inline">Save & exit</span>
          </button>
        )}
        <button
          className="p-2 rounded transition-base"
          style={{ color: 'var(--muted-foreground)' }}
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--muted)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          title="Help"
        >
          <HelpCircle size={17} />
        </button>
        <button
          onClick={onToggleDark}
          className="p-2 rounded transition-base"
          style={{ color: 'var(--muted-foreground)' }}
          onMouseEnter={e => (e.currentTarget.style.background = 'var(--muted)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {dark ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        {onLogout && (
          <button
            onClick={onLogout}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded transition-base ml-1"
            style={{ color: 'var(--muted-foreground)' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--muted)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            title="Sign out"
          >
            <LogOut size={15} />
            <span className="hidden sm:inline">Sign out</span>
          </button>
        )}
      </div>
    </header>
  )
}
