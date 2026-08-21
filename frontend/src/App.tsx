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
          {/* Original full-colour wordmark (2026-08-21, jakkaritw verbatim:
              "logo เอาแบบ original") — supersedes the 2026-08-15
              white-knockout call this comment used to describe. Source:
              /chememan-full-logo.png, byte-identical to the DS (design
              system) repo's assets/logo/chememan-full-logo.png. Its
              dark-green ink only reaches 1.89:1 on the CI green shell
              (#00805e) — nearly the shell's own hue now, effectively
              invisible on its own — so it sits on a small white plate
              (.nav-logo-plate, global.css) below it, the standard brand
              treatment for dropping the mark onto a colored surface.
              /chememan-full-logo-white.png stays in public/, unused by
              this file today, kept for any future plain-shell placement —
              not deleted. */}
          {/* alt="" (2026-08-15 gate finding): decorative — the "Chememan"
              text two nodes below already carries this for screen readers,
              so a real alt would announce it twice. */}
          <div className="nav-logo-plate">
            <img src="/chememan-full-logo.png" alt="" className="nav-logo" />
          </div>
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
