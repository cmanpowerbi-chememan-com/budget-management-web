import { useEffect, useMemo, useState } from 'react'
import { AdminModeToggle } from '../admin/AdminModeToggle'
import { useAdminViewToggle } from '../admin/useAdminViewToggle'
import { fetchLockedDepartments, fetchPendingForMe } from '../api/approval'
import { ApiError } from '../api/client'
import { deleteRow, fetchBudgetGrid, fetchDepartments, fetchGlAccounts, saveRow } from '../api/budget'
import type { BudgetRow, DepartmentRow, GlAccount } from '../api/types'
import { costCentersOfDepartment, isFillerOfDepartment } from '../approval/model'
import { ApprovalActionBar } from '../approval/ApprovalActionBar'
import { AttachmentsModal } from '../attachments/AttachmentsModal'
import type { ScopeState } from '../auth/useScope'
import type { DeepLinkFilter } from '../filters/deepLink'
import { DetailSubform } from '../subform/DetailSubform'
import { deriveTravelSideFromGl, type TripSide } from '../subform/model'
import { TripManager } from '../subform/TripManager'
import { AddTransactionForm, type AddResult } from './AddTransactionForm'
import { GridTable, type RowMessage } from './GridTable'
import {
  buildNewRowPayload, buildSavePayload, glMetaFor, isCostCenterLocked, lockedCostCenterDepartments, mergeSavedRow, type MonthKey,
} from './model'
import { DeptPicker } from '../picker/DeptPicker'
import { buildDeptHierarchy, resolveInitialDept } from '../picker/model'
import { YearPicker } from './YearPicker'

export interface BudgetGridProps {
  scope: ScopeState
  initialFilter: DeepLinkFilter
}

/** Single source of truth for the "no Fill/See scope" contact — the CC↔Filler
 * master (`cc dept.xlsx`, ADR-0019) that feeds `dbo.cc_filler_map`. Exported
 * so any other empty state needing the same contact (e.g. DeptPicker) reuses
 * these instead of re-typing the email/filename. */
export const SCOPE_ACCESS_CONTACT_EMAIL = 'nipapornt@chememan.com'
export const SCOPE_ACCESS_SOURCE_FILE = 'cc dept.xlsx'

function rowKey(cc: string, gl: string): string {
  return `${cc}|${gl}`
}

function defaultPlanningYear(): number {
  // Pending layer is the NEXT fiscal year relative to "now" (planning
  // year Y+1, per read_model.get_budget_grid's `year` param contract).
  return new Date().getFullYear() + 1
}

/** Main budget grid (A8) — ฝ่าย + year pickers, 3-layer grid, inline
 * Pending-cell editing with per-row save/conflict handling, and
 * "+ เพิ่ม transaction". Owns all API calls for this page; `GridTable`/
 * `DeptPicker`/`AddTransactionForm` are pure presentational children. */
export function BudgetGrid({ scope, initialFilter }: BudgetGridProps) {
  const [year, setYear] = useState<number>(initialFilter.year ?? defaultPlanningYear())
  const [department, setDepartment] = useState<string | null>(null)
  const [deptResolved, setDeptResolved] = useState(false)

  const [departments, setDepartments] = useState<DepartmentRow[]>([])
  const [glRef, setGlRef] = useState<GlAccount[]>([])
  const [rows, setRows] = useState<BudgetRow[]>([])
  const [rowMessages, setRowMessages] = useState<Record<string, RowMessage>>({})

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // A9: which special-GL subform (or Trip Manager) is currently open, if
  // any — only one at a time, opened from a special row's "เปิดฟอร์มย่อย" /
  // "🔒 ดูรายละเอียด" button (GridTable). `null` = none open. `readOnly`
  // (ADR-0013 read-only lock, UI parity port, 2026-08-05) is captured from
  // `!row.editable` AT OPEN TIME — the grid already computed the real
  // edit-rights rule (Fill scope × department lock × admin bypass) server-
  // side, so the modal never re-derives it.
  const [detailTarget, setDetailTarget] = useState<
    { costCenter: string; glAccount: string; glGroup: string; readOnly: boolean } | null
  >(null)
  // The open Trip Manager's target CC + its LOCKED accounting side (jakkaritw,
  // 2026-08-04 — final: the side is always the one the clicked GL row
  // belongs to, for every user incl. admins — never editable, never
  // inferred from ฝ่าย history) + its read-only lock (ADR-0013, same policy
  // as `detailTarget` above). One state, not several, so the values can
  // never drift out of sync with each other.
  const [tripManagerOpenFor, setTripManagerOpenFor] = useState<{ costCenter: string; lockedSide: TripSide; readOnly: boolean } | null>(
    null,
  )
  const [attachmentsOpen, setAttachmentsOpen] = useState(false)
  // Fullscreen overlay (⤢ toggle, jakkaritw-approved 2026-07-31) — lifts the
  // WHOLE grid block (toolbar + legend + both side-tables + Submit bar) into
  // a fixed layer above the nav. State lives HERE, not in GridTable (unlike
  // columnsCollapsed), because the overlay must contain controls that are
  // GridTable's siblings. Deliberately NOT persisted — same policy as
  // compact mode: always starts normal on load.
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [pendingApprovalDepartments, setPendingApprovalDepartments] = useState<Set<string>>(new Set())
  // "+ เพิ่ม Transaction" lock-awareness (2026-08-08 bug fix, ADR-0013 UI
  // parity): every one of the CALLER's OWN Fill-scope departments that is
  // currently mid-approval/APPROVED for `year` (`GET
  // /approval/locked-departments`, backed by the exact same
  // `read_model.fetch_locked_departments` the grid's own `row.editable` is
  // built from — one source, cannot drift). Crossed with `departments`
  // (the live CC->department mapping already fetched for the ฝ่าย picker)
  // in `lockedCostCenters` below.
  const [lockedDepartments, setLockedDepartments] = useState<Set<string>>(new Set())
  // 2026-08-08 3-state extension: `year` has no `dbo.submission_deadline` row
  // at all — a YEAR-wide lock (every department, not just the ones already
  // mid-approval), fetched from the SAME `GET /approval/locked-departments`
  // call as `lockedDepartments` above (its `year_not_open` field) so this can
  // never drift from what the server would actually refuse on write. Always
  // `false` for admin (the endpoint itself reports `false` for an admin
  // caller) and for admin-wide (skipped entirely below, same reasoning as
  // `lockedDepartments`).
  const [yearNotOpen, setYearNotOpen] = useState(false)

  // Pure admins (ADR-0014: no base actor role, so no toggle — always
  // admin-wide). Dual-role admins (is_admin AND some Fill/See scope, e.g.
  // Nipaporn/Waraporn) get an explicit "โหมด Admin" toggle, default OFF
  // (A10) — the ONE state this component threads everywhere admin-wide vs
  // personal scope matters (read, picker, approve/reject visibility).
  const isPureAdmin = scope.isAdmin && scope.fillCostCenters.length === 0 && scope.seeCostCenters.length === 0
  const isDualRoleAdmin = scope.isAdmin && !isPureAdmin
  const [adminModeOn, setAdminModeOn] = useAdminViewToggle()
  const adminViewEnabled = isPureAdmin || (isDualRoleAdmin && adminModeOn)

  // No-scope empty state (A10 scope-role UX): a caller with no admin, no
  // Fill, and no See has nothing to do on this page — show a friendly Thai
  // message instead of an empty toolbar/grid. `see_only` (e.g. a manager
  // who is nobody's Filler but may still be an approver) keeps the full
  // page, per the brief.
  const hasNoScope = scope.role === 'none'

  function handleAdminModeToggle(next: boolean) {
    setAdminModeOn(next)
    // ADR-0014: switching hats resets the locked ฝ่าย — scope differs
    // between "my ฝ่าย" and "every ฝ่าย" — then immediately re-resolves to
    // the first ฝ่าย of the NEW scope via the same resolveInitialDept path
    // as the initial mount (2026-07-24 jakkaritw: the 2026-07-21 "never
    // land unselected" rule applies after a hat-switch too, not only on
    // page load). deptResolved=false re-opens the resolution branch in the
    // reference-data effect AND holds the grid-load gate, so the grid never
    // flashes an unfiltered (department=null) load in between.
    setDepartment(null)
    setDeptResolved(false)
  }

  // Reference data (GL master + department hierarchy) loads once, then
  // again whenever the admin hat toggles (admin-wide vs personal scope
  // changes the department list itself). The deep-link ฝ่าย (ADR-0016) is
  // only applied once, the first time the real hierarchy arrives — it must
  // be validated against the caller's ACTUAL scope, never taken on faith
  // (convenience-only, never a bearer of access).
  useEffect(() => {
    if (hasNoScope) return
    fetchGlAccounts().then(setGlRef).catch(() => setGlRef([]))
    fetchDepartments(adminViewEnabled)
      .then((data) => {
        setDepartments(data)
        if (!deptResolved) {
          setDepartment(resolveInitialDept(buildDeptHierarchy(data), initialFilter.dept))
          setDeptResolved(true)
        }
      })
      .catch(() => {
        setDepartments([])
        // Even on failure, unblock the grid-load gate below — a broken
        // department list must never leave the grid stuck in "loading"
        // forever (it just loads with department=null, same as a >1-ฝ่าย
        // caller with no auto-select).
        setDeptResolved(true)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [adminViewEnabled, hasNoScope])

  // A10 รออนุมัติ badge (ADR-0016): departments where the caller is the
  // current approver, refetched whenever the planning year changes and
  // after any submit/approve/reject action (ApprovalActionBar's onChanged).
  async function loadPendingApprovals() {
    if (hasNoScope) return
    try {
      const result = await fetchPendingForMe(year)
      setPendingApprovalDepartments(new Set(result.departments))
    } catch {
      setPendingApprovalDepartments(new Set()) // never blocks the page — badge just stays empty
    }
  }

  useEffect(() => {
    loadPendingApprovals()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, hasNoScope])

  /** "+ เพิ่ม Transaction" lock-awareness data fetch. Admin-wide bypasses the
   * lock everywhere else in this component (`row.editable`, subform
   * read-only) — its result would never be consulted (`lockedCostCenters`
   * below stays empty for admin-wide regardless), so skip the round trip
   * entirely, same "never consulted" reasoning as `get_budget_grid`'s own
   * admin_wide skip server-side. Refetched on year change AND after any
   * submit/approve/reject (`handleApprovalChanged` below) — a submit can
   * lock a department immediately. */
  async function loadLockedDepartments() {
    if (hasNoScope || adminViewEnabled) {
      setLockedDepartments(new Set())
      setYearNotOpen(false)
      return
    }
    try {
      const result = await fetchLockedDepartments(year)
      setLockedDepartments(new Set(result.departments))
      setYearNotOpen(result.year_not_open)
    } catch {
      setLockedDepartments(new Set()) // fail-open — never blocks "+ เพิ่ม Transaction" on a fetch error
      setYearNotOpen(false)
    }
  }

  useEffect(() => {
    loadLockedDepartments()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, hasNoScope, adminViewEnabled])

  /** Refreshes both approval-driven caches after a submit/approve/reject —
   * a submit can both change the รออนุมัติ badge list AND lock the
   * department the caller just submitted. */
  function handleApprovalChanged() {
    loadPendingApprovals()
    loadLockedDepartments()
  }

  async function loadGrid() {
    if (hasNoScope) return
    setLoading(true)
    setError(null)
    try {
      const data = await fetchBudgetGrid({ year, department: department ?? undefined, adminViewEnabled })
      setRows(data)
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'โหลดข้อมูลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // Gated on deptResolved so mount fetches the grid exactly ONCE, with
    // the ฝ่าย already decided (auto-selected single ฝ่าย, or null for
    // >1 — resolveInitialDept in the reference-data effect above) —
    // instead of an initial department=null fetch immediately followed by
    // a second fetch once resolution runs a moment later (every single-ฝ่าย
    // filler, ~55% of them, used to eat that redundant fetch + a loading
    // flicker on every mount). `deptResolved` still flips true even when
    // the department fetch itself fails, so this gate can never hang the
    // grid in "loading" forever.
    if (!deptResolved) return
    loadGrid()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, department, adminViewEnabled, deptResolved])

  const fillCostCenters = useMemo(
    () => (isPureAdmin ? [...new Set(departments.map((d) => d.cost_center))] : scope.fillCostCenters),
    [isPureAdmin, departments, scope.fillCostCenters],
  )

  /** cost_center -> department, LOCKED entries only, for every Cost Center
   * "+ เพิ่ม Transaction" can offer — feeds `AddTransactionForm`'s lock
   * check (see `model.lockedCostCenterDepartments`). `lockedDepartments` is
   * already empty for admin-wide (`loadLockedDepartments` above), so no
   * separate admin bypass is needed here. */
  const lockedCostCenters = useMemo(
    () => lockedCostCenterDepartments(fillCostCenters, departments, lockedDepartments),
    [fillCostCenters, departments, lockedDepartments],
  )

  const isFillerOfSelectedDept = department !== null && isFillerOfDepartment(departments, department, scope.fillCostCenters)
  const selectedDeptCostCenterCount = department !== null ? costCentersOfDepartment(departments, department).length : 0
  const canUploadAttachments = adminViewEnabled || isFillerOfSelectedDept

  /** Shared save path for any Pending-layer edit (month cell or remark) —
   * optimistic local replace, `PUT /budget/rows`, then the server-
   * authoritative merge. Per-row status lives in `rowMessages` so one row's
   * failure never blocks another. */
  async function persistRow(key: string, optimistic: BudgetRow) {
    setRows((prev) => prev.map((r) => (rowKey(r.cost_center, r.gl_account) === key ? optimistic : r)))
    setRowMessages((prev) => ({ ...prev, [key]: { kind: 'saving', text: 'กำลังบันทึก…' } }))

    try {
      const payload = buildSavePayload(optimistic, year)
      const saved = await saveRow(payload)
      setRows((prev) => prev.map((r) => (rowKey(r.cost_center, r.gl_account) === key ? mergeSavedRow(r, saved) : r)))
      setRowMessages((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setRowMessages((prev) => ({
          ...prev,
          [key]: { kind: 'error', text: 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น กรุณาโหลดข้อมูลใหม่แล้วลองอีกครั้ง' },
        }))
        await loadGrid()
        return
      }
      const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'บันทึกไม่สำเร็จ'
      setRowMessages((prev) => ({ ...prev, [key]: { kind: 'error', text: message } }))
    }
  }

  async function handleCommitMonth(row: BudgetRow, month: MonthKey, value: number) {
    const optimistic = { ...row, pending: { ...row.pending, [month]: value } }
    optimistic.pending.total_year = Object.keys(optimistic.pending)
      .filter((k) => /^m\d\d$/.test(k))
      .reduce((sum, k) => sum + (optimistic.pending as unknown as Record<string, number>)[k], 0)
    await persistRow(rowKey(row.cost_center, row.gl_account), optimistic)
  }

  /** Remark commit — same whole-row replace contract as a month commit
   * (`buildSavePayload` already carries `pending.remark`); an emptied input
   * normalizes to null. */
  async function handleCommitRemark(row: BudgetRow, remark: string) {
    const optimistic = { ...row, pending: { ...row.pending, remark: remark === '' ? null : remark } }
    await persistRow(rowKey(row.cost_center, row.gl_account), optimistic)
  }

  /** Special-GL cells never edit inline (A8) — clicking "เปิดฟอร์มย่อย"
   * opens the matching A9 editor: Travelling Expense (8 GL, trip-centric)
   * goes to Trip Manager, LOCKED to the clicked row's own accounting side
   * (jakkaritw, 2026-08-04 — final, applies to every user incl. admins: a
   * trip's GLs must match the row the user clicked, offering the other
   * side could only create a mismatch); the other 5 special groups go to
   * DetailSubform. Shared by an existing row's own open button
   * (`handleOpenSpecial`) AND "+ เพิ่ม Transaction" picking a special-GL
   * code (`handleAddTransaction`) — neither needs a pre-existing
   * `pending_budget` row to open the subform, only the (CC, GL) pair. */
  function openSpecialForm(costCenter: string, glAccount: string, glGroup: string, readOnly: boolean) {
    if (glGroup === 'Travelling Expense') {
      const lockedSide = deriveTravelSideFromGl(glAccount)
      if (lockedSide === null) {
        // Defensive only — every GL that reaches here via a Travelling
        // Expense row IS one of the 8 travel GLs, so this never fires in
        // practice. Bail out rather than open a modal with no side to lock.
        console.error(`Travelling Expense row has an unrecognized GL: ${glAccount}`)
        return
      }
      setTripManagerOpenFor({ costCenter, lockedSide, readOnly })
    } else {
      setDetailTarget({ costCenter, glAccount, glGroup, readOnly })
    }
  }

  function handleOpenSpecial(row: BudgetRow, glGroup: string) {
    openSpecialForm(row.cost_center, row.gl_account, glGroup, !row.editable)
  }

  /** "+ เพิ่ม Transaction" — a special-GL pick (Spec B path ข, jakkaritw
   * 2026-08-05) skips `/budget/rows` entirely and opens that GL's own
   * subform directly, exactly like clicking an existing special-GL row's
   * open button: the backend unconditionally refuses to create a
   * special-GL header row through the plain create path
   * (`_save_one_pending_row`: SpecialGlDirectEditError) — the subform's own
   * save lazily creates the `pending_budget` row on its first write, then
   * `onSaved={loadGrid}` picks it up for real. A non-special GL keeps the
   * original create-a-blank-row flow. */
  async function handleAddTransaction(costCenter: string, glAccount: string): Promise<AddResult> {
    const meta = glMetaFor(glAccount, glRef)
    if (meta.is_special) {
      openSpecialForm(costCenter, glAccount, meta.gl_group, false)
      return { ok: true }
    }
    try {
      const saved = await saveRow(buildNewRowPayload(costCenter, glAccount, year))
      const months = Object.fromEntries(
        (['m01', 'm02', 'm03', 'm04', 'm05', 'm06', 'm07', 'm08', 'm09', 'm10', 'm11', 'm12'] as MonthKey[]).map((m) => [
          m,
          saved[m],
        ]),
      )
      const blankLayer = { ...months, total_year: 0 }
      const newRow: BudgetRow = {
        cost_center: costCenter,
        gl_account: glAccount,
        sap: blankLayer as BudgetRow['sap'],
        board: { ...blankLayer, gl_name: null, gl_group: null, c_level: null, division: null, department: null } as BudgetRow['board'],
        pending: {
          ...months,
          total_year: saved.total_year,
          template: saved.template,
          remark: saved.remark,
          gl_name: saved.gl_name,
          gl_group: saved.gl_group,
          c_level: saved.c_level,
          division: saved.division,
          department: saved.department,
          updated_at: saved.updated_at,
        } as BudgetRow['pending'],
        // Derived, not hardcoded (jakkaritw 2026-08-08 bug fix): the create
        // above only ever succeeds for a Cost Center this SAME
        // `lockedCostCenters` answer says is not locked (the Add form's own
        // `validateNewTransaction` check already refused it otherwise) —
        // this stays the honest, self-correcting source of truth rather
        // than a value that merely HAPPENS to always be true today.
        editable: !isCostCenterLocked(costCenter, lockedCostCenters),
      }
      setRows((prev) => [...prev, newRow])
      return { ok: true }
    } catch (err) {
      const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'สร้างรายการไม่สำเร็จ'
      return { ok: false, errorTh: message }
    }
  }

  /** Grid trailing "ลบ" column — deletes a manually-added Pending row
   * (`isDeletableRow`'s eligibility already gated whether the button was
   * even rendered). Thai confirm before an irreversible delete; a 409
   * refetches the grid (the row was changed/removed elsewhere) instead of
   * assuming this client's view is still correct. */
  async function handleDeleteRow(row: BudgetRow) {
    if (!window.confirm(`ลบรายการนี้? (${row.cost_center} · ${row.gl_account})\nลบแล้วเรียกคืนไม่ได้`)) return
    const key = rowKey(row.cost_center, row.gl_account)
    try {
      await deleteRow({
        costCenter: row.cost_center, glAccount: row.gl_account, fiscalYear: year,
        expectedUpdatedAt: row.pending.updated_at ?? '',
      })
      setRows((prev) => prev.filter((r) => rowKey(r.cost_center, r.gl_account) !== key))
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        await loadGrid()
        return
      }
      const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'ลบไม่สำเร็จ'
      setRowMessages((prev) => ({ ...prev, [key]: { kind: 'error', text: message } }))
    }
  }

  // Fullscreen side-effects: lock the page behind the overlay so a wheel
  // scroll moves the grid, not the covered page; Esc as the convenience exit
  // (the ⤡ button is the primary one). Cleanup restores everything,
  // including on an unmount that happens WHILE fullscreen (scope switch,
  // route change) — the same class of bug the drag-listener cleanup in
  // GridTable guards against.
  useEffect(() => {
    if (!isFullscreen) return
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      const tag = (e.target as HTMLElement | null)?.tagName
      // Esc inside a field belongs to that field/dropdown (AddTransactionForm's
      // GL list closes on Esc, GridTable's filter inputs, month-cell inputs).
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      // Esc with a subform/trip modal open belongs to the modal, not the grid.
      if (document.querySelector('.modal-backdrop')) return
      setIsFullscreen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = prevOverflow
      window.removeEventListener('keydown', onKey)
    }
  }, [isFullscreen])

  if (hasNoScope) {
    return (
      <div className="budget-grid">
        <div className="grid-empty no-scope-empty" data-testid="no-scope-empty-state">
          <p className="no-scope-empty-heading">ไม่มีสิทธิ์เข้าถึงระบบงบประมาณ</p>
          {scope.email && <p>บัญชีของคุณ {scope.email} ยังไม่ได้รับสิทธิ์กรอกงบประมาณ</p>}
          <p>
            กรุณาติดต่อ {SCOPE_ACCESS_CONTACT_EMAIL} เพื่อเพิ่มสิทธิ์ที่ไฟล์ {SCOPE_ACCESS_SOURCE_FILE}
            {' '}(SharePoint › Budgeting and Management)
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`budget-grid${isFullscreen ? ' is-fullscreen' : ''}`} data-testid="budget-grid">
      <div className="grid-toolbar">
        <YearPicker year={year} onChange={setYear} />
        <DeptPicker rows={departments} selected={department} onSelect={setDepartment} pendingApprovalDepartments={pendingApprovalDepartments} />
        <AddTransactionForm
          fillCostCenters={fillCostCenters}
          glRef={glRef}
          existingRows={rows}
          onAdd={handleAddTransaction}
          lockedCostCenters={lockedCostCenters}
          yearNotOpen={yearNotOpen}
        />
        {department && (
          <button type="button" className="btn btn-attach" onClick={() => setAttachmentsOpen(true)}>
            แนบไฟล์
          </button>
        )}
        {isDualRoleAdmin && <AdminModeToggle enabled={adminModeOn} onChange={handleAdminModeToggle} />}
        <div className="legend" data-testid="status-legend">
          <span className="legend-item">
            <span className="legend-dot sap" />
            SAP · ใช้จริง ({year - 1})
          </span>
          <span className="legend-item">
            <span className="legend-dot approved" />
            Approved · งบอนุมัติ ({year - 1})
          </span>
          <span className="legend-item">
            <span className="legend-dot pending" />
            Pending · งบรออนุมัติ ({year})
          </span>
        </div>
      </div>

      {/* Admin marker only (jakkaritw 2026-08-04) — the strip used to carry the
          whole provenance sentence + the FX read-out; every word of that now
          lives in the tooltip so the row costs one icon's height. The visible
          text is deliberately just "Admin". */}
      {scope.isAdmin && (
        <div
          className="admin-zone"
          data-testid="admin-zone"
          title={`งบอนุมัติ (Approved) · ทั้งบริษัท · ทั้งปี · ไม่ขึ้นกับตัวกรองปี / ฝ่าย ที่เลือกดู — อ่านอย่างเดียว (read-only) มาจากไฟล์ Excel รายปีใน SharePoint › Budgeting and Management › approved budget · Master FX (USD→THB · FY${year - 1}) แก้ที่ Master Currency (Module 09) เท่านั้น`}
        >
          <svg
            className="admin-zone-ic"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          <span className="admin-zone-title">Admin</span>
        </div>
      )}

      {error && (
        <div className="grid-error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn" onClick={loadGrid}>
            ลองใหม่
          </button>
        </div>
      )}

      {loading && !error && <div className="grid-loading">กำลังโหลดข้อมูลงบประมาณ…</div>}

      {!loading && !error && (
        <GridTable
          rows={rows}
          glRef={glRef}
          onCommitMonth={handleCommitMonth}
          onCommitRemark={handleCommitRemark}
          rowMessages={rowMessages}
          onOpenSpecial={handleOpenSpecial}
          onDeleteRow={handleDeleteRow}
          isFullscreen={isFullscreen}
          onToggleFullscreen={() => setIsFullscreen((v) => !v)}
        />
      )}

      {/* Below the grid, right-aligned — mockup 0002.3 .submit-row sits at
       * the END of <main>, under the table. */}
      {department && (
        <ApprovalActionBar
          department={department}
          fiscalYear={year}
          isFillerOfDept={isFillerOfSelectedDept}
          adminViewEnabled={adminViewEnabled}
          isAdmin={scope.isAdmin}
          rowCount={rows.length}
          costCenterCount={selectedDeptCostCenterCount}
          onChanged={handleApprovalChanged}
        />
      )}

      {detailTarget && (
        <DetailSubform
          costCenter={detailTarget.costCenter}
          glAccount={detailTarget.glAccount}
          glGroup={detailTarget.glGroup}
          glName={glMetaFor(detailTarget.glAccount, glRef).gl_name}
          fiscalYear={year}
          readOnly={detailTarget.readOnly}
          onClose={() => setDetailTarget(null)}
          onSaved={loadGrid}
        />
      )}

      {tripManagerOpenFor && (
        <TripManager
          costCenter={tripManagerOpenFor.costCenter}
          fiscalYear={year}
          lockedSide={tripManagerOpenFor.lockedSide}
          readOnly={tripManagerOpenFor.readOnly}
          onClose={() => setTripManagerOpenFor(null)}
          onSaved={loadGrid}
        />
      )}

      {attachmentsOpen && department && (
        <AttachmentsModal
          department={department}
          fiscalYear={year}
          canUpload={canUploadAttachments}
          onClose={() => setAttachmentsOpen(false)}
        />
      )}
    </div>
  )
}
