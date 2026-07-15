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
 * manual door for a (CC, GL) with no SAP actual yet). */
export function AddTransactionForm({ fillCostCenters, glRef, existingRows, onAdd }: AddTransactionFormProps) {
  const [open, setOpen] = useState(false)
  const [costCenter, setCostCenter] = useState('')
  const [glAccount, setGlAccount] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const nonSpecialGls = glRef.filter((g) => !g.is_special)

  function reset() {
    setOpen(false)
    setCostCenter('')
    setGlAccount('')
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
        <select value={glAccount} onChange={(e) => setGlAccount(e.target.value)} aria-label="GL Code">
          <option value="">— เลือก GL Code —</option>
          {nonSpecialGls.map((g) => (
            <option key={g.gl_code} value={g.gl_code}>
              {g.gl_code} — {g.gl_name ?? g.gl_group}
            </option>
          ))}
        </select>
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
