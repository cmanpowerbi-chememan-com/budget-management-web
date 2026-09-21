import { useState } from 'react'
import type { BudgetRow, DepartmentRow, GlAccount } from '../api/types'
import { addTransactionBlockedReasonTh, isGlPickableForCostCenter, validateNewTransaction } from './model'

export interface AddResult {
  ok: boolean
  errorTh?: string
}

export interface AddTransactionFormProps {
  /** Issue #32 (2026-09-21): an EMPTY array (the caller has no Fill Cost
   * Center in the ฝ่าย on screen at all) now disables the button too, with
   * its own Thai reason (`noFillCostCentersAddReasonTh`) — was previously
   * left enabled with nothing pickable, a dead-end open form. */
  fillCostCenters: string[]
  glRef: GlAccount[]
  existingRows: BudgetRow[]
  /** Owned by the parent (`BudgetGrid`) so this component never calls the API
   * directly. For a plain GL: creates the blank Pending row (PUT
   * /budget/rows, expected_updated_at=null) and resolves `{ok:false,
   * errorTh}` on a server-side rejection (e.g. a 409 raced by another
   * Filler) instead of throwing, so the form can show it inline without a
   * try/catch at the call site. For a special-GL pick (Spec B path ข,
   * jakkaritw 2026-08-05): skips the create call entirely and opens that
   * GL's own subform directly — always resolves `{ok:true}`. */
  onAdd: (costCenter: string, glAccount: string) => Promise<AddResult>
  /** `true` when the whole fiscal_year is NOT_OPEN (2026-08-08 3-state
   * extension) — from `GET /approval/locked-departments`'s `year_not_open`.
   * A year-wide lock takes precedence over every other disabled reason
   * below. Optional/defaults to `false` — "the year is open", the
   * pre-existing behavior. */
  yearNotOpen?: boolean
  /** Issue #13, decision 1 (2026-09-17): the ฝ่าย this form is scoped to —
   * `fillCostCenters` above is expected to ALREADY be narrowed to this
   * ฝ่าย's own Cost Centers by the caller (`BudgetGrid`, via
   * `approval/model.costCentersOfDepartment`). Used here only to name the
   * ฝ่าย in the locked-reason message. Optional/defaults to `null`. */
  selectedDepartment?: string | null
  /** Issue #13, decision 1: `true` when `selectedDepartment` is currently
   * mid-approval/APPROVED — replaces the old per-Cost-Center
   * `lockedCostCenters` map now that the form only ever shows ONE ฝ่าย's
   * Cost Centers at a time. jakkaritw's decision (2026-08-08, reaffirmed
   * 2026-09-17): keep the button VISIBLE, never hidden — disable it and
   * show the reason instead. Optional/defaults to `false`. */
  departmentLocked?: boolean
  /** Issue #13, decision 1/G: `true` when no ฝ่าย is selected/known — either
   * nothing has been picked yet, or `GET /scope/departments` failed. The
   * button disables with a distinct Thai reason rather than silently
   * falling open and offering every Fill Cost Center regardless of ฝ่าย.
   * Optional/defaults to `false`. */
  departmentUnknown?: boolean
  /** Issue #13, decision G: `true` when the lock-status fetch itself
   * (`GET /approval/locked-departments`) failed — disables the button with
   * its own Thai reason instead of assuming "nothing is locked".
   * Optional/defaults to `false`. */
  lockStatusUnavailable?: boolean
  /** One row per Cost Center in the caller's scope (`GET /scope/departments`,
   * already fetched by `BudgetGrid`) — used only for the Issue #13 ฝ่าย-
   * mismatch check inside `validateNewTransaction`. The GL rule
   * (`CC_RESTRICTED_GLS`) is keyed on the Cost Center directly and does not
   * read this list. Optional/defaults to `[]`. */
  departments?: DepartmentRow[]
  /** Admins pick any GL on any Cost Center — they bypass `CC_RESTRICTED_GLS`.
   * Optional/defaults to `false`. */
  isAdmin?: boolean
}

/** "+ เพิ่ม transaction" — picks a Cost Center + a GL code (Fill scope
 * only; special-GL codes ARE pickable too, Spec B path ข, jakkaritw
 * 2026-08-05 — routes straight into that GL's own subform, same as any
 * special-GL row), then either creates a new blank Pending row (ADR-0010:
 * the manual door for a non-special (CC, GL) with no SAP actual yet) or
 * opens the subform (special GL — see `onAdd` doc). BOTH pickers are the
 * SAME searchable-combobox pattern (a plain <select> was unusable — 130+ GL
 * rows, 400+ Fill-scope cost centers): type to filter, Enter picks the
 * first match, Esc closes, click also picks. */
export function AddTransactionForm({
  fillCostCenters, glRef, existingRows, onAdd, yearNotOpen = false,
  selectedDepartment = null, departmentLocked = false, departmentUnknown = false, lockStatusUnavailable = false,
  departments = [], isAdmin = false,
}: AddTransactionFormProps) {
  const [open, setOpen] = useState(false)
  const [costCenter, setCostCenter] = useState('')
  const [ccSearch, setCcSearch] = useState('')
  const [ccListOpen, setCcListOpen] = useState(false)
  const [glAccount, setGlAccount] = useState('')
  const [glSearch, setGlSearch] = useState('')
  const [glListOpen, setGlListOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const ccQuery = ccSearch.trim().toLowerCase()
  // Cost centers are bare codes (no name/department string available in
  // this component's props) — filter by substring on the code itself.
  const filteredCcs = ccQuery ? fillCostCenters.filter((cc) => cc.toLowerCase().includes(ccQuery)) : fillCostCenters

  const selectedGl = glRef.find((g) => g.gl_code === glAccount)

  /** Every path that changes the Cost Center goes through here — picking one
   * from the list, and typing free text (which un-picks it). A GL the new Cost
   * Center may not use is dropped on the spot: otherwise a user could pick the
   * Talent & Culture cost center + the seminar GL, switch to another cost
   * center, and save the exact combination the rule forbids. */
  function changeCostCenter(cc: string) {
    setCostCenter(cc)
    if (selectedGl && !isGlPickableForCostCenter(selectedGl, cc, isAdmin)) {
      setGlAccount('')
      setGlSearch('')
    }
  }

  function pickCc(cc: string) {
    changeCostCenter(cc)
    setCcSearch(cc)
    setCcListOpen(false)
  }

  const query = glSearch.trim().toLowerCase()
  // Eligibility BEFORE the search filter, so a GL this Cost Center may not
  // budget for cannot be typed back into view either.
  const pickableGls = glRef.filter((g) => isGlPickableForCostCenter(g, costCenter, isAdmin))
  // Match code, name AND group — the label shows only name, but users also
  // search by group (e.g. "office" for the Office Expenses GLs).
  const filteredGls = query
    ? pickableGls.filter((g) => `${g.gl_code} ${g.gl_name ?? ''} ${g.gl_group}`.toLowerCase().includes(query))
    : pickableGls

  function glLabel(g: GlAccount): string {
    return `${g.gl_code} — ${g.gl_name ?? g.gl_group}${g.edit_by === 'admin' ? ' (เฉพาะแอดมิน)' : ''}`
  }

  function pickGl(g: GlAccount) {
    setGlAccount(g.gl_code)
    setGlSearch(glLabel(g))
    setGlListOpen(false)
  }

  function reset() {
    setOpen(false)
    setCostCenter('')
    setCcSearch('')
    setCcListOpen(false)
    setGlAccount('')
    setGlSearch('')
    setGlListOpen(false)
    setError(null)
    setBusy(false)
  }

  async function handleSubmit() {
    const validation = validateNewTransaction({
      costCenter, glAccount, fillCostCenters, glRef, existingRows, selectedDepartment, yearNotOpen, departments, isAdmin,
    })
    if (!validation.ok) {
      setError(validation.errorTh ?? 'ข้อมูลไม่ถูกต้อง')
      return
    }
    setBusy(true)
    setError(null)
    const result = await onAdd(costCenter, glAccount)
    setBusy(false)
    if (result.ok) {
      reset()
    } else {
      setError(result.errorTh ?? 'สร้างรายการไม่สำเร็จ กรุณาลองใหม่')
    }
  }

  // jakkaritw's decision (2026-08-08, reaffirmed 2026-09-17 issue #13): the
  // button stays VISIBLE (never hidden silently) but non-actionable, with
  // the Thai reason shown right beside it — same "say why on screen" tone as
  // the subform's own 🔒 ดูรายละเอียด lock affordance. Precedence (issue #32
  // extended this with a 5th, lowest-priority reason — see
  // `addTransactionBlockedReasonTh`'s own doc in model.ts, the ONE place
  // this chain is defined, shared with the empty-grid message so the two
  // surfaces can never disagree about the same state).
  const disabledReason = addTransactionBlockedReasonTh({
    yearNotOpen, departmentUnknown, lockStatusUnavailable, departmentLocked,
    department: selectedDepartment, hasFillCostCenters: fillCostCenters.length > 0,
  })
  const disabled = disabledReason !== null

  if (!open) {
    return (
      <div className="add-txn-trigger">
        <button type="button" className="btn btn-add" onClick={() => setOpen(true)} disabled={disabled}>
          + เพิ่ม Transaction
        </button>
        {disabledReason && <span className="act-status">{disabledReason}</span>}
      </div>
    )
  }

  return (
    <div className="add-txn-form">
      <label>
        Cost Center
        <div className="gl-combo">
          <input
            aria-label="Cost Center"
            className="gl-combo-input"
            placeholder="— เลือก Cost Center —"
            value={ccListOpen ? ccSearch : costCenter || ccSearch}
            onFocus={() => {
              setCcListOpen(true)
              setCcSearch('')
            }}
            onChange={(e) => {
              // Free text is never a selection by itself — the CC only
              // counts once the user picks it from the filtered list.
              setCcSearch(e.target.value)
              changeCostCenter('')
            }}
            onBlur={() => setCcListOpen(false)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setCcListOpen(false)
              if (e.key === 'Enter' && ccListOpen && filteredCcs.length > 0) {
                e.preventDefault()
                pickCc(filteredCcs[0])
              }
            }}
          />
          {ccListOpen && (
            <div className="gl-combo-list" role="listbox" aria-label="ตัวเลือก Cost Center">
              {filteredCcs.length === 0 && <div className="gl-combo-empty">ไม่พบ Cost Center ที่ค้นหา</div>}
              {filteredCcs.map((cc) => (
                <button
                  key={cc}
                  type="button"
                  role="option"
                  aria-selected={cc === costCenter}
                  className="gl-combo-option"
                  // preventDefault keeps input focus — otherwise blur would
                  // close the list before the click lands.
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pickCc(cc)}
                >
                  {cc}
                </button>
              ))}
            </div>
          )}
        </div>
      </label>
      <label>
        GL Code
        <div className="gl-combo">
          <input
            aria-label="GL Code"
            className="gl-combo-input"
            placeholder="— เลือก GL Code —"
            value={glListOpen ? glSearch : selectedGl ? glLabel(selectedGl) : glSearch}
            onFocus={() => {
              setGlListOpen(true)
              setGlSearch('')
            }}
            onChange={(e) => {
              // Free text is never a selection by itself — the GL only counts
              // once the user picks it from the filtered list.
              setGlSearch(e.target.value)
              setGlAccount('')
            }}
            onBlur={() => setGlListOpen(false)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setGlListOpen(false)
              if (e.key === 'Enter' && glListOpen && filteredGls.length > 0) {
                e.preventDefault()
                pickGl(filteredGls[0])
              }
            }}
          />
          {glListOpen && (
            <div className="gl-combo-list" role="listbox" aria-label="ตัวเลือก GL Code">
              {filteredGls.length === 0 && (
                <div className="gl-combo-empty">ไม่พบ GL Code ที่ค้นหา</div>
              )}
              {filteredGls.map((g) => (
                <button
                  key={g.gl_code}
                  type="button"
                  role="option"
                  aria-selected={g.gl_code === glAccount}
                  className="gl-combo-option"
                  // preventDefault keeps input focus — otherwise blur would
                  // close the list before the click lands.
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pickGl(g)}
                >
                  {glLabel(g)}
                </button>
              ))}
            </div>
          )}
        </div>
      </label>
      {error && <div className="add-txn-error">{error}</div>}
      <div className="add-txn-actions">
        <button type="button" className="btn" onClick={reset} disabled={busy}>
          ยกเลิก
        </button>
        <button type="button" className="btn btn-export" onClick={handleSubmit} disabled={busy}>
          บันทึก
        </button>
      </div>
    </div>
  )
}
