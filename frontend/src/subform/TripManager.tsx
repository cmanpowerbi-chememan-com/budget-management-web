import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { createTrip, deleteTrip, fetchDetailLines, fetchTrips, saveDetailLine, updateTrip } from '../api/subform'
import type { DetailLineState, TripListItem } from '../api/types'
import { formatThb, MONTH_KEYS, type MonthKey } from '../grid/model'
import {
  MANUAL_TRAVEL_TYPES,
  TRAVEL_GL_BY_TYPE_SIDE,
  TRAVEL_TYPE_LABEL_TH,
  type TravelExpenseType,
} from './glDropdownConstants'
import {
  blankManualLineDraft,
  blankTripDraft,
  buildManualLinePayload,
  buildTripPayload,
  draftFromTripListItem,
  indexDetailLinesByTrip,
  isTripMonthActive,
  manualLineDraftFromServerLine,
  manualLineTotal,
  validateTripDraft,
  type ManualLineDraft,
  type TravelSideHistory,
  type TripDraft,
  type TripSide,
} from './model'

export interface TripManagerProps {
  costCenter: string
  fiscalYear: number
  /** ฝ่าย-level travel-side history (`deriveTravelSideHistory` over the
   * parent's already-loaded grid rows) — decides the side select's
   * default / lock / placeholder state. */
  sideHistory: TravelSideHistory
  /** `is_admin` from /scope — only an admin may book a side the ฝ่าย has
   * never used (e.g. legitimately introducing it in a forward budget). */
  isAdmin: boolean
  onClose: () => void
  /** Called after EVERY successful trip/manual-line save — the parent grid
   * refetches so all 8 travel GL cells (both sides, in case of a side flip)
   * show server-recomputed sums. */
  onSaved: () => void
}

type Status = 'idle' | 'saving' | 'deleting' | 'error'

interface TripCardState {
  localId: string
  draft: TripDraft
  dirty: boolean
  perDiemMonths: Record<string, number> | null
  perDiemError: string | null
  status: Status
  errorText?: string
  manual: Record<Exclude<TravelExpenseType, 'per_diem'>, ManualLineDraft>
  manualStatus: Record<Exclude<TravelExpenseType, 'per_diem'>, Status>
  manualError: Partial<Record<Exclude<TravelExpenseType, 'per_diem'>, string>>
}

const DELETE_TRIP_CONFIRM_TEXT = 'ลบทริปนี้ทั้งหมด? รายการเบี้ยเลี้ยง/ค่าเดินทางทั้งหมดของทริปจะถูกลบ'
const DELETE_TRIP_CONFLICT_MESSAGE = 'ทริปนี้ถูกแก้ไขหรือถูกลบโดยผู้อื่นไปแล้ว กรุณาตรวจสอบข้อมูลล่าสุด'

function blankManualByType(): Record<Exclude<TravelExpenseType, 'per_diem'>, ManualLineDraft> {
  return {
    transport: blankManualLineDraft(),
    accommodation: blankManualLineDraft(),
    other: blankManualLineDraft(),
  }
}

function blankManualStatus(): Record<Exclude<TravelExpenseType, 'per_diem'>, Status> {
  return { transport: 'idle', accommodation: 'idle', other: 'idle' }
}

function cardFromServerTrip(
  trip: TripListItem,
  detailIndex: Record<number, Partial<Record<Exclude<TravelExpenseType, 'per_diem'>, DetailLineState>>>,
): TripCardState {
  const manual = blankManualByType()
  const lines = detailIndex[trip.trip_id] ?? {}
  MANUAL_TRAVEL_TYPES.forEach((type) => {
    const line = lines[type]
    if (line) manual[type] = manualLineDraftFromServerLine(line)
  })
  return {
    localId: `existing-${trip.trip_id}`,
    draft: draftFromTripListItem(trip),
    dirty: false,
    perDiemMonths: trip.per_diem_months,
    perDiemError: trip.per_diem_error,
    status: 'idle',
    manual,
    manualStatus: blankManualStatus(),
    manualError: {},
  }
}

async function fetchAllManualLines(costCenter: string, fiscalYear: number): Promise<DetailLineState[]> {
  const requests = MANUAL_TRAVEL_TYPES.flatMap((type) =>
    (['COST', 'SGA'] as const).map((side) => fetchDetailLines(costCenter, TRAVEL_GL_BY_TYPE_SIDE[type][side], fiscalYear)),
  )
  const results = await Promise.all(requests)
  return results.flat()
}

/** Trip Manager (A9) — "1 ทริป = กรอกครั้งเดียว": one trip header (traveler,
 * destination, days, travel months, accounting side) auto-derives per-diem
 * server-side (ADR-0005/0015); the 3 manual expense types (transport/
 * accommodation/other) are entered per month, locked to the trip's selected
 * travel_months. Per-diem is NEVER computed here — only the server's own
 * response/read is ever shown (never-cut). */
export function TripManager({ costCenter, fiscalYear, sideHistory, isAdmin, onClose, onSaved }: TripManagerProps) {
  const [cards, setCards] = useState<TripCardState[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [newTripCounter, setNewTripCounter] = useState(0)
  const [conflictMessage, setConflictMessage] = useState<string | null>(null)

  // Exactly one side in the ฝ่าย's real history → non-admins cannot
  // mis-book to the side the ฝ่าย never uses. Both sides / no history →
  // the select stays open (nothing to lock to).
  const sideLocked = !isAdmin && sideHistory.sides.length === 1

  async function load() {
    setLoading(true)
    setLoadError(null)
    try {
      const [trips, manualLines] = await Promise.all([
        fetchTrips(costCenter, fiscalYear),
        fetchAllManualLines(costCenter, fiscalYear),
      ])
      const index = indexDetailLinesByTrip(manualLines)
      setCards(trips.map((t) => cardFromServerTrip(t, index)))
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : 'โหลดข้อมูลทริปไม่สำเร็จ กรุณาลองใหม่อีกครั้ง')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [costCenter, fiscalYear])

  function addTrip() {
    const localId = `new-${newTripCounter}`
    setNewTripCounter((n) => n + 1)
    setCards((prev) => [
      ...prev,
      {
        localId,
        draft: blankTripDraft(costCenter, fiscalYear, sideHistory.defaultSide),
        dirty: false,
        perDiemMonths: null,
        perDiemError: null,
        status: 'idle',
        manual: blankManualByType(),
        manualStatus: blankManualStatus(),
        manualError: {},
      },
    ])
  }

  function updateTripField(localId: string, updater: (draft: TripDraft) => TripDraft) {
    setCards((prev) => prev.map((c) => (c.localId === localId ? { ...c, draft: updater(c.draft), dirty: true } : c)))
  }

  function toggleMonth(localId: string, month: string) {
    updateTripField(localId, (d) => {
      const has = d.travel_months.includes(month)
      const travel_months = has ? d.travel_months.filter((m) => m !== month) : [...d.travel_months, month].sort()
      return { ...d, travel_months }
    })
  }

  async function saveTrip(localId: string) {
    const card = cards.find((c) => c.localId === localId)
    if (!card) return
    const validation = validateTripDraft(card.draft)
    if (!validation.ok) {
      setCards((prev) => prev.map((c) => (c.localId === localId ? { ...c, status: 'error', errorText: validation.errorTh } : c)))
      return
    }
    setCards((prev) => prev.map((c) => (c.localId === localId ? { ...c, status: 'saving', errorText: undefined } : c)))
    try {
      const payload = buildTripPayload(card.draft)
      const saved = card.draft.trip_id === null ? await createTrip(payload) : await updateTrip(payload)
      setCards((prev) =>
        prev.map((c) =>
          c.localId === localId
            ? {
                ...c,
                localId: `existing-${saved.trip_id}`,
                draft: { ...card.draft, trip_id: saved.trip_id, side: saved.side, expected_updated_at: saved.updated_at },
                dirty: false,
                perDiemMonths: saved.per_diem_months,
                perDiemError: null,
                status: 'idle',
              }
            : c,
        ),
      )
      onSaved()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        await load()
        return
      }
      const message =
        err instanceof ApiError && err.status >= 500
          ? `ไม่สามารถคำนวณเบี้ยเลี้ยงได้ — ${err.detail ?? 'ไม่พบอัตราเบี้ยเลี้ยงหรืออัตราแลกเปลี่ยนสำหรับปีนี้'}`
          : err instanceof ApiError
            ? `${err.message}${err.detail ? ` (${err.detail})` : ''}`
            : 'บันทึกทริปไม่สำเร็จ'
      setCards((prev) => prev.map((c) => (c.localId === localId ? { ...c, status: 'error', errorText: message } : c)))
    }
  }

  function setManualMonth(localId: string, type: Exclude<TravelExpenseType, 'per_diem'>, month: MonthKey, value: number) {
    setCards((prev) =>
      prev.map((c) =>
        c.localId === localId
          ? { ...c, manual: { ...c.manual, [type]: { ...c.manual[type], months: { ...c.manual[type].months, [month]: value } } } }
          : c,
      ),
    )
  }

  async function saveManualLine(localId: string, type: Exclude<TravelExpenseType, 'per_diem'>) {
    const card = cards.find((c) => c.localId === localId)
    // side is always set once a trip exists (the server returns it on save/read).
    if (!card || card.draft.trip_id === null || card.draft.side === null) return
    const tripId = card.draft.trip_id
    const glAccount = TRAVEL_GL_BY_TYPE_SIDE[type][card.draft.side]
    setCards((prev) =>
      prev.map((c) =>
        c.localId === localId
          ? { ...c, manualStatus: { ...c.manualStatus, [type]: 'saving' }, manualError: { ...c.manualError, [type]: undefined } }
          : c,
      ),
    )
    try {
      const saved = await saveDetailLine(buildManualLinePayload(card.manual[type], costCenter, glAccount, fiscalYear, tripId))
      setCards((prev) =>
        prev.map((c) =>
          c.localId === localId
            ? {
                ...c,
                manual: { ...c.manual, [type]: manualLineDraftFromServerLine(saved) },
                manualStatus: { ...c.manualStatus, [type]: 'idle' },
              }
            : c,
        ),
      )
      onSaved()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        await load()
        return
      }
      const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'บันทึกไม่สำเร็จ'
      setCards((prev) =>
        prev.map((c) =>
          c.localId === localId
            ? { ...c, manualStatus: { ...c.manualStatus, [type]: 'error' }, manualError: { ...c.manualError, [type]: message } }
            : c,
        ),
      )
    }
  }

  async function deleteTripCard(localId: string) {
    const card = cards.find((c) => c.localId === localId)
    if (!card) return

    // An unsaved (never-persisted) trip has nothing to delete server-side —
    // just drop the card from local state, no confirm needed.
    if (card.draft.trip_id === null) {
      setCards((prev) => prev.filter((c) => c.localId !== localId))
      return
    }

    if (!window.confirm(DELETE_TRIP_CONFIRM_TEXT)) return

    setConflictMessage(null)
    setCards((prev) => prev.map((c) => (c.localId === localId ? { ...c, status: 'deleting', errorText: undefined } : c)))
    try {
      await deleteTrip(card.draft.trip_id, card.draft.expected_updated_at ?? '')
      setCards((prev) => prev.filter((c) => c.localId !== localId))
      onSaved()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConflictMessage(DELETE_TRIP_CONFLICT_MESSAGE)
        await load()
        return
      }
      const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'ลบทริปไม่สำเร็จ'
      setCards((prev) => prev.map((c) => (c.localId === localId ? { ...c, status: 'error', errorText: message } : c)))
    }
  }

  return (
    <div className="modal-backdrop open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal trip-modal" data-testid="trip-manager">
        <div className="modal-head">
          <div>
            <h2 className="modal-title">
              Travelling Expense — <em>จัดการทริป</em>
            </h2>
            <p className="modal-subtitle">
              {costCenter} · FY{fiscalYear} · ทริปทั้งหมดรวมกัน 4 ประเภทค่าใช้จ่าย
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

          {loading && <div className="grid-loading">กำลังโหลดข้อมูลทริป…</div>}

          {!loading && loadError && (
            <div className="grid-error" role="alert">
              <span>{loadError}</span>
              <button type="button" className="btn" onClick={load}>
                ลองใหม่
              </button>
            </div>
          )}

          {!loading && !loadError && cards.length === 0 && (
            <div className="trip-empty">ยังไม่มีทริป — กด “+ เพิ่มทริป” เพื่อเริ่ม</div>
          )}

          {!loading &&
            !loadError &&
            cards.map((card, idx) => (
              <div key={card.localId} className="trip-card" data-testid={`trip-card-${card.localId}`}>
                <div className="trip-card-head">
                  <span className="trip-idx">{String(idx + 1).padStart(2, '0')}</span>
                  <span>{card.draft.traveler_empcode || 'ผู้เดินทางใหม่'}</span>
                  <button
                    type="button"
                    className="action-btn"
                    aria-label="ลบทริป"
                    disabled={card.status === 'deleting' || card.status === 'saving'}
                    onClick={() => deleteTripCard(card.localId)}
                  >
                    {card.status === 'deleting' ? 'กำลังลบ…' : 'ลบ'}
                  </button>
                </div>
                <div className="trip-card-body">
                  <div className="trip-field-grid">
                    <label>
                      รหัสพนักงานผู้เดินทาง
                      <input
                        aria-label={`traveler_empcode ${card.localId}`}
                        value={card.draft.traveler_empcode}
                        onChange={(e) => updateTripField(card.localId, (d) => ({ ...d, traveler_empcode: e.target.value }))}
                      />
                    </label>
                    <label>
                      ปลายทาง
                      <input
                        aria-label={`destination ${card.localId}`}
                        value={card.draft.destination ?? ''}
                        onChange={(e) => updateTripField(card.localId, (d) => ({ ...d, destination: e.target.value || null }))}
                      />
                    </label>
                    <label>
                      กลุ่มปลายทาง
                      <select
                        aria-label={`country_group ${card.localId}`}
                        value={card.draft.country_group}
                        onChange={(e) =>
                          updateTripField(card.localId, (d) => ({ ...d, country_group: Number(e.target.value) as 1 | 2 | 3 }))
                        }
                      >
                        <option value={1}>ในประเทศ</option>
                        <option value={2}>ต่างประเทศ · อาเซียน</option>
                        <option value={3}>ต่างประเทศ · อื่นๆ</option>
                      </select>
                    </label>
                    <label>
                      จำนวนวัน
                      <input
                        aria-label={`days ${card.localId}`}
                        inputMode="numeric"
                        value={card.draft.days || ''}
                        onChange={(e) =>
                          updateTripField(card.localId, (d) => ({ ...d, days: Number(e.target.value.replace(/[^0-9]/g, '')) || 0 }))
                        }
                      />
                    </label>
                    <label>
                      ฝั่งบัญชี
                      <select
                        aria-label={`side ${card.localId}`}
                        value={card.draft.side ?? ''}
                        disabled={sideLocked}
                        title={sideLocked ? 'ฝ่ายนี้ใช้ฝั่งนี้ฝั่งเดียวตามข้อมูลจริง — เฉพาะ Admin เปลี่ยนได้' : undefined}
                        onChange={(e) => updateTripField(card.localId, (d) => ({ ...d, side: e.target.value as TripSide }))}
                      >
                        {card.draft.side === null && (
                          <option value="" disabled>
                            — เลือกฝั่ง —
                          </option>
                        )}
                        <option value="COST">ฝั่งผลิต / ต้นทุน (5xxx)</option>
                        <option value="SGA">ฝั่งบริหาร / ขาย · SG&A (6xxx)</option>
                      </select>
                    </label>
                  </div>

                  <div className="trip-months-label">Travel Month — คลิกเลือกเดือนที่เดินทาง</div>
                  <div className="trip-months-grid">
                    {MONTH_KEYS.map((m) => {
                      const monthNum = m.slice(1)
                      const on = card.draft.travel_months.includes(monthNum)
                      return (
                        <button
                          type="button"
                          key={m}
                          className={`tm-toggle ${on ? 'on' : ''}`}
                          aria-pressed={on}
                          onClick={() => toggleMonth(card.localId, monthNum)}
                        >
                          {m}
                        </button>
                      )
                    })}
                  </div>

                  <div className="trip-per-diem-note">
                    {card.perDiemError ? (
                      <span className="row-message row-message-error">ไม่สามารถคำนวณเบี้ยเลี้ยงได้ — {card.perDiemError}</span>
                    ) : card.dirty || !card.perDiemMonths ? (
                      <span>เบี้ยเลี้ยง: ระบบจะคำนวณให้หลังกดบันทึก</span>
                    ) : (
                      <span>
                        เบี้ยเลี้ยง (จากเซิร์ฟเวอร์):{' '}
                        {formatThb(Object.values(card.perDiemMonths).reduce((s, v) => s + v, 0))}
                      </span>
                    )}
                  </div>

                  <div className="trip-actions">
                    <button
                      type="button"
                      className="btn btn-export"
                      disabled={card.status === 'saving' || card.status === 'deleting' || card.draft.side === null}
                      title={card.draft.side === null ? 'กรุณาเลือกฝั่งบัญชีก่อนบันทึก' : undefined}
                      onClick={() => saveTrip(card.localId)}
                      data-testid={`save-trip-${card.localId}`}
                    >
                      {card.status === 'saving' ? 'กำลังบันทึก…' : 'บันทึกทริป'}
                    </button>
                    {card.status === 'error' && <span className="row-message row-message-error">{card.errorText}</span>}
                  </div>

                  {card.draft.trip_id !== null && (
                    <table className="trip-exp-table">
                      <thead>
                        <tr>
                          <th>ประเภทค่าใช้จ่าย</th>
                          {MONTH_KEYS.map((m) => (
                            <th key={m}>{m}</th>
                          ))}
                          <th>รวม</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {MANUAL_TRAVEL_TYPES.map((type) => (
                          <tr key={type}>
                            <td className="exp-type-name">{TRAVEL_TYPE_LABEL_TH[type]}</td>
                            {MONTH_KEYS.map((m) => {
                              const active = isTripMonthActive(card.draft.travel_months, m)
                              return (
                                <td key={m}>
                                  {active ? (
                                    <input
                                      aria-label={`${type} ${m} ${card.localId}`}
                                      className="exp-detail-input"
                                      inputMode="numeric"
                                      value={card.manual[type].months[m] || ''}
                                      onChange={(e) =>
                                        setManualMonth(card.localId, type, m, Number(e.target.value.replace(/[^0-9]/g, '')) || 0)
                                      }
                                    />
                                  ) : (
                                    <span title="เดือนนี้ไม่ได้เลือกเดินทาง">—</span>
                                  )}
                                </td>
                              )
                            })}
                            <td>{formatThb(manualLineTotal(card.manual[type]))}</td>
                            <td>
                              <button
                                type="button"
                                className="btn"
                                disabled={card.manualStatus[type] === 'saving' || card.status === 'deleting'}
                                onClick={() => saveManualLine(card.localId, type)}
                                data-testid={`save-manual-${type}-${card.localId}`}
                              >
                                บันทึก
                              </button>
                              {card.manualStatus[type] === 'error' && (
                                <span className="row-message row-message-error">{card.manualError[type]}</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            ))}
        </div>

        <div className="modal-foot">
          <div className="modal-foot-info">ทริป: {cards.length}</div>
          <div className="modal-actions">
            {/* Disabled while load() is in-flight — its setCards(...) REPLACES the
             * array, so a card added before the data lands would be silently lost. */}
            <button type="button" className="btn" disabled={loading} onClick={addTrip}>
              + เพิ่มทริป
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
