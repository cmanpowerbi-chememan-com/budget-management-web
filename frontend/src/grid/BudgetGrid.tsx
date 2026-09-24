import { useEffect, useMemo, useRef, useState } from 'react'
import { AdminModeToggle } from '../admin/AdminModeToggle'
import { useAdminViewToggle } from '../admin/useAdminViewToggle'
import { fetchApprovalStatus, fetchLockedDepartments, fetchPendingDepartments, fetchPendingForMe } from '../api/approval'
import { ApiError, isDepartmentLockedError } from '../api/client'
import { deleteRow, downloadBudgetExport, fetchBudgetGrid, fetchDepartments, fetchGlAccounts, fetchSapCoverage, saveRow } from '../api/budget'
import type { BudgetRow, DepartmentRow, GlAccount, SapCoverage } from '../api/types'
import { costCentersOfDepartment, isFillerOfDepartment } from '../approval/model'
import { ApprovalActionBar } from '../approval/ApprovalActionBar'
import { AttachmentsModal } from '../attachments/AttachmentsModal'
import type { ScopeState } from '../auth/useScope'
import type { DeepLinkFilter } from '../filters/deepLink'
import { confirmDialog } from '../platform/confirm'
import { publishNotice } from '../platform/notice'
import { DetailSubform } from '../subform/DetailSubform'
import { deriveTravelSideFromGl, type TripSide } from '../subform/model'
import { TripManager } from '../subform/TripManager'
import { AddTransactionForm, type AddResult } from './AddTransactionForm'
import { GridTable, type RowMessage } from './GridTable'
import {
  addTransactionBlockedReasonTh, admitRows, buildNewRowPayload, buildSavePayload, emptyGridMessage,
  glMetaFor, mergeSavedRow, sapFreshnessLine, type MonthKey,
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
  // Bug fix (2026-09-16): a Filler's FIRST successful save on an empty
  // department flips the server's can_submit/department_empty verdict, but
  // ApprovalActionBar's own status fetch is keyed only on
  // [department, fiscalYear] -- neither changes on a save, so it kept
  // showing "Draft — not submitted" until a manual reload. Bumped after
  // every successful write that could create the department's first
  // pending_budget row (a month-cell/remark save via persistRow, or any
  // DetailSubform/TripManager save via handleSpecialSaved below) so the bar
  // can refetch its status in place. Never bumped on a failed save.
  const [dataVersion, setDataVersion] = useState(0)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Latest-request guard for `loadGrid` (gate fix round 2, item A) — see
  // that function's own doc comment for why this exists.
  const loadSeqRef = useRef(0)

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
  // "ดาวน์โหลด Excel" (issue #35) — one ฝ่าย's grid as the approved 1-sheet
  // workbook. Own loading/error state, separate from the grid's own
  // `loading`/`error` (a download in flight must never look like the grid
  // itself is reloading).
  const [exportLoading, setExportLoading] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  // Fullscreen overlay (⤢ toggle, jakkaritw-approved 2026-07-31) — lifts the
  // WHOLE grid block (toolbar + legend + both side-tables + Submit bar) into
  // a fixed layer above the nav. State lives HERE, not in GridTable (unlike
  // columnsCollapsed), because the overlay must contain controls that are
  // GridTable's siblings. Deliberately NOT persisted — same policy as
  // compact mode: always starts normal on load.
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [pendingApprovalDepartments, setPendingApprovalDepartments] = useState<Set<string>>(new Set())
  // Admin-mode pill text (jakkaritw, 2026-09-18): department -> "Pending ·
  // <English approver name>". Only ever populated in admin mode (see
  // `loadPendingApprovals` below) -- an approver's own pill stays plain
  // "Pending" (it already means "your turn"; naming the reader to
  // themselves adds nothing), so this stays empty outside admin mode.
  const [pendingApprovalLabels, setPendingApprovalLabels] = useState<Map<string, string>>(new Map())
  // "+ เพิ่ม Transaction" lock-awareness (2026-08-08 bug fix, ADR-0013 UI
  // parity): every one of the CALLER's OWN Fill-scope departments that is
  // currently mid-approval/APPROVED for `year` (`GET
  // /approval/locked-departments`, backed by the exact same
  // `read_model.fetch_locked_departments` the grid's own `row.editable` is
  // built from — one source, cannot drift). Crossed with `departments`
  // (the live CC->department mapping already fetched for the ฝ่าย picker)
  // in `lockedCostCenters` below.
  const [lockedDepartments, setLockedDepartments] = useState<Set<string>>(new Set())
  // Issue #13, decision G (2026-09-17): the fetch above failing must NEVER
  // silently act as though nothing were locked (the old catch reset
  // `lockedDepartments`/`yearNotOpen` to their "open" defaults) — the Add
  // button disables itself with its own Thai reason instead, via this flag
  // (see `AddTransactionForm`'s `lockStatusUnavailable`).
  const [lockedDepartmentsFailed, setLockedDepartmentsFailed] = useState(false)
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
    // Gate fix round 3, item 3: an old-hat `loadGrid` fetch may still be in
    // flight (e.g. the toggle fires mid-load) — bump the sequence NOW so
    // that response, whenever it settles, is dropped as stale rather than
    // landing under the NEW hat's (department=null, then re-resolved) view.
    loadSeqRef.current += 1
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
  // Admin mode (jakkaritw, 2026-09-18): switches the DATA SOURCE to the
  // admin-only company-wide queue (`GET /approval/pending-departments`) so
  // an admin — who is rarely the current approver — still sees every
  // department mid-approval, with the current approver's name; also
  // refetched when `adminViewEnabled` itself toggles (see the effect below).
  async function loadPendingApprovals() {
    if (hasNoScope) return
    if (adminViewEnabled) {
      try {
        const result = await fetchPendingDepartments(year)
        setPendingApprovalDepartments(new Set(result.departments.map((d) => d.department)))
        const labels = new Map<string, string>()
        result.departments.forEach((d) => {
          if (d.current_approver_name) labels.set(d.department, `Pending · ${d.current_approver_name}`)
        })
        setPendingApprovalLabels(labels)
      } catch {
        setPendingApprovalDepartments(new Set()) // never blocks the page — badge just stays empty
        setPendingApprovalLabels(new Map())
      }
      return
    }
    setPendingApprovalLabels(new Map()) // outside admin mode the pill is always plain "Pending"
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
  }, [year, hasNoScope, adminViewEnabled])

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
      setLockedDepartmentsFailed(false)
      return
    }
    try {
      const result = await fetchLockedDepartments(year)
      setLockedDepartments(new Set(result.departments))
      setYearNotOpen(result.year_not_open)
      setLockedDepartmentsFailed(false)
    } catch {
      // Issue #13, decision G: NEVER fall open — leave the last-known
      // `lockedDepartments`/`yearNotOpen` untouched (stale is safer than
      // wrong) and disable "+ เพิ่ม Transaction" via `lockedDepartmentsFailed`
      // instead of pretending the check succeeded and found nothing locked.
      setLockedDepartmentsFailed(true)
    }
  }

  useEffect(() => {
    loadLockedDepartments()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, hasNoScope, adminViewEnabled])

  // SAP freshness chip (ADR-0030 — supersedes the ADR-0026 month mask):
  // `GET /budget/sap-coverage` is auth-only/no-RLS, refetched whenever the
  // planning year changes. A failed read never turns into a page error (the
  // grid itself already has its own loud error state) — but per ADR-0030
  // §3.2 the chip IS the release-blocking safety net for a stale/dead SAP
  // feed, so a failure must WARN, not go silent (H1 gate fix): it renders
  // the same "unknown freshness" wording as a null watermark, via
  // `sapCoverageFailed` below. `sapCoverage` stays `null` only for the very
  // first render, before the first fetch has resolved either way — that
  // moment says nothing, same as before.
  const [sapCoverage, setSapCoverage] = useState<SapCoverage | null>(null)
  const [sapCoverageFailed, setSapCoverageFailed] = useState(false)
  useEffect(() => {
    if (hasNoScope) return
    fetchSapCoverage(year)
      .then((coverage) => {
        setSapCoverage(coverage)
        setSapCoverageFailed(false)
      })
      .catch(() => {
        setSapCoverage(null)
        setSapCoverageFailed(true)
      })
  }, [year, hasNoScope])

  /** Refreshes everything a submit/approve/reject/override can invalidate —
   * the รออนุมัติ badge list, the "+ เพิ่ม Transaction" lock-awareness
   * cache, AND the grid's own rows (UAT-34, 2026-09-09: `row.editable`
   * lives on each fetched row, so without this refetch the SAME page kept
   * showing editable month inputs right after a successful Submit until a
   * manual reload — a reject unlocks the same way, through this same
   * refetch). */
  function handleApprovalChanged() {
    loadPendingApprovals()
    loadLockedDepartments()
    loadGridRef.current()
  }

  /** Latest-request guard (gate fix round 2, item A): `loadGrid` fires again
   * on every year/department/adminViewEnabled change, but nothing ever
   * cancelled the PREVIOUS in-flight fetch — a late response for a ฝ่าย/year
   * the user has since navigated away from used to overwrite `rows` with
   * stale data (shown under the NEW heading) and could leave `loading`
   * cleared while a newer request was still pending, silently re-enabling
   * "ดาวน์โหลด Excel" against the wrong ฝ่าย. Each call claims the next
   * sequence number; only the call that still holds the LATEST number when
   * its fetch settles is allowed to touch `rows`/`error`/`loading` — an
   * out-of-order (or simply superseded) response is dropped entirely. */
  async function loadGrid() {
    if (hasNoScope) return
    const seq = ++loadSeqRef.current
    setLoading(true)
    setError(null)
    try {
      const data = await fetchBudgetGrid({ year, department: department ?? undefined, adminViewEnabled })
      if (seq !== loadSeqRef.current) return
      setRows(admitRows(data, department))
    } catch (err) {
      if (seq !== loadSeqRef.current) return
      const message = err instanceof ApiError ? err.message : 'โหลดข้อมูลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง'
      setError(message)
    } finally {
      if (seq === loadSeqRef.current) setLoading(false)
    }
  }

  // Latest-CLOSURE guard (gate fix round 3, item 1 — a HIGH regression the
  // round-2 seq guard introduced): `loadGrid` is a plain function redefined
  // every render, closing over THAT render's year/department. The seq
  // guard above only orders RESPONSES against each other — it says nothing
  // about which render's `loadGrid` a DEFERRED completion handler
  // (`persistRow`'s 409 branch, `refreshAfterLockChange`,
  // `handleApprovalChanged`, `handleSpecialSaved`, `handleDeleteRow`'s 409
  // branch — none of them run inside the grid-load effect itself) is still
  // holding from back when it started. If the ฝ่าย switches while one of
  // those is in flight, its own stale closure still calls the OLD
  // `loadGrid` (old year/department baked in) — and because it only
  // *starts* fetching later than the legitimate reload, it claims a HIGHER
  // seq number and wins, so the stale ฝ่าย's rows land under the NEW
  // heading. `loadGridRef` is synced on every render (no deps array — same
  // pattern as `refreshAfterLockChangeRef` below) so it always points at
  // the FRESHEST `loadGrid`; every one of those deferred call sites goes
  // through `loadGridRef.current()` instead of calling `loadGrid()`
  // directly. `loadGrid` itself, and the grid-load effect that calls it
  // directly, are UNCHANGED — do NOT make `loadGrid` read
  // department/year from refs instead: `departmentRef`/`adminViewEnabledRef`
  // below are synced by effects declared AFTER the grid-load effect, so
  // `loadGrid` reading them would lag one render behind the effect that
  // calls it.
  const loadGridRef = useRef(loadGrid)
  useEffect(() => {
    loadGridRef.current = loadGrid
  })

  /** `onSaved` for DetailSubform / TripManager — a special-GL detail line or
   * a trip's manual line lazily creates the (CC, GL)'s `pending_budget`
   * parent row on ITS OWN first successful write (see `handleAddTransaction`
   * doc comment above), so this can ALSO be a department's first-ever row —
   * same reason `persistRow` bumps `dataVersion`, applied to this save path
   * too. Both children already only call `onSaved` after a genuinely
   * successful write (never on a failed save or a plain close). */
  function handleSpecialSaved() {
    setDataVersion((v) => v + 1)
    loadGridRef.current()
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

  /** Issue #13, decision F (2026-09-17): "+ เพิ่ม Transaction" now offers
   * ONLY the Cost Centers of the ฝ่าย on screen — a Filler with Cost Centers
   * in 2+ ฝ่าย (38 of 71) must switch the picker to add to the OTHER one,
   * never have both mixed into a single Add form (the G1 bug this whole
   * change exists to close). Reuses `approval/model.costCentersOfDepartment`
   * (the caller's own live `GET /scope/departments` rows) crossed with the
   * caller's Fill scope. */
  const fillCostCentersOfSelectedDept = useMemo(() => {
    if (!department) return []
    const fillSet = new Set(fillCostCenters)
    return costCentersOfDepartment(departments, department).filter((cc) => fillSet.has(cc))
  }, [department, departments, fillCostCenters])

  // `lockedDepartments` is already empty for admin-wide (`loadLockedDepartments`
  // above), so `selectedDepartmentLocked` is always false there — no separate
  // admin bypass needed here.
  const selectedDepartmentLocked = department !== null && lockedDepartments.has(department)

  const isFillerOfSelectedDept = department !== null && isFillerOfDepartment(departments, department, scope.fillCostCenters)
  const canUploadAttachments = adminViewEnabled || isFillerOfSelectedDept

  /** Issue #32: the SAME reason `<AddTransactionForm>` resolves for its own
   * disabled state — computed from the exact inputs already passed to it
   * (`fillCostCentersOfSelectedDept`, not `isFillerOfSelectedDept`/
   * `scope.fillCostCenters` above, since a pure admin's Add button bypasses
   * via the former, not the latter — using the wrong one here would make
   * the empty-grid hint disagree with the Add button for that caller). Fed
   * into `emptyGridMessage` below; no new fetch, no new state. */
  const addBlockedReasonTh = addTransactionBlockedReasonTh({
    yearNotOpen,
    departmentUnknown: deptResolved && department === null,
    lockStatusUnavailable: lockedDepartmentsFailed,
    departmentLocked: selectedDepartmentLocked,
    department,
    hasFillCostCenters: fillCostCentersOfSelectedDept.length > 0,
  })
  const emptyState = emptyGridMessage({
    fiscalYear: year, department, canAddTransaction: addBlockedReasonTh === null, addBlockedReasonTh,
  })

  /** Issue #13, decision H (2026-09-17): the ONE reaction to "the server
   * says this write is now department-locked" — shared by `persistRow` and
   * `handleDeleteRow` below (called inline) and by `onDepartmentLocked`
   * passed down to `DetailSubform`/`TripManager` (called via their own
   * save/delete catch). Bumps `dataVersion` (so `ApprovalActionBar`
   * refreshes its Submit/locked-note state too), reloads the grid so its
   * rows match the server, and refreshes `lockedDepartments` too (same
   * bundle `handleApprovalChanged` already reloads after a submit/approve/
   * reject) so "+ เพิ่ม Transaction" locks itself in the same beat, not just
   * the grid cells. Also the target of decision I's focus-revalidation (a
   * status change detected proactively gets the exact same remedy as one
   * discovered via a refused write). */
  function refreshAfterLockChange() {
    setDataVersion((v) => v + 1)
    loadGridRef.current()
    loadLockedDepartments()
  }

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
      setDataVersion((v) => v + 1)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setRowMessages((prev) => ({
          ...prev,
          [key]: { kind: 'error', text: 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น กรุณาโหลดข้อมูลใหม่แล้วลองอีกครั้ง' },
        }))
        await loadGridRef.current()
        return
      }
      // UAT-34: a department can be locked by someone ELSE's Submit between
      // this cell's last render and this blur — same "trust the server,
      // refetch" contract as the 409 branch above (reverts the optimistic
      // value AND flips row.editable off), except the message IS the
      // server's own Thai reason (messageForStatus's department-locked
      // mapping), not a generic conflict line.
      if (err instanceof ApiError && isDepartmentLockedError(err)) {
        setRowMessages((prev) => ({ ...prev, [key]: { kind: 'error', text: err.message } }))
        refreshAfterLockChange()
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

  /** "ดาวน์โหลด Excel" (issue #35) — downloads the SAME rows on screen
   * (current year / ฝ่าย / admin flag) as the approved 1-sheet workbook,
   * via a blob + object-URL anchor (never `showSaveFilePicker` — dead on
   * Edge for this app, files land in Downloads like any browser download). */
  async function handleExportDownload() {
    if (!department) return
    setExportLoading(true)
    setExportError(null)
    try {
      const { blob, filename } = await downloadBudgetExport({ year, department, adminViewEnabled })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename ?? `budget_FY${year}_export.xlsx`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : 'ดาวน์โหลดไฟล์ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง')
    } finally {
      setExportLoading(false)
    }
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
      // Issue #13, decision F/G5 (2026-09-17): derives readOnly from the
      // SELECTED ฝ่าย's own lock state — was a literal `false`, so a special
      // GL picked from the Add form always opened a fully editable subform
      // even while the ฝ่าย on screen was locked (the row path just below,
      // `handleOpenSpecial`, already used `!row.editable` correctly; only
      // this Add-form path had the bug).
      openSpecialForm(costCenter, glAccount, meta.gl_group, selectedDepartmentLocked)
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
        // Issue #13, decision E (2026-09-17): taken straight from the
        // server's own save response, never derived client-side — was
        // `!isCostCenterLocked(costCenter, lockedCostCenters)` (removed),
        // which answered "is this Cost Center's ฝ่าย locked" but never
        // checked whether the row actually belongs to the ฝ่าย ON SCREEN
        // (the G1 bug: a Filler with 2 ฝ่าย could add to their OTHER, open
        // ฝ่าย while looking at a locked one, and this line would compute
        // `editable: true` for a row about to be admitted under the wrong
        // heading). `admitRows` below is what actually closes that gap.
        editable: saved.editable,
        department: saved.department,
        lock_reason: saved.lock_reason,
      }
      // Issue #13, decision E: the ONE admission point — a row whose
      // department does not match the ฝ่าย on screen is never appended.
      // Defensive only: `validateNewTransaction` (via `AddTransactionForm`)
      // already rejects a Cost Center outside the selected ฝ่าย before this
      // is ever called, so `saved.department` should always match `department`
      // in practice; this is the backstop for the rare case it doesn't
      // (e.g. a live CC->ฝ่าย remap landing between the form opening and the
      // save completing).
      let admitted = true
      setRows((prev) => {
        const next = admitRows([...prev, newRow], department)
        admitted = next.length > prev.length
        return next
      })
      if (!admitted) {
        publishNotice(`บันทึกไปที่ฝ่าย "${saved.department ?? '-'}" แล้ว สลับฝ่ายเพื่อดู`)
      }
      // Same reason persistRow / handleSpecialSaved bump dataVersion: a
      // non-special GL picked here can ALSO be the department's first-ever
      // row, so the Submit button must not stay stuck on a stale department_empty.
      setDataVersion((v) => v + 1)
      return { ok: true }
    } catch (err) {
      // Issue #13 (2026-09-19): this was the last write path without a
      // department-locked branch — persistRow, handleDeleteRow, and both
      // DetailSubform/TripManager saves already have one. Without it, a
      // department locked between the Add form opening and this save
      // landing fell through to the generic message below, which appends
      // the raw English backend detail in brackets (the leak
      // BudgetGrid.test.tsx already asserts against elsewhere), and never
      // called refreshAfterLockChange, so the grid stayed unlocked and the
      // Add button kept inviting retries. Mirrors handleDeleteRow's branch:
      // Thai message only, shared refresh. No rowMessages update here —
      // unlike a row edit/delete, there is no existing row key to attach a
      // message to; the Thai reason goes back through errorTh instead, same
      // as the generic branch below.
      if (err instanceof ApiError && isDepartmentLockedError(err)) {
        refreshAfterLockChange()
        return { ok: false, errorTh: err.message }
      }
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
    if (!(await confirmDialog(`ลบรายการนี้? (${row.cost_center} · ${row.gl_account})\nลบแล้วเรียกคืนไม่ได้`, { danger: true, confirmLabel: 'ลบ' }))) return
    const key = rowKey(row.cost_center, row.gl_account)
    try {
      await deleteRow({
        costCenter: row.cost_center, glAccount: row.gl_account, fiscalYear: year,
        expectedUpdatedAt: row.pending.updated_at ?? '',
      })
      setRows((prev) => prev.filter((r) => rowKey(r.cost_center, r.gl_account) !== key))
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        await loadGridRef.current()
        return
      }
      // Issue #13, decision H: department-locked refused the same way as a
      // save (Thai message only, shared refresh) — this delete path had no
      // such branch before, unlike persistRow's.
      if (err instanceof ApiError && isDepartmentLockedError(err)) {
        setRowMessages((prev) => ({ ...prev, [key]: { kind: 'error', text: err.message } }))
        refreshAfterLockChange()
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

  // Issue #13, decision I (2026-09-17): revalidate the selected ฝ่าย's lock
  // state on tab focus/visibility ONLY — no polling, no interval. A tab left
  // open before a submit (by this user, another tab, another device, or a
  // co-Filler) must lock itself within one focus change, not never. Refs
  // (not effect deps) carry `department`/`lockedDepartments` so the two
  // listeners are attached exactly ONCE per mount, not re-attached on every
  // state change — and `inFlight` keeps this to exactly ONE
  // `GET /approval/status` call per focus/visibility event (a prior change
  // elsewhere in this app once produced ~240 status calls per grid by
  // accident; this must never repeat that).
  const departmentRef = useRef(department)
  const lockedDepartmentsRef = useRef(lockedDepartments)
  // Gate 06/07/08 HIGH-1 (2026-09-17): `refreshAfterLockChange` (and the
  // `loadGrid`/`loadLockedDepartments` it calls) is a plain function
  // redefined every render, but this effect only re-attaches on
  // `[hasNoScope, year]` — so calling it directly used to run whichever
  // `refreshAfterLockChange` existed at MOUNT, when `department` was still
  // `null` (resolved later, via the departments fetch's `.then`). That stale
  // closure's `loadGrid()` fetched with no department filter and
  // `admitRows(data, null)` admitted every See-scope row into the ฝ่าย on
  // screen. Same "latest ref" fix as `departmentRef` above, except synced on
  // every render — a plain function has no single value to key an effect's
  // deps on, so the sync effect below intentionally has no deps array.
  const refreshAfterLockChangeRef = useRef(refreshAfterLockChange)
  // Gate MED-1: admin-wide never locks (ADR-0012), but `GET /approval/status`
  // is caller-agnostic — without this, an admin viewing any mid-approval/
  // APPROVED ฝ่าย got a spurious mismatch (nothing is ever in
  // `lockedDepartments` for admin-wide) and a reload on every focus.
  const adminViewEnabledRef = useRef(adminViewEnabled)
  useEffect(() => {
    departmentRef.current = department
  }, [department])
  useEffect(() => {
    lockedDepartmentsRef.current = lockedDepartments
  }, [lockedDepartments])
  useEffect(() => {
    refreshAfterLockChangeRef.current = refreshAfterLockChange
  })
  useEffect(() => {
    adminViewEnabledRef.current = adminViewEnabled
  }, [adminViewEnabled])
  useEffect(() => {
    if (hasNoScope) return
    let inFlight = false
    async function revalidate() {
      if (adminViewEnabledRef.current) return
      const dept = departmentRef.current
      if (!dept || inFlight) return
      inFlight = true
      try {
        const status = await fetchApprovalStatus(dept, year)
        if (status.locked !== lockedDepartmentsRef.current.has(dept)) {
          refreshAfterLockChangeRef.current()
        }
      } catch {
        // Best-effort background check — a failed revalidation just tries
        // again on the next focus/visibility event, never blocks the page.
      } finally {
        inFlight = false
      }
    }
    function onVisibility() {
      if (document.visibilityState === 'visible') revalidate()
    }
    window.addEventListener('focus', revalidate)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('focus', revalidate)
      document.removeEventListener('visibilitychange', onVisibility)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasNoScope, year])

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

  // SAP freshness suffix for the legend chip (ADR-0030 §3.2). `null` ONLY
  // for the very first render, before the first fetch has resolved either
  // way — that moment says nothing extra, same as before this feature
  // existed. A FAILED fetch (`sapCoverageFailed`) is a distinct, non-null
  // state that must warn (H1 gate fix) — it reuses the exact "unknown
  // freshness" wording `sapFreshnessLine` already produces for a null
  // watermark, rather than inventing a second string for the same meaning
  // ("we don't know how fresh this is"). `isWarn` comes back as DATA on the
  // result (L1 gate fix) — the frontend never re-derives staleness by
  // string-sniffing `text` for `⚠`, and never computes staleness itself
  // (ADR-0030).
  const sapFreshness = sapCoverage
    ? sapFreshnessLine(sapCoverage)
    : sapCoverageFailed
      ? sapFreshnessLine({ fiscal_year: year - 1, watermark_date: null, days_behind: null, is_stale: true })
      : null
  const isSapStale = sapFreshness?.isWarn ?? false

  return (
    <div className={`budget-grid${isFullscreen ? ' is-fullscreen' : ''}`} data-testid="budget-grid">
      <div className="grid-toolbar">
        <YearPicker year={year} onChange={setYear} />
        <DeptPicker
          rows={departments}
          selected={department}
          onSelect={setDepartment}
          pendingApprovalDepartments={pendingApprovalDepartments}
          pendingLabels={pendingApprovalLabels}
        />
        <AddTransactionForm
          fillCostCenters={fillCostCentersOfSelectedDept}
          glRef={glRef}
          existingRows={rows}
          onAdd={handleAddTransaction}
          yearNotOpen={yearNotOpen}
          selectedDepartment={department}
          departmentLocked={selectedDepartmentLocked}
          departmentUnknown={deptResolved && department === null}
          lockStatusUnavailable={lockedDepartmentsFailed}
          departments={departments}
          isAdmin={scope.isAdmin}
        />
        {department && (
          <button type="button" className="btn btn-attach" onClick={() => setAttachmentsOpen(true)}>
            แนบไฟล์
          </button>
        )}
        {department && (
          <button
            type="button"
            className="btn btn-download"
            onClick={handleExportDownload}
            // `rows` keeps the PREVIOUS ฝ่าย/year's data during a reload
            // (`loadGrid` never clears it before fetching) — `loading`/
            // `error` must ALSO gate this button, or a refetch for a
            // different ฝ่าย (or one that fails) leaves stale rows behind
            // that would download the wrong data (gate fix round, issue #35).
            disabled={exportLoading || loading || error !== null || rows.length === 0}
          >
            {exportLoading ? 'กำลังสร้างไฟล์…' : 'ดาวน์โหลด Excel'}
          </button>
        )}
        {isDualRoleAdmin && <AdminModeToggle enabled={adminModeOn} onChange={handleAdminModeToggle} />}
        <div className="legend-block">
          <div className="legend" data-testid="status-legend">
            <span className="legend-item">
              <span className="legend-dot sap" />
              SAP · ใช้จริง ({year - 1})
              {sapFreshness && (
                <span
                  className={`sap-freshness${isSapStale ? ' sap-freshness-warn' : ''}`}
                  data-testid="sap-freshness"
                >
                  {' '}· {sapFreshness.text}
                </span>
              )}
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
        {/* jakkaritw 2026-09-21: moved OUT of .legend-block (which used to own
            both the legend chips and this note, right-aligned as one block)
            into .grid-toolbar directly, so it can sit at the toolbar's own
            LEFT edge instead of trailing the legend on the right. Direct
            .grid-toolbar child + CSS `flex-basis: 100%` forces it onto its
            own full-width row; `order` pins that row last regardless of DOM
            position, so it never moves the picker/Add/แนบไฟล์/admin controls
            before it. States the PENDING_AMOUNT_ROUND_TO rule (model.ts) up
            front so the filler is not surprised when a typed 146 commits as
            100 — the rounding itself is silent by design (no toast). */}
        <p className="legend-note" data-testid="pending-rounding-note">
          <strong>หมายเหตุ:</strong> กรอกได้ตั้งแต่ <strong>100</strong> ขึ้นไป
          {' '}โดยระบบจะปรับตัวเลข 2 หลักสุดท้ายเป็น <strong>00</strong> โดยอัตโนมัติ
        </p>
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

      {exportError && (
        <div className="grid-error" role="alert">
          <span>{exportError}</span>
          <button type="button" className="btn" onClick={() => setExportError(null)}>
            ปิด
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
          emptyState={emptyState}
        />
      )}

      {/* Below the grid, right-aligned — mockup 0002.3 .submit-row sits at
       * the END of <main>, under the table. */}
      {department && (
        <ApprovalActionBar
          department={department}
          fiscalYear={year}
          dataVersion={dataVersion}
          isFillerOfDept={isFillerOfSelectedDept}
          adminViewEnabled={adminViewEnabled}
          isAdmin={scope.isAdmin}
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
          onSaved={handleSpecialSaved}
          onDepartmentLocked={() => {
            setDetailTarget((prev) => (prev ? { ...prev, readOnly: true } : prev))
            refreshAfterLockChange()
          }}
        />
      )}

      {tripManagerOpenFor && (
        <TripManager
          costCenter={tripManagerOpenFor.costCenter}
          fiscalYear={year}
          lockedSide={tripManagerOpenFor.lockedSide}
          readOnly={tripManagerOpenFor.readOnly}
          onClose={() => setTripManagerOpenFor(null)}
          onSaved={handleSpecialSaved}
          onDepartmentLocked={() => {
            setTripManagerOpenFor((prev) => (prev ? { ...prev, readOnly: true } : prev))
            refreshAfterLockChange()
          }}
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
