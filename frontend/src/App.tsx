import { useEffect, useState } from 'react'
import { useAuth } from './auth/useAuth'
import { useScope } from './auth/useScope'
import { parseDeepLink } from './filters/deepLink'
import { BudgetGrid } from './grid/BudgetGrid'
import { UserBar } from './userbar/UserBar'
import './styles/global.css'

const THEME_STORAGE_KEY = 'budget-theme'
type Theme = 'light' | 'dark'

function readStoredTheme(): Theme {
  return window.localStorage.getItem(THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light'
}

/** Nav-bar dark/light toggle — demonstrates the ported dark-theme tokens
 * (tokens.css) actually work; A8+ can reuse the same `data-theme` switch. */
function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readStoredTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  }, [theme])

  return (
    <button
      type="button"
      className="icon-btn"
      onClick={() => setTheme((current) => (current === 'light' ? 'dark' : 'light'))}
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
  const [filter] = useState(() => parseDeepLink(window.location.search))
  const { email, loading: authLoading, error: authError } = useAuth()
  const scope = useScope()

  const ready = !authLoading && !authError && !scope.loading && !scope.error

  return (
    <>
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
            <h1 className="page-title">OPEX Management</h1>
          </div>
        </header>

        {ready && email && <BudgetGrid scope={scope} initialFilter={filter} />}
      </main>
    </>
  )
}

export default App
