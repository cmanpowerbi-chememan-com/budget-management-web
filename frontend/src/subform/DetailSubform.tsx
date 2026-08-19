import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { deleteDetailLine, fetchDetailLines, saveDetailLine } from '../api/subform'
import type { DetailLineState } from '../api/types'
import { formatThb, MONTH_KEYS, MONTH_LABELS } from '../grid/model'
import { MonthAmountInput } from './MonthAmountInput'
import {
  blankDetailDraft,
  buildDetailLinePayload,
  detailFieldsFor,
  detailLineTotal,
  draftFromServerLine,
  fieldFreeText,
  fieldSelectValue,
  firstBlankFreeTextField,
  firstUnselectedRequiredField,
  type DetailLineDraft,
} from './model'

export interface DetailSubformProps {
  costCenter: string
  glAccount: string
  glGroup: string
  glName: string | null
  fiscalYear: number
  /** ADR-0013 read-only lock (UI parity port, 2026-08-05) — set by the
   * caller from `!row.editable` at open time (See-only viewer, or the
   * department is mid-approval/APPROVED for this Filler). Every mutation
   * (add/save/delete row, edit a field) is a no-op; `บันทึก`/`+ เพิ่มรายการ`
   * are hidden and `ยกเลิก` becomes `ปิด`. Defaults to `false` (editable) so
   * existing callers/tests are unaffected. */
  readOnly?: boolean
  onClose: () => void
  /** Called after a successful save batch (at least one line written) — the
   * parent grid refetches so the aggregate Pending cell (server-recomputed
   * SUM of detail) stays in sync. */
  onSaved: () => void
}

type RowStatus = 'idle' | 'deleting' | 'error'

interface RowState {
  localId: string
  draft: DetailLineDraft
  status: RowStatus
  errorText?: string
}

const DELETE_CONFIRM_TEXT = 'ลบรายการนี้?'
const DELETE_CONFLICT_MESSAGE = 'รายการนี้ถูกแก้ไขหรือถูกลบโดยผู้อื่นไปแล้ว กรุณาตรวจสอบข้อมูลล่าสุด'

function rowsFromServer(lines: DetailLineState[]): RowState[] {
  return lines.map((line) => ({ localId: `existing-${line.detail_id}`, draft: draftFromServerLine(line), status: 'idle' }))
}

/** Special-GL detail-line subform for the 5 non-travel groups (Entertainment,
 * Lease & Rental, Professional & Legal Fee, Public Relation & Donation,
 * Training & Seminar) — Travelling Expense uses `TripManager` instead
 * (ADR-0005: trip-centric, structurally different). Layout follows mockup
 * 0002.3budget-export.html `#detailModal`: JAN..DEC month columns, a Monthly
 * total row, and ONE footer บันทึก button (`saveAll`) that writes every line
 * (`PUT /budget/detail` is still one line per call) so one line's error never
 * blocks another — on full success the modal closes, on any failure it stays
 * open with the failed rows marked. */
export function DetailSubform({
  costCenter,
  glAccount,
  glGroup,
  glName,
  fiscalYear,
  readOnly = false,
  onClose,
  onSaved,
}: DetailSubformProps) {
  const [rows, setRows] = useState<RowState[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [newRowCounter, setNewRowCounter] = useState(0)
  const [conflictMessage, setConflictMessage] = useState<string | null>(null)

  const fields = detailFieldsFor(glGroup, glAccount)

  async function load() {
    setLoading(true)
    setLoadError(null)
    try {
      const lines = await fetchDetailLines(costCenter, glAccount, fiscalYear)
      setRows(rowsFromServer(lines))
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : 'โหลดรายละเอียดไม่สำเร็จ กรุณาลองใหม่อีกครั้ง')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [costCenter, glAccount, fiscalYear])

  function addRow() {
    if (readOnly) return
    const localId = `new-${newRowCounter}`
    setNewRowCounter((n) => n + 1)
    setRows((prev) => [...prev, { localId, draft: blankDetailDraft(costCenter, glAccount, fiscalYear), status: 'idle' }])
  }

  function updateDraft(localId: string, updater: (draft: DetailLineDraft) => DetailLineDraft) {
    setRows((prev) => prev.map((r) => (r.localId === localId ? { ...r, draft: updater(r.draft) } : r)))
  }

  function setMeta(localId: string, key: string, value: string) {
    if (readOnly) return
    updateDraft(localId, (d) => ({ ...d, meta: { ...d.meta, [key]: value } }))
  }

  function setMonth(localId: string, month: (typeof MONTH_KEYS)[number], value: number) {
    if (readOnly) return
    updateDraft(localId, (d) => ({ ...d, months: { ...d.months, [month]: value } }))
  }

  /** Consolidated บันทึก — the ONE save path for the whole modal (mockup
   * `#detailModal` foot: ยกเลิก / + เพิ่มรายการ / บันทึก). Iterates one
   * snapshot of `rows` taken at click time; every line is attempted, one
   * line's failure never blocks the rest of the batch (partial-failure
   * policy, same as TripManager's saveAll). Full success closes the modal
   * (mock saveDetailData); any failure keeps it open with the failed rows
   * marked so the user can fix and re-click. */
  async function saveAll() {
    if (readOnly || saving || loading) return
    setSaving(true)
    setConflictMessage(null)
    const snapshot = rows
    // Seeded with every row up front and replaced BY INDEX (never pushed) —
    // an unexpected throw mid-loop still leaves every earlier row's result
    // intact instead of silently dropping the tail of the batch.
    const nextRows: RowState[] = snapshot.slice()
    let anySaved = false
    let anyError = false
    try {
      for (let i = 0; i < snapshot.length; i++) {
        const row = snapshot[i]
        // A free-text trigger option ('อื่นๆ') with nothing typed must never
        // be sent — the API expects the actual plate, not the trigger literal.
        const blankFreeText = firstBlankFreeTextField(fields, row.draft.meta)
        if (blankFreeText) {
          anyError = true
          nextRows[i] = { ...row, status: 'error', errorText: `กรุณาพิมพ์${blankFreeText}` }
          continue
        }
        // A required dropdown (e.g. Entertainment's ประเภทการรับรอง) left on
        // the blank placeholder must never reach the API — a doomed save
        // used to sail past here and 400 on the server (bug-entertainment-
        // blank-type-400). Same guard shape/Thai voice as the free-text check.
        const blankRequired = firstUnselectedRequiredField(fields, row.draft.meta)
        if (blankRequired) {
          anyError = true
          nextRows[i] = { ...row, status: 'error', errorText: `กรุณาเลือก${blankRequired}` }
          continue
        }
        try {
          const saved = await saveDetailLine(buildDetailLinePayload(row.draft))
          anySaved = true
          nextRows[i] = { localId: `existing-${saved.detail_id}`, draft: draftFromServerLine(saved), status: 'idle' }
        } catch (err) {
          if (err instanceof ApiError && err.status === 409) {
            // Someone else changed these lines — replace with the server's
            // latest and abort the rest of the batch (the snapshot is stale).
            const lines = await fetchDetailLines(costCenter, glAccount, fiscalYear)
            setRows(rowsFromServer(lines))
            if (anySaved) onSaved()
            return
          }
          anyError = true
          const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'บันทึกไม่สำเร็จ'
          nextRows[i] = { ...row, status: 'error', errorText: message }
        }
      }
      setRows(nextRows)
      if (anySaved) onSaved()
      if (!anyError) onClose()
    } finally {
      setSaving(false)
    }
  }

  async function deleteRow(localId: string) {
    if (readOnly) return
    const row = rows.find((r) => r.localId === localId)
    if (!row) return

    // An unsaved (never-persisted) row has nothing to delete server-side —
    // just drop it from local state, no confirm needed.
    if (row.draft.detail_id === null) {
      setRows((prev) => prev.filter((r) => r.localId !== localId))
      return
    }

    if (!window.confirm(DELETE_CONFIRM_TEXT)) return

    setConflictMessage(null)
    setRows((prev) => prev.map((r) => (r.localId === localId ? { ...r, status: 'deleting', errorText: undefined } : r)))
    try {
      await deleteDetailLine(row.draft.detail_id, row.draft.expected_updated_at ?? '')
      setRows((prev) => prev.filter((r) => r.localId !== localId))
      onSaved()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConflictMessage(DELETE_CONFLICT_MESSAGE)
        const lines = await fetchDetailLines(costCenter, glAccount, fiscalYear)
        setRows(rowsFromServer(lines))
        return
      }
      const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'ลบไม่สำเร็จ'
      setRows((prev) => prev.map((r) => (r.localId === localId ? { ...r, status: 'error', errorText: message } : r)))
    }
  }

  /** Client-side Monthly total row (mockup `#detailModal` renderDetailTable)
   * — display only; the authoritative sums are server-recomputed on save. */
  const monthlyTotals = MONTH_KEYS.map((m) => rows.reduce((sum, r) => sum + (r.draft.months[m] || 0), 0))
  const grandTotal = monthlyTotals.reduce((a, b) => a + b, 0)

  return (
    <div className="modal-backdrop open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" data-testid="detail-subform">
        <div className="modal-head">
          <div>
            <h2 className="modal-title">
              รายละเอียด <em>{glGroup}</em>
              {readOnly ? ' 🔒' : ''}
            </h2>
            <p className="modal-subtitle">
              {costCenter} · {glAccount} · {glName ?? '—'}
              {readOnly ? ' · อ่านอย่างเดียว (แก้ไม่ได้)' : ''}
            </p>
          </div>
          <button type="button" className="modal-close" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {conflictMessage && (
            <div className="grid-error" role="alert">
              <span>{conflictMessage}</span>
            </div>
          )}

          {loading && <div className="grid-loading">กำลังโหลดรายละเอียด…</div>}

          {!loading && loadError && (
            <div className="grid-error" role="alert">
              <span>{loadError}</span>
              <button type="button" className="btn" onClick={load}>
                ลองใหม่
              </button>
            </div>
          )}

          {!loading && !loadError && rows.length === 0 && (
            <div className="grid-empty">ยังไม่มีรายการ — กด “+ เพิ่มรายการ” เพื่อเริ่ม</div>
          )}

          {!loading && !loadError && rows.length > 0 && (
            <table className="detail-table">
              <thead>
                <tr>
                  <th className="num-col">#</th>
                  {fields.map((f) => (
                    <th key={f.key} className="special-col">
                      {f.key}
                    </th>
                  ))}
                  {MONTH_KEYS.map((m) => (
                    <th key={m} className="month-col">
                      {MONTH_LABELS[m]}
                    </th>
                  ))}
                  {/* Accent-tinted รวม header, per mockup #detailModal */}
                  <th
                    className="month-col"
                    style={{ background: 'color-mix(in oklab, var(--accent) 10%, var(--paper-2))', color: 'var(--accent-text)' }}
                  >
                    รวม
                  </th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={row.localId} data-testid={`detail-row-${row.localId}`}>
                    <td className="num-col">
                      <div className="idx-cell">{idx + 1}</div>
                    </td>
                    {fields.map((f) => {
                      if (f.kind === 'locked') {
                        return (
                          <td key={f.key} className="special-col-cell">
                            <span title="ไม่ใช้กับ GL นี้">—</span>
                          </td>
                        )
                      }
                      if (f.kind === 'select') {
                        const storedValue = row.draft.meta[f.key] ?? null
                        const selectValue = fieldSelectValue(f, storedValue)
                        const showFreeText = f.freeTextOption !== undefined && selectValue === f.freeTextOption
                        return (
                          <td key={f.key} className="special-col-cell">
                            <select
                              aria-label={f.key}
                              className="detail-input"
                              value={selectValue}
                              disabled={readOnly}
                              onChange={(e) => setMeta(row.localId, f.key, e.target.value)}
                            >
                              <option value="">— เลือก —</option>
                              {f.options?.map((opt) => (
                                <option key={opt} value={opt}>
                                  {opt}
                                </option>
                              ))}
                            </select>
                            {showFreeText && (
                              <input
                                aria-label={`${f.key} กำหนดเอง`}
                                className="detail-input free-text-input"
                                placeholder={`พิมพ์${f.key}`}
                                value={fieldFreeText(f, storedValue)}
                                disabled={readOnly}
                                onChange={(e) =>
                                  // Empty box falls back to the trigger literal so the
                                  // select stays on อื่นๆ; save is blocked in that state.
                                  setMeta(row.localId, f.key, e.target.value.trim() ? e.target.value : f.freeTextOption!)
                                }
                              />
                            )}
                          </td>
                        )
                      }
                      return (
                        <td key={f.key} className="special-col-cell">
                          <input
                            aria-label={f.key}
                            className="detail-input"
                            value={row.draft.meta[f.key] ?? ''}
                            disabled={readOnly}
                            onChange={(e) => setMeta(row.localId, f.key, e.target.value)}
                          />
                        </td>
                      )
                    })}
                    {MONTH_KEYS.map((m) => (
                      <td key={m} className="month-cell">
                        <MonthAmountInput
                          ariaLabel={`${m} ${row.localId}`}
                          className="detail-input month-input"
                          value={row.draft.months[m]}
                          disabled={readOnly}
                          onCommit={(v) => setMonth(row.localId, m, v)}
                        />
                      </td>
                    ))}
                    <td className="month-cell">
                      <span className="month-value pending-readonly">{formatThb(detailLineTotal(row.draft))}</span>
                    </td>
                    <td>
                      {/* Icon-only trash, mockup #detailModal .action-btn (26×26) —
                       * hidden entirely when read-only (ADR-0013), not just disabled. */}
                      {!readOnly && (
                        <button
                          type="button"
                          className="action-btn"
                          aria-label="ลบรายการ"
                          title="ลบรายการ"
                          disabled={row.status === 'deleting' || saving}
                          onClick={() => deleteRow(row.localId)}
                        >
                          {row.status === 'deleting' ? (
                            '…'
                          ) : (
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="3 6 5 6 21 6" />
                              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                            </svg>
                          )}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {/* Monthly total row — mockup #detailModal renderDetailTable */}
                <tr className="total-row">
                  <td className="label" colSpan={1 + fields.length}>
                    Monthly total
                  </td>
                  {MONTH_KEYS.map((m, i) => (
                    <td key={m} className="month-cell">
                      <span className="month-value pending-readonly">{formatThb(monthlyTotals[i])}</span>
                    </td>
                  ))}
                  <td className="month-cell grand">{formatThb(grandTotal)}</td>
                  <td />
                </tr>
              </tbody>
            </table>
          )}

          {/* Per-row save errors — no per-row save button; the ONE บันทึก
           * lives in the footer (mockup #detailModal). Each error is labeled
           * with its 1-based row number so the user can find the failed row. */}
          {rows.map((row, idx) =>
            row.status === 'error' && row.errorText ? (
              <div key={`error-${row.localId}`} className="detail-row-actions" data-testid={`detail-row-error-${row.localId}`}>
                <span>รายการที่ {idx + 1}:</span>
                <span className="row-message row-message-error">{row.errorText}</span>
              </div>
            ) : null,
          )}
        </div>

        <div className="modal-foot">
          <div className="modal-foot-info">
            Rows: <b>{rows.length}</b> · Year total: <b>฿{formatThb(grandTotal)}</b>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" disabled={loading || saving} onClick={onClose}>
              {readOnly ? 'ปิด' : 'ยกเลิก'}
            </button>
            {/* Add/save hidden entirely when read-only (ADR-0013) — mockup
             * #detailModal footer: detailAddBtn/detailSaveBtn display:none. */}
            {!readOnly && (
              <>
                {/* Disabled while load() is in-flight — its setRows(...) REPLACES the
                 * array, so a row added before the data lands would be silently lost. */}
                <button type="button" className="btn btn-add" disabled={loading || saving} onClick={addRow}>
                  + เพิ่มรายการ
                </button>
                <button
                  type="button"
                  className="btn btn-export"
                  disabled={loading || saving || rows.length === 0}
                  onClick={saveAll}
                  data-testid="save-all"
                >
                  {saving ? 'กำลังบันทึก…' : 'บันทึก'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
