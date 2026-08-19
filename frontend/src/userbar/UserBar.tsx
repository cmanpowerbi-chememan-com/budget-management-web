import type { ScopeRole } from '../api/types'
import type { ScopeState } from '../auth/useScope'
import { deriveScopeSummary, truncateChipNames } from './model'
import { useFillGlCount } from './useFillGlCount'
import { useOwnDepartments } from './useOwnDepartments'

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

function defaultPlanningYear(): number {
  // Same convention as `grid/BudgetGrid.tsx`'s own default — the header's
  // GL count is a scope indicator, not tied to whatever year the user
  // later picks in the grid below, so it always reads "now + 1".
  return new Date().getFullYear() + 1
}

/** Avatar initials from the email local-part (no real display name exists
 * — `/me` returns only an email), mirroring the mockup's own fallback. */
function initialsOf(emailLocal: string): string {
  const cleaned = emailLocal.replace(/[()@._-]/g, ' ').trim()
  return (cleaned.slice(0, 2) || '??').toUpperCase()
}

function ChevronIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="v3-arrow">
      <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export interface UserBarProps {
  email: string | null
  authLoading: boolean
  authError: string | null
  scope: ScopeState
}

/** Login-bar area: who am I + what can I access (ADR-0004/0019) — ported
 * from the mockup's V3 layout: avatar/identity | สายงาน › ฝ่าย(n) › Cost
 * Centers(n)/GL Codes(n). The mockup's user-switcher is deliberately
 * omitted (real Entra auth has no persona to switch into). The Cost
 * Centers(n)/GL Codes(n) pills and the ฝ่าย *count* badge stay FILL-scope
 * only — See is broader/viewing, so those numbers never imply the ability
 * to type. The สายงาน/ฝ่าย chip TEXT itself falls back to See when Fill is
 * empty (`deriveScopeSummary`, `laddawank-no-division-chip`) so a
 * manager/See-only user reads their real division instead of
 * "ไม่ระบุสายงาน" — the existing `role-badge` ("ดูอย่างเดียว") is what marks
 * that case as view-only, not a new label. Only a PURE admin (no Fill/See
 * CCs at all, ADR-0014) gets the "sees everything" note in place of the
 * hierarchy; a dual-role admin (e.g. Nipaporn/Waraporn) still sees their
 * own real scope here, independent of whatever `BudgetGrid`'s admin-view
 * toggle is set to. */
export function UserBar({ email, authLoading, authError, scope }: UserBarProps) {
  const isPureAdmin = scope.isAdmin && scope.fillCostCenters.length === 0 && scope.seeCostCenters.length === 0
  const ready = !authLoading && !scope.loading && !authError && !scope.error
  // A caller with role='none' (no admin, no Fill, no See) has nothing to show
  // here either — same "no scope, no backend work" invariant BudgetGrid's own
  // `hasNoScope` gate already enforces. Without this check, useOwnDepartments
  // fired GET /scope/departments even for a no-scope caller (reproduced live,
  // tracker e2e-stale-specs-fix): a wasted call the header can never use,
  // since deriveScopeSummary of an empty/no-scope result renders nothing.
  const wantsScopeData = ready && !isPureAdmin && scope.role !== 'none'

  const { departments, loading: departmentsLoading } = useOwnDepartments(wantsScopeData)
  const { count: glCount, loading: glCountLoading } = useFillGlCount(
    defaultPlanningYear(),
    wantsScopeData ? scope.fillCostCenters : [],
  )

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

  const emailLocal = (email ?? '').split('@')[0]
  const { divisions, departments: departmentNames } = deriveScopeSummary(
    departments,
    scope.fillCostCenters,
    scope.seeCostCenters,
  )
  // A senior manager's fallback-to-See chip (deriveScopeSummary, above) can
  // fan out to 9 สายงาน/45 ฝ่าย and overflow the header (bunpotk@chememan.com,
  // measured 174 rendered chars) — truncateChipNames caps BOTH chips at the
  // first 3 names + a Thai "+N <unit>" suffix (jakkaritw, verbatim: "โชว์ 3
  // ชื่อแรก แล้วต่อท้าย +6 สายงาน"). The full list stays one click away in
  // the ฝ่าย picker (`DeptPicker`, rendered right below this header in
  // `BudgetGrid`, searchable and grouped by division) — no title/tooltip
  // added here on purpose, it would just duplicate that.
  const { shown: shownDivisions, suffix: divisionSuffix } = truncateChipNames(divisions, 'สายงาน')
  const divisionText =
    divisions.length > 0
      ? [...shownDivisions, ...(divisionSuffix ? [divisionSuffix] : [])].join(' · ')
      : departmentsLoading
        ? 'กำลังโหลด…'
        : 'ไม่ระบุสายงาน'
  const { shown: shownDepartments, suffix: departmentSuffix } = truncateChipNames(departmentNames, 'ฝ่าย')
  const glText = glCountLoading ? '…' : glCount === null ? '—' : String(glCount)

  return (
    <section className="user-bar v3" data-testid="user-bar">
      <div className="v3-id">
        <div className={`user-avatar${scope.isAdmin ? ' admin' : ''}`} aria-hidden="true">
          {initialsOf(emailLocal)}
        </div>
        <div className="v3-id-text">
          <span className="v3-name">{emailLocal}</span>
          <span className="v3-email">{email}</span>
          <span className={`role-badge ${scope.isAdmin ? 'admin' : 'user'}`}>{roleLabel(scope.role)}</span>
        </div>
      </div>

      <div className="v3-flow">
        {isPureAdmin ? (
          <span className="v3-allnote">เห็นข้อมูลทั้งหมด · ทุก Cost Center</span>
        ) : (
          <>
            <div className="v3-seg">
              <span className="meta-tag">สายงาน</span>
              <span className="v3-division">{divisionText}</span>
            </div>

            {departmentNames.length > 0 && (
              <>
                <ChevronIcon />
                <div className="v3-seg">
                  <span className="v3-label-wrap">
                    <span className="meta-tag">ฝ่าย</span>
                    <span className="v3-count" data-testid="v3-dept-count">
                      {departmentNames.length}
                    </span>
                  </span>
                  <div className="v3-depts">
                    {shownDepartments.map((name) => (
                      <span className="user-chip cc" key={name}>
                        <span className="v">{name}</span>
                      </span>
                    ))}
                    {departmentSuffix && (
                      <span className="user-chip cc" data-testid="v3-dept-more">
                        <span className="v">{departmentSuffix}</span>
                      </span>
                    )}
                  </div>
                </div>
              </>
            )}

            {scope.fillCostCenters.length > 0 && (
              <>
                <ChevronIcon />
                <div className="v3-metrics">
                  <span className="v3-cc-pill">
                    <span className="n" data-testid="v3-cc-count">
                      {scope.fillCostCenters.length}
                    </span>
                    <span className="t">Cost Centers</span>
                  </span>
                  <span className="v3-gl-pill">
                    <span className="n" data-testid="v3-gl-count">
                      {glText}
                    </span>
                    <span className="t">GL Codes</span>
                  </span>
                </div>
              </>
            )}
          </>
        )}
      </div>

      {/* Session action, in the slot the mockup's user-switcher (v3-switch,
          demo-only persona picker) used to occupy — real Entra auth has no
          persona to switch into, but a real session STILL needs an exit. A
          plain same-origin <a> straight to Easy Auth's built-in endpoint:
          no client JS, natively keyboard-reachable, its visible text is its
          own accessible name; the shared `a:focus-visible` rule in
          global.css already draws a visible ring, untouched by this change.
          NOTE: /.auth/logout only clears this browser's auth cookie — it
          does not revoke the session server-side, so the same cookie
          replayed elsewhere still works. Shown for every resolved role
          (incl. no-scope/pure-admin) since a stuck user still needs a way
          out; intentionally NOT shown on the loading/error status lines
          above, which render no other control either.
          Styled inline, not via global.css (out of scope for this change,
          the Sea Green theme file is frozen) — `--ink-2`/`--surface`/`--r`/
          `--sans` are the SAME already-live tokens `.v3-email`/`.v3-name`
          use two elements up, just read at the call site instead of adding
          a new stylesheet selector. */}
      <a
        href="/.auth/logout"
        style={{
          marginLeft: 'auto',
          flexShrink: 0,
          padding: '4px 2px',
          fontFamily: 'var(--sans)',
          fontSize: '12.5px',
          fontWeight: 600,
          color: 'var(--ink-2)',
          textDecoration: 'none',
          borderRadius: 'var(--r)',
        }}
      >
        ออกจากระบบ
      </a>
    </section>
  )
}
