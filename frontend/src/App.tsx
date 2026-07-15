import { useEffect, useState } from 'react'
import { useAuth } from './auth/useAuth'
import { useScope, type ScopeState } from './auth/useScope'
import type { ScopeRole } from './api/types'
import { parseDeepLink } from './filters/deepLink'
import { BudgetGrid } from './grid/BudgetGrid'
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

function roleLabel(role: ScopeRole | null): string {
  switch (role) {
    case 'admin':
      return 'ผู้ดูแลระบบ'
    case 'filler':
      return 'ผู้กรอกงบประมาณ'
    case 'see_only':
      return 'ดูอย่างเดียว'
    case 'none':
      return 'ไม่มีสิทธิ์เข้าถึง'
    default:
      return '—'
  }
}

interface UserBarProps {
  email: string | null
  authLoading: boolean
  authError: string | null
  scope: ScopeState
}

/** Login-bar area: who am I + what can I access (ADR-0004/0019). The ฝ่าย
 * picker itself (สายงาน›ฝ่าย›CC, counts) is `BudgetGrid`'s `DeptPicker`
 * (A8) — this bar only surfaces identity + scope counts. Takes
 * auth/scope as props (resolved once in `App`) rather than calling the
 * hooks again, so the page fires one `/me` + one `/scope` request, not two. */
function UserBar({ email, authLoading, authError, scope }: UserBarProps) {
  if (authLoading || scope.loading) {
    return (
      <section className="user-bar" data-testid="user-bar">
        <span className="user-bar-status">กำลังโหลดข้อมูลผู้ใช้…</span>
      </section>
    )
  }

  if (authError) {
    return (
      <section className="user-bar" data-testid="user-bar">
        <span className="user-bar-status user-bar-error">
          โหลดข้อมูลผู้ใช้ไม่สำเร็จ — กรุณาลองรีเฟรชหน้าใหม่
        </span>
      </section>
    )
  }

  if (scope.error) {
    return (
      <section className="user-bar" data-testid="user-bar">
        <span className="user-bar-status user-bar-error">
          โหลดข้อมูลสิทธิ์ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง
        </span>
      </section>
    )
  }

  return (
    <section className="user-bar" data-testid="user-bar">
      <div className="user-id">
        <span className="user-email">{email}</span>
        {scope.isAdmin && <span className="role-badge admin">Admin</span>}
        <span className="role-badge">{roleLabel(scope.role)}</span>
      </div>
      <div className="user-chips">
        <span className="user-chip" title="Cost Center ที่กรอกงบประมาณได้ (Fill scope)">
          <span className="k">Fill</span>
          <span className="v">{scope.fillCostCenters.length} CC</span>
        </span>
        <span className="user-chip" title="Cost Center ที่ดูได้ทั้งหมด (See scope)">
          <span className="k">See</span>
          <span className="v">{scope.seeCostCenters.length} CC</span>
        </span>
      </div>
    </section>
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
