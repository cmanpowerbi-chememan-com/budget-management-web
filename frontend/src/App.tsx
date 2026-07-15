import { useEffect, useState } from 'react'
import { useAuth } from './auth/useAuth'
import { useScope } from './auth/useScope'
import type { ScopeRole } from './api/types'
import { parseDeepLink, type DeepLinkFilter } from './filters/deepLink'
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

/** Login-bar area: who am I + what can I access (ADR-0004/0019). The full
 * สายงาน›ฝ่าย›CC hierarchy picker is A8 — this only surfaces identity +
 * scope counts so a developer/tester can see the auth wiring works. */
function UserBar() {
  const { email, loading: authLoading, error: authError } = useAuth()
  const scope = useScope()

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

/** Renders the ADR-0016 deep-link filter as a visible chip so the parse
 * result is testable/observable — A8's real picker consumes the same
 * `filter` state. */
function FilterSummary({ filter }: { filter: DeepLinkFilter }) {
  if (!filter.dept && !filter.year) {
    return (
      <div className="filter-chip filter-chip-empty" data-testid="filter-chip">
        ยังไม่มีตัวกรองจากลิงก์อีเมล — เลือกฝ่าย/ปีด้านล่าง (มาใน A8)
      </div>
    )
  }

  const parts: string[] = []
  if (filter.dept) parts.push(`ฝ่าย ${filter.dept}`)
  if (filter.year) parts.push(`ปี ${filter.year}`)

  return (
    <div className="filter-chip" data-testid="filter-chip">
      🔗 ลิงก์จากอีเมล: {parts.join(' · ')}
    </div>
  )
}

function App() {
  // Parsed once on load — ADR-0016 deep-link is convenience-only, the
  // server enforces scope regardless of what this pre-fills.
  const [filter] = useState<DeepLinkFilter>(() => parseDeepLink(window.location.search))

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
          <UserBar />
          <div className="page-title-row">
            <h1 className="page-title">OPEX Management</h1>
          </div>
          <FilterSummary filter={filter} />
        </header>

        <section className="table-panel-placeholder" data-testid="grid-placeholder">
          ตารางงบประมาณ (SAP / Approved / Pending) จะมาในขั้นถัดไป — A8
        </section>
      </main>
    </>
  )
}

export default App
