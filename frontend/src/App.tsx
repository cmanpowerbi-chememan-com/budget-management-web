import { useState } from 'react'
import { useAuth } from './auth/useAuth'
import { useScope } from './auth/useScope'
import { SessionExpiredDialog } from './auth/SessionExpiredDialog'
import { parseDeepLink } from './filters/deepLink'
import { BudgetGrid } from './grid/BudgetGrid'
import { UserBar } from './userbar/UserBar'
import { currentSearch } from './platform/location'

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
          {/* White knockout variant (2026-08-15, jakkaritw: "ทำโลโก้สีขาวใหม่")
              — the stock artwork's dark-green wordmark only reached 2.84:1 on
              the #2E8B57 shell. -white.png reverses the ink to solid white
              while keeping the artwork's own white areas transparent (shell
              shows through), so it reads at the same 4.25:1 ceiling as every
              other on-shell element. Original /chememan-full-logo.png kept in
              public/ for any future light-shell use — not deleted. */}
          {/* alt="" (2026-08-15 gate finding): decorative — the "Chememan"
              text two nodes below already carries this for screen readers,
              so a real alt would announce it twice. */}
          <img src="/chememan-full-logo-white.png" alt="" className="nav-logo" />
          <div className="nav-logo-text">
            <span className="name">Budget Management</span>
            <span className="sub">Chememan</span>
          </div>
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
