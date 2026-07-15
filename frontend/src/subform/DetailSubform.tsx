import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { deleteDetailLine, fetchDetailLines, saveDetailLine } from '../api/subform'
import type { DetailLineState } from '../api/types'
import { formatThb, MONTH_KEYS } from '../grid/model'
import {
  blankDetailDraft,
  buildDetailLinePayload,
  detailFieldsFor,
  detailLineTotal,
  draftFromServerLine,
  type DetailLineDraft,
} from './model'

export interface DetailSubformProps {
  costCenter: string
  glAccount: string
  glGroup: string
  glName: string | null
  fiscalYear: number
  onClose: () => void
  /** Called after EVERY successful line save — the parent grid refetches so
   * the aggregate Pending cell (server-recomputed SUM of detail) stays in
   * sync while this modal is still open. */
  onSaved: () => void
}

type RowStatus = 'idle' | 'saving' | 'deleting' | 'error'

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
 * (ADR-0005: trip-centric, structurally different). Each line saves
 * independently (`PUT /budget/detail` is one line per call) so one line's
 * error never blocks another (mirrors the backend's per-item contract). */
export function DetailSubform({ costCenter, glAccount, glGroup, glName, fiscalYear, onClose, onSaved }: DetailSubformProps) {
  const [rows, setRows] = useState<RowState[]>([])
  const [loading, setLoading] = useState(true)
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
    const localId = `new-${newRowCounter}`
    setNewRowCounter((n) => n + 1)
    setRows((prev) => [...prev, { localId, draft: blankDetailDraft(costCenter, glAccount, fiscalYear), status: 'idle' }])
  }

  function updateDraft(localId: string, updater: (draft: DetailLineDraft) => DetailLineDraft) {
    setRows((prev) => prev.map((r) => (r.localId === localId ? { ...r, draft: updater(r.draft) } : r)))
  }

  function setMeta(localId: string, key: string, value: string) {
    updateDraft(localId, (d) => ({ ...d, meta: { ...d.meta, [key]: value } }))
  }

  function setMonth(localId: string, month: (typeof MONTH_KEYS)[number], value: number) {
    updateDraft(localId, (d) => ({ ...d, months: { ...d.months, [month]: value } }))
  }

  async function saveRow(localId: string) {
    const row = rows.find((r) => r.localId === localId)
    if (!row) return
    setRows((prev) => prev.map((r) => (r.localId === localId ? { ...r, status: 'saving', errorText: undefined } : r)))
    try {
      const saved = await saveDetailLine(buildDetailLinePayload(row.draft))
      setRows((prev) =>
        prev.map((r) =>
          r.localId === localId
            ? { localId: `existing-${saved.detail_id}`, draft: draftFromServerLine(saved), status: 'idle' }
            : r,
        ),
      )
      onSaved()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const lines = await fetchDetailLines(costCenter, glAccount, fiscalYear)
        setRows(rowsFromServer(lines))
        return
      }
      const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'บันทึกไม่สำเร็จ'
      setRows((prev) => prev.map((r) => (r.localId === localId ? { ...r, status: 'error', errorText: message } : r)))
    }
  }

  async function deleteRow(localId: string) {
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

  return (
    <div className="modal-backdrop open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" data-testid="detail-subform">
        <div className="modal-head">
          <div>
            <h2 className="modal-title">
              รายละเอียด <em>{glGroup}</em>
            </h2>
            <p className="modal-subtitle">
              {costCenter} · {glAccount} · {glName ?? '—'}
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
                  <th>#</th>
                  {fields.map((f) => (
                    <th key={f.key} className="special-col">
                      {f.key}
                    </th>
                  ))}
                  {MONTH_KEYS.map((m) => (
                    <th key={m} className="month-col">
                      {m}
                    </th>
                  ))}
                  <th className="month-col">รวม</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr key={row.localId} data-testid={`detail-row-${row.localId}`}>
                    <td>{idx + 1}</td>
                    {fields.map((f) => {
                      if (f.kind === 'locked') {
                        return (
                          <td key={f.key} className="special-col-cell">
                            <span title="ไม่ใช้กับ GL นี้">—</span>
                          </td>
                        )
                      }
                      if (f.kind === 'select') {
                        return (
                          <td key={f.key} className="special-col-cell">
                            <select
                              aria-label={f.key}
                              className="detail-input"
                              value={row.draft.meta[f.key] ?? ''}
                              onChange={(e) => setMeta(row.localId, f.key, e.target.value)}
                            >
                              <option value="">— เลือก —</option>
                              {f.options?.map((opt) => (
                                <option key={opt} value={opt}>
                                  {opt}
                                </option>
                              ))}
                            </select>
                          </td>
                        )
                      }
                      return (
                        <td key={f.key} className="special-col-cell">
                          <input
                            aria-label={f.key}
                            className="detail-input"
                            value={row.draft.meta[f.key] ?? ''}
                            onChange={(e) => setMeta(row.localId, f.key, e.target.value)}
                          />
                        </td>
                      )
                    })}
                    {MONTH_KEYS.map((m) => (
                      <td key={m} className="month-cell">
                        <input
                          aria-label={`${m} ${row.localId}`}
                          className="detail-input month-input"
                          inputMode="numeric"
                          value={row.draft.months[m] || ''}
                          onChange={(e) => setMonth(row.localId, m, Number(e.target.value.replace(/[^0-9]/g, '')) || 0)}
                        />
                      </td>
                    ))}
                    <td className="month-cell">
                      <span className="month-value">{formatThb(detailLineTotal(row.draft))}</span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="action-btn"
                        aria-label="ลบรายการ"
                        disabled={row.status === 'deleting' || row.status === 'saving'}
                        onClick={() => deleteRow(row.localId)}
                      >
                        {row.status === 'deleting' ? 'กำลังลบ…' : 'ลบ'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {rows.map((row) => (
            <div key={`actions-${row.localId}`} className="detail-row-actions">
              <button
                type="button"
                className="btn btn-export"
                disabled={row.status === 'saving' || row.status === 'deleting'}
                onClick={() => saveRow(row.localId)}
                data-testid={`save-row-${row.localId}`}
              >
                {row.status === 'saving' ? 'กำลังบันทึก…' : 'บันทึกรายการนี้'}
              </button>
              {row.status === 'error' && (
                <span className="row-message row-message-error">{row.errorText}</span>
              )}
            </div>
          ))}
        </div>

        <div className="modal-foot">
          <div className="modal-foot-info">รายการ: {rows.length}</div>
          <div className="modal-actions">
            <button type="button" className="btn" onClick={addRow}>
              + เพิ่มรายการ
            </button>
            <button type="button" className="btn" onClick={onClose}>
              ปิด
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
