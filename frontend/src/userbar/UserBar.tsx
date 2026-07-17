import type { ScopeRole } from '../api/types'
import type { ScopeState } from '../auth/useScope'
import { deriveScopeSummary } from './model'
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
 * omitted (real Entra auth has no persona to switch into). Counts are
 * FILL-scope only — See is broader/viewing and dropped from the header by
 * design. Only a PURE admin (no Fill/See CCs at all, ADR-0014) gets the
 * "sees everything" note in place of the hierarchy; a dual-role admin
 * (e.g. Nipaporn/Waraporn) still sees their own real scope here,
 * independent of whatever `BudgetGrid`'s admin-view toggle is set to. */
export function UserBar({ email, authLoading, authError, scope }: UserBarProps) {
  const isPureAdmin = scope.isAdmin && scope.fillCostCenters.length === 0 && scope.seeCostCenters.length === 0
  const ready = !authLoading && !scope.loading && !authError && !scope.error
  const wantsScopeData = ready && !isPureAdmin

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
  const { divisions, departments: departmentNames } = deriveScopeSummary(departments, scope.fillCostCenters)
  const divisionText =
    divisions.length > 0 ? divisions.join(' · ') : departmentsLoading ? 'กำลังโหลด…' : 'ไม่ระบุสายงาน'
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
                    {departmentNames.map((name) => (
                      <span className="user-chip cc" key={name}>
                        <span className="v">{name}</span>
                      </span>
                    ))}
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
    </section>
  )
}
