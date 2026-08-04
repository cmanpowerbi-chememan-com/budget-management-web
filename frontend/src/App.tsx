import { useEffect, useState } from 'react'
import { useAuth } from './auth/useAuth'
import { useScope } from './auth/useScope'
import { SessionExpiredDialog } from './auth/SessionExpiredDialog'
import { parseDeepLink } from './filters/deepLink'
import { BudgetGrid } from './grid/BudgetGrid'
import { UserBar } from './userbar/UserBar'
import { currentSearch } from './platform/location'
import { usePersistedState } from './platform/usePersistedToggle'

const THEME_STORAGE_KEY = 'budget-theme'
type Theme = 'light' | 'dark'

function decodeTheme(raw: string | null): Theme {
  return raw === 'dark' ? 'dark' : 'light'
}

function encodeTheme(theme: Theme): string {
  return theme
}

/** Nav-bar dark/light toggle — demonstrates the ported dark-theme tokens
 * (tokens.css) actually work; A8+ can reuse the same `data-theme` switch.
 * Persistence guard shared with the admin-view toggle via
 * platform/usePersistedToggle (ARCH-b); the pre-paint <script> in
 * app/layout.tsx (ARCH-a) already applies the stored theme before this
 * component ever mounts, so this effect only needs to keep the DOM attribute
 * in sync with subsequent toggles. */
function ThemeToggle() {
  const [theme, setTheme] = usePersistedState<Theme>(
    THEME_STORAGE_KEY,
    'local',
    'light',
    decodeTheme,
    encodeTheme,
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  return (
    <button
      type="button"
      className="icon-btn"
      onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
      aria-label="สลับโหมดสี"
      title="สลับโหมดสี (light/dark)"
    >
      {theme === 'light' ? '🌙' : '☀️'}
    </button>
  )
}

function App() {
  // Parsed once on load — ADR-0016 deep-link is convenience-only, the
  // server enforces scope regardless of what this pre-fills; BudgetGrid
  // validates `filter.dept` against the caller's actual scope before ever
  // using it (never a bearer of access).
  const [filter] = useState(() => parseDeepLink(currentSearch()))
  const { email, loading: authLoading, error: authError } = useAuth()
  const scope = useScope()

  const ready = !authLoading && !authError && !scope.loading && !scope.error

  return (
    <>
      {/* Mounted unconditionally, above the `ready` gate below — must still
          render even when the very first boot call (GET /me, useAuth) is
          what raises the session-expiry latch, before BudgetGrid mounts. */}
      <SessionExpiredDialog />

      <nav className="nav">
        <div className="nav-inner">
          <div className="nav-logo-text">
            <span className="name">Budget Management</span>
            <span className="sub">Chememan</span>
          </div>
          <ThemeToggle />
        </div>
      </nav>

      <main className="wrap">
        <header className="page-head">
          <UserBar email={email} authLoading={authLoading} authError={authError} scope={scope} />
          <div className="page-title-row">
            <h1 className="page-title glassy">OPEX <em>Management.</em></h1>
          </div>
        </header>

        {ready && email && <BudgetGrid scope={scope} initialFilter={filter} />}
      </main>
    </>
  )
}

export default App
