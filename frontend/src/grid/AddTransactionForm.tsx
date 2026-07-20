import { useState } from 'react'
import type { BudgetRow, GlAccount } from '../api/types'
import { validateNewTransaction } from './model'

export interface AddResult {
  ok: boolean
  errorTh?: string
}

export interface AddTransactionFormProps {
  fillCostCenters: string[]
  glRef: GlAccount[]
  existingRows: BudgetRow[]
  /** Performs the actual create (PUT /budget/rows, expected_updated_at=null)
   * — owned by the parent (`BudgetGrid`) so this component never calls the
   * API directly. Resolves `{ok:false, errorTh}` on a server-side rejection
   * (e.g. a 409 raced by another Filler) instead of throwing, so the form
   * can show it inline without a try/catch at the call site. */
  onAdd: (costCenter: string, glAccount: string) => Promise<AddResult>
}

/** "+ เพิ่ม transaction" — picks a Cost Center (Fill scope only) + a
 * non-special GL, then creates a new blank Pending row (ADR-0010: the
 * manual door for a (CC, GL) with no SAP actual yet). The GL picker is a
 * SEARCHABLE combobox (130+ master rows — a plain <select> was unusable):
 * type to filter by code/name, Enter picks the first match, Esc closes. */
export function AddTransactionForm({ fillCostCenters, glRef, existingRows, onAdd }: AddTransactionFormProps) {
  const [open, setOpen] = useState(false)
  const [costCenter, setCostCenter] = useState('')
  const [glAccount, setGlAccount] = useState('')
  const [glSearch, setGlSearch] = useState('')
  const [glListOpen, setGlListOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const nonSpecialGls = glRef.filter((g) => !g.is_special)
  const selectedGl = nonSpecialGls.find((g) => g.gl_code === glAccount)
  const query = glSearch.trim().toLowerCase()
  // Match code, name AND group — the label shows only name, but users also
  // search by group (e.g. "office" for the Office Expenses GLs).
  const filteredGls = query
    ? nonSpecialGls.filter((g) => `${g.gl_code} ${g.gl_name ?? ''} ${g.gl_group}`.toLowerCase().includes(query))
    : nonSpecialGls

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
    setGlAccount('')
    setGlSearch('')
    setGlListOpen(false)
    setError(null)
    setBusy(false)
  }

  async function handleSubmit() {
    const validation = validateNewTransaction({ costCenter, glAccount, fillCostCenters, glRef, existingRows })
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

  if (!open) {
    return (
      <button type="button" className="btn btn-add" onClick={() => setOpen(true)}>
        + เพิ่ม Transaction
      </button>
    )
  }

  return (
    <div className="add-txn-form">
      <label>
        Cost Center
        <select value={costCenter} onChange={(e) => setCostCenter(e.target.value)} aria-label="Cost Center">
          <option value="">— เลือก Cost Center —</option>
          {fillCostCenters.map((cc) => (
            <option key={cc} value={cc}>
              {cc}
            </option>
          ))}
        </select>
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
              {filteredGls.length === 0 && <div className="gl-combo-empty">ไม่พบ GL Code ที่ค้นหา</div>}
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
