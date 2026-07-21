import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { fetchCountries, fetchTravelers } from '../api/reference'
import { createTrip, deleteTrip, fetchDetailLines, fetchTrips, saveDetailLine, updateTrip } from '../api/subform'
import type { DetailLineState, TravelerOption, TripListItem, TripState } from '../api/types'
import { formatThb, MONTH_KEYS, MONTH_LABELS, type MonthKey } from '../grid/model'
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
  countryGroupFor,
  countryOptionsWithOther,
  draftFromTripListItem,
  indexDetailLinesByTrip,
  isTripMonthActive,
  manualLineDraftFromServerLine,
  manualLineTotal,
  resolveTravelerDisplay,
  shouldWriteManualLine,
  validateTripDraft,
  type DestinationOption,
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
  /** The trip response's own traveler identity — display fallback when the
   * stored empcode is no longer in the `/reference/travelers` list (left the
   * company, moved CC). `null` for a brand-new card. */
  serverTraveler: TravelerOption | null
  perDiemMonths: Record<string, number> | null
  perDiemError: string | null
  status: Status
  errorText?: string
  manual: Record<Exclude<TravelExpenseType, 'per_diem'>, ManualLineDraft>
  manualStatus: Record<Exclude<TravelExpenseType, 'per_diem'>, Status>
  manualError: Partial<Record<Exclude<TravelExpenseType, 'per_diem'>, string>>
  /** True once a manual line's month value has changed since its last save
   * (or since load, for a never-persisted line) — drives `saveAll`'s
   * per-line write decision (`shouldWriteManualLine`) independently of the
   * trip header's own `dirty` flag. */
  manualDirty: Partial<Record<Exclude<TravelExpenseType, 'per_diem'>, boolean>>
}

const DELETE_TRIP_CONFIRM_TEXT = 'ลบทริปนี้ทั้งหมด? รายการเบี้ยเลี้ยง/ค่าเดินทางทั้งหมดของทริปจะถูกลบ'
const DELETE_TRIP_CONFLICT_MESSAGE = 'ทริปนี้ถูกแก้ไขหรือถูกลบโดยผู้อื่นไปแล้ว กรุณาตรวจสอบข้อมูลล่าสุด'
const CANCEL_UNSAVED_CONFIRM_TEXT = 'มีข้อมูลที่ยังไม่บันทึก ต้องการปิดโดยไม่บันทึก?'
/** One card/line's write hit a 409 during `saveAll` — same Thai wording the
 * single-item paths already used, now shown per-card/per-line instead of
 * auto-reloading (a batch holds too much unsaved state to discard silently). */
const SAVE_ALL_CONFLICT_MESSAGE = 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น กรุณาโหลดข้อมูลล่าสุดแล้วบันทึกอีกครั้ง'
/** Shown once, batch-wide, when ANY card/line above hit a 409 — explicit
 * reload (never auto) because reloading discards every OTHER card's
 * still-unsaved edits too. */
const SAVE_ALL_BATCH_CONFLICT_MESSAGE =
  'บางรายการถูกแก้ไขโดยผู้อื่น กด "โหลดข้อมูลล่าสุด" เพื่อดูข้อมูลปัจจุบัน (การโหลดจะล้างข้อมูลที่ยังไม่บันทึกในการ์ดอื่นด้วย)'

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
    serverTraveler: { empcode: trip.traveler_empcode, name: trip.traveler_name, position: trip.position },
    perDiemMonths: trip.per_diem_months,
    perDiemError: trip.per_diem_error,
    status: 'idle',
    manual,
    manualStatus: blankManualStatus(),
    manualError: {},
    manualDirty: {},
  }
}

/** The trip-header portion of a successful create/update — localId flips to
 * the real `existing-<id>` (never re-uses the pre-save one, matching the
 * old per-card save behavior), the draft's server-owned fields refresh from
 * the response, and the optimistic-lock token advances. `tripId`/`side` are
 * threaded from THIS SAME response by the caller — never re-read from
 * `cards` state (financial never-cut, see saveAll). */
function buildSavedTripCardPatch(card: TripCardState, saved: TripState): Partial<TripCardState> {
  return {
    localId: `existing-${saved.trip_id}`,
    draft: { ...card.draft, trip_id: saved.trip_id, side: saved.side, expected_updated_at: saved.updated_at },
    dirty: false,
    serverTraveler: { empcode: saved.traveler_empcode, name: saved.traveler_name, position: saved.position },
    perDiemMonths: saved.per_diem_months,
    perDiemError: null,
    status: 'idle',
    errorText: undefined,
  }
}

/** Thai message for a non-409 trip create/update failure — unchanged ladder
 * from the old single-item `saveTrip` catch block. */
function tripErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.status >= 500) {
    return `ไม่สามารถคำนวณเบี้ยเลี้ยงได้ — ${err.detail ?? 'ไม่พบอัตราเบี้ยเลี้ยงหรืออัตราแลกเปลี่ยนสำหรับปีนี้'}`
  }
  return err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'บันทึกทริปไม่สำเร็จ'
}

/** Thai message for a non-409 manual-line save failure — unchanged from the
 * old single-item `saveManualLine` catch block. */
function manualErrorMessage(err: unknown): string {
  return err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'บันทึกไม่สำเร็จ'
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
  /** Always mirrors the LATEST `cards` state — read by long-running async
   * handlers (delete's 409 catch) that must see edits made to a SIBLING card
   * while their own network round-trip was in flight. A plain read of the
   * `cards` closure captured at click time would be stale by the time the
   * response lands (race fixed 2026-07-19: a sibling edit mid-delete could
   * be silently discarded by the stale-closure guard's fallback `load()`). */
  const cardsRef = useRef<TripCardState[]>(cards)
  useEffect(() => {
    cardsRef.current = cards
  }, [cards])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [newTripCounter, setNewTripCounter] = useState(0)
  const [conflictMessage, setConflictMessage] = useState<string | null>(null)
  const [travelers, setTravelers] = useState<TravelerOption[]>([])
  const [destinationOptions, setDestinationOptions] = useState<DestinationOption[]>([])
  /** True only while `saveAll` is in flight — disables the whole card list
   * (via `<fieldset>`) plus the footer buttons so no edit is made mid-batch
   * and lost by the final `setCards`. */
  const [saving, setSaving] = useState(false)

  // Exactly one side in the ฝ่าย's real history → non-admins cannot
  // mis-book to the side the ฝ่าย never uses. Both sides / no history →
  // the select stays open (nothing to lock to).
  const sideLocked = !isAdmin && sideHistory.sides.length === 1

  async function load() {
    setLoading(true)
    setLoadError(null)
    try {
      const [trips, manualLines, travelerList, countryList] = await Promise.all([
        fetchTrips(costCenter, fiscalYear),
        fetchAllManualLines(costCenter, fiscalYear),
        fetchTravelers(costCenter),
        fetchCountries(),
      ])
      const index = indexDetailLinesByTrip(manualLines)
      setCards(trips.map((t) => cardFromServerTrip(t, index)))
      setTravelers(travelerList)
      setDestinationOptions(countryOptionsWithOther(countryList))
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
        serverTraveler: null,
        perDiemMonths: null,
        perDiemError: null,
        status: 'idle',
        manual: blankManualByType(),
        manualStatus: blankManualStatus(),
        manualError: {},
        manualDirty: {},
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

  function setManualMonth(localId: string, type: Exclude<TravelExpenseType, 'per_diem'>, month: MonthKey, value: number) {
    setCards((prev) =>
      prev.map((c) =>
        c.localId === localId
          ? {
              ...c,
              manual: { ...c.manual, [type]: { ...c.manual[type], months: { ...c.manual[type].months, [month]: value } } },
              manualDirty: { ...c.manualDirty, [type]: true },
            }
          : c,
      ),
    )
  }

  /** Consolidated "บันทึก & ลงบัญชี" — the ONE save path for the whole modal.
   * Iterates one snapshot of `cards` taken at click time (inputs are
   * disabled for the whole batch via `<fieldset disabled={saving}>`, so the
   * snapshot never goes stale mid-loop); every trip write's response is
   * bound to a LOCAL const and threaded DIRECTLY into that same card's
   * manual-line saves — `cards` state is never read again after an await,
   * closing the stale-closure drop a naive per-item retry would hit
   * (financial never-cut). Every card is attempted; one card's failure
   * never blocks the rest of the batch (partial-failure policy). */
  async function saveAll() {
    if (saving || loading) return
    setSaving(true)
    setConflictMessage(null)
    const snapshot = cards
    // Seeded with every card up front and replaced BY INDEX (never pushed) —
    // an unexpected throw mid-loop still leaves every earlier card's result
    // intact instead of silently dropping the tail of the batch.
    const nextCards: TripCardState[] = snapshot.slice()
    let anyWriteSucceeded = false
    let sawConflict = false
    try {
      for (let i = 0; i < snapshot.length; i++) {
        const card = snapshot[i]
        const anyManualDirty = MANUAL_TRAVEL_TYPES.some((type) => card.manualDirty?.[type])
        const isPersisted = card.draft.trip_id !== null
        const needsTripWrite = !isPersisted || card.dirty

        // Re-clicking after a partial save (or a fresh save touching only
        // some cards) skips anything already persisted-and-clean — nothing
        // to write, no needless PUT/409.
        if (isPersisted && !card.dirty && !anyManualDirty) {
          nextCards[i] = card
          continue
        }

        if (needsTripWrite) {
          const validation = validateTripDraft(card.draft)
          if (!validation.ok) {
            nextCards[i] = { ...card, status: 'error', errorText: validation.errorTh }
            continue
          }
        }

        let tripId: number
        let side: TripSide
        let patch: Partial<TripCardState>

        if (needsTripWrite) {
          try {
            const payload = buildTripPayload(card.draft)
            const saved = card.draft.trip_id === null ? await createTrip(payload) : await updateTrip(payload)
            anyWriteSucceeded = true
            tripId = saved.trip_id
            side = saved.side
            patch = buildSavedTripCardPatch(card, saved)
          } catch (err) {
            if (err instanceof ApiError && err.status === 409) {
              sawConflict = true
              nextCards[i] = { ...card, status: 'error', errorText: SAVE_ALL_CONFLICT_MESSAGE }
              continue
            }
            nextCards[i] = { ...card, status: 'error', errorText: tripErrorMessage(err) }
            continue
          }
        } else {
          // Persisted + header clean, only a manual line changed — stable,
          // non-stale values straight from the card's own draft.
          tripId = card.draft.trip_id as number
          side = card.draft.side as TripSide
          patch = { status: 'idle', errorText: undefined }
        }

        const nextManual = { ...card.manual }
        const nextManualStatus = blankManualStatus()
        const nextManualError: Partial<Record<Exclude<TravelExpenseType, 'per_diem'>, string>> = {}
        const nextManualDirty = { ...card.manualDirty }

        for (const type of MANUAL_TRAVEL_TYPES) {
          const draft = card.manual[type]
          const dirty = !!card.manualDirty?.[type]
          if (!shouldWriteManualLine(draft, dirty)) {
            // An all-zero NEW line was never written — clear its phantom
            // dirty flag too, so re-clicking save-all treats it as clean.
            if (draft.detail_id === null) nextManualDirty[type] = false
            continue
          }
          const glAccount = TRAVEL_GL_BY_TYPE_SIDE[type][side]
          try {
            const saved = await saveDetailLine(buildManualLinePayload(draft, costCenter, glAccount, fiscalYear, tripId))
            anyWriteSucceeded = true
            nextManual[type] = manualLineDraftFromServerLine(saved)
            nextManualDirty[type] = false
          } catch (err) {
            if (err instanceof ApiError && err.status === 409) {
              sawConflict = true
              nextManualStatus[type] = 'error'
              nextManualError[type] = SAVE_ALL_CONFLICT_MESSAGE
            } else {
              nextManualStatus[type] = 'error'
              nextManualError[type] = manualErrorMessage(err)
              // Double-count guard: a NEW line's create may have COMMITTED
              // server-side even though the response was lost (network
              // error) — re-fetch before the NEXT retry sends detail_id:null
              // again (which would INSERT a second row, not update the first).
              if (draft.detail_id === null) {
                try {
                  const liveLines = await fetchDetailLines(costCenter, glAccount, fiscalYear)
                  const live = liveLines.find((l) => l.trip_id === tripId)
                  if (live) nextManual[type] = manualLineDraftFromServerLine(live)
                } catch {
                  // Re-fetch also failed — leave detail_id null; a real fix
                  // needs a backend natural-key upsert (flagged, not built here).
                }
              }
            }
          }
        }

        nextCards[i] = {
          ...card,
          ...patch,
          manual: nextManual,
          manualStatus: nextManualStatus,
          manualError: nextManualError,
          manualDirty: nextManualDirty,
        }
      }

      setCards(nextCards)
      if (anyWriteSucceeded) onSaved()
      if (sawConflict) setConflictMessage(SAVE_ALL_BATCH_CONFLICT_MESSAGE)
    } finally {
      setSaving(false)
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
        // load() replaces the whole `cards` array from the server — auto-
        // calling it here would silently discard any OTHER card's unsaved
        // edits (a dirty header, or a manual line cleared to 0 but not yet
        // saved — financial never-cut). Only auto-refresh when there is
        // nothing else to lose; otherwise reuse the SAME conflict banner +
        // explicit "โหลดข้อมูลล่าสุด" button save-all's batch-conflict path
        // already renders, and leave the deleted card visibly flagged
        // (status='error') instead of wiping it.
        // cardsRef.current (NOT the `cards` closure captured at click time) —
        // a sibling card may have been edited during this delete's in-flight
        // network round-trip; the closure would still show it as clean.
        const otherCardsHaveUnsavedEdits = cardsRef.current.some(
          (c) => c.localId !== localId && (c.dirty || MANUAL_TRAVEL_TYPES.some((type) => c.manualDirty?.[type])),
        )
        if (otherCardsHaveUnsavedEdits) {
          setCards((prev) =>
            prev.map((c) => (c.localId === localId ? { ...c, status: 'error', errorText: DELETE_TRIP_CONFLICT_MESSAGE } : c)),
          )
          return
        }
        await load()
        return
      }
      const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'ลบทริปไม่สำเร็จ'
      setCards((prev) => prev.map((c) => (c.localId === localId ? { ...c, status: 'error', errorText: message } : c)))
    }
  }

  // True when the last save-all batch left ANY card or manual line red —
  // drives the footer summary line (a lone red cell deep in a horizontally
  // scrolled expense table is easy to miss otherwise).
  const hasAnyError = cards.some(
    (c) => c.status === 'error' || MANUAL_TRAVEL_TYPES.some((type) => c.manualStatus[type] === 'error'),
  )

  function onCancel() {
    if (saving) return
    const anyDirty = cards.some((c) => c.dirty || MANUAL_TRAVEL_TYPES.some((type) => c.manualDirty?.[type]))
    if (anyDirty && !window.confirm(CANCEL_UNSAVED_CONFIRM_TEXT)) return
    onClose()
  }

  return (
    <div className="modal-backdrop open" onClick={(e) => e.target === e.currentTarget && !saving && onClose()}>
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
          <button type="button" className="modal-close" aria-label="Close" disabled={saving} onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {/* Rendered ONCE per modal (not per card) — the "1 ทริป = กรอกครั้งเดียว"
            * legend explaining the auto-GL behavior below. Pure copy, no state. */}
          <div className="trip-legend" data-testid="trip-legend">
            <p className="trip-legend-head">
              1 ทริป = กรอกครั้งเดียว — ระบบลง GL ให้อัตโนมัติใน 4 ประเภทค่าใช้จ่าย
            </p>
            <div className="trip-legend-steps">
              <div className="trip-legend-step">
                <span className="trip-legend-badge">A</span>
                <span>ข้อมูลหลัก: ผู้เดินทาง → ปลายทาง → วัน → เดือน</span>
              </div>
              <div className="trip-legend-step">
                <span className="trip-legend-badge">B</span>
                <span>ค่าใช้จ่าย: เบี้ยเลี้ยงคำนวณให้ · พาหนะ/ที่พัก/อื่น กรอกยอดรวม แล้วเฉลี่ยเท่ากัน</span>
              </div>
              <div className="trip-legend-step">
                <span className="trip-legend-badge">C</span>
                <span>กด บันทึก แล้วระบบอัปเดต GL ให้เอง</span>
              </div>
            </div>
          </div>

          {conflictMessage && (
            <div className="grid-error" role="alert">
              <span>{conflictMessage}</span>
              <button type="button" className="btn" onClick={load}>
                โหลดข้อมูลล่าสุด
              </button>
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

          {!loading && !loadError && (
            // Disables every descendant input/select/button at once while a
            // save-all batch is in flight — no edit can be made mid-batch
            // and lost by the final setCards (native fieldset semantics).
            <fieldset disabled={saving} className="trip-cards-fieldset">
            {cards.map((card, idx) => {
              const traveler = resolveTravelerDisplay(card.draft.traveler_empcode, travelers, card.serverTraveler)
              // A stored traveler/destination missing from the current master
              // still needs a visible option — data must never vanish from an
              // existing trip just because the master moved on.
              const travelerFallback =
                card.draft.traveler_empcode !== '' && !travelers.some((t) => t.empcode === card.draft.traveler_empcode)
                  ? card.serverTraveler
                  : null
              const destinationFallback =
                card.draft.destination !== null && !destinationOptions.some((o) => o.country === card.draft.destination)
                  ? card.draft.destination
                  : null
              return (
              <div key={card.localId} className="trip-card" data-testid={`trip-card-${card.localId}`}>
                <div className="trip-card-head">
                  <span className="trip-idx">{String(idx + 1).padStart(2, '0')}</span>
                  <span>{traveler.name ?? 'ผู้เดินทางใหม่'}</span>
                  <button
                    type="button"
                    className="action-btn"
                    aria-label="ลบทริป"
                    title="ลบทริป"
                    disabled={card.status === 'deleting'}
                    onClick={() => deleteTripCard(card.localId)}
                  >
                    {card.status === 'deleting' ? (
                      '…'
                    ) : (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                      </svg>
                    )}
                  </button>
                </div>
                <div className="trip-card-body">
                  {card.status === 'error' && card.errorText && (
                    <div className="row-message row-message-error" data-testid={`trip-card-error-${card.localId}`}>
                      {card.errorText}
                    </div>
                  )}
                  <div className="trip-section-label">A — ข้อมูลหลัก (กรอกครั้งเดียว)</div>
                  <div className="trip-field-grid">
                    <label>
                      TRAVELER NAME · SAP
                      <select
                        aria-label={`traveler_empcode ${card.localId}`}
                        value={card.draft.traveler_empcode}
                        onChange={(e) => updateTripField(card.localId, (d) => ({ ...d, traveler_empcode: e.target.value }))}
                      >
                        {card.draft.traveler_empcode === '' && (
                          <option value="" disabled>
                            — เลือกผู้เดินทาง —
                          </option>
                        )}
                        {travelerFallback && <option value={travelerFallback.empcode}>{travelerFallback.name}</option>}
                        {travelers.map((t) => (
                          <option key={t.empcode} value={t.empcode}>
                            {t.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      POSITION
                      {/* Read-only by design: position comes from the traveler
                        * master / trip response and drives per-diem server-side. */}
                      <span className="trip-readonly" data-testid={`position-${card.localId}`}>
                        {traveler.position ?? '—'}
                      </span>
                    </label>
                    <label>
                      DESTINATION · ปลายทาง
                      {/* Picking a country ALSO sets country_group (1/2/3) — the
                        * old manual group select is gone: a hand-picked wrong
                        * group meant a wrong per-diem rate. A legacy free-typed
                        * destination keeps its stored group until re-picked. */}
                      <select
                        aria-label={`destination ${card.localId}`}
                        value={card.draft.destination ?? ''}
                        onChange={(e) =>
                          updateTripField(card.localId, (d) => {
                            const group = countryGroupFor(destinationOptions, e.target.value)
                            return { ...d, destination: e.target.value || null, country_group: group ?? d.country_group }
                          })
                        }
                      >
                        {card.draft.destination === null && (
                          <option value="" disabled>
                            — เลือกปลายทาง —
                          </option>
                        )}
                        {destinationFallback && <option value={destinationFallback}>{destinationFallback}</option>}
                        {destinationOptions.map((o) => (
                          <option key={o.country} value={o.country}>
                            {o.country}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      PROJECT · โครงการ
                      <input
                        aria-label={`project ${card.localId}`}
                        value={card.draft.project ?? ''}
                        onChange={(e) => updateTripField(card.localId, (d) => ({ ...d, project: e.target.value }))}
                      />
                    </label>
                    <label>
                      PURPOSE · วัตถุประสงค์
                      <input
                        aria-label={`purpose ${card.localId}`}
                        value={card.draft.purpose ?? ''}
                        onChange={(e) => updateTripField(card.localId, (d) => ({ ...d, purpose: e.target.value || null }))}
                      />
                    </label>
                    <label>
                      TOTAL DAYS / YEAR
                      <input
                        aria-label={`days ${card.localId}`}
                        inputMode="numeric"
                        value={card.draft.days || ''}
                        onChange={(e) =>
                          updateTripField(card.localId, (d) => ({ ...d, days: Number(e.target.value.replace(/[^0-9]/g, '')) || 0 }))
                        }
                      />
                    </label>
                    {/* ฝั่งบัญชี — kept exactly as-is (locked/derived select, ADR
                      * per jakkaritw): only its position in the grid changed. */}
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
                          {MONTH_LABELS[m]}
                        </button>
                      )
                    })}
                  </div>

                  {/* Section B header — no fx field exists yet on the trip model
                    * (TripDraft/TripInput/TripListItem all lack it), so the FX
                    * suffix from the mockup is intentionally omitted rather than
                    * showing a fabricated number (never-cut). */}
                  <div className="trip-section-label">B — ค่าใช้จ่าย 4 ประเภท</div>

                  {/* Expense table renders for UNSAVED trips too (Option B) —
                    * "บันทึก & ลงบัญชี" creates the trip AND its manual lines in
                    * one click; GL chips read "—" until a side is picked. */}
                  <>
                      <div className="trip-exp-scroll">
                        <table className="trip-exp-table">
                        <thead>
                          <tr>
                            <th>ประเภทค่าใช้จ่าย</th>
                            <th>GL</th>
                            {MONTH_KEYS.map((m) => (
                              <th key={m}>{MONTH_LABELS[m]}</th>
                            ))}
                            <th>ยอดรวม/ทริป</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {/* Per-diem row — ALWAYS read-only: the value shown is
                            * either the server's last response or the pending
                            * state, NEVER computed here (financial never-cut). */}
                          <tr className="exp-per-diem-row" data-testid={`per-diem-row-${card.localId}`}>
                            <td className="exp-type-name">
                              เบี้ยเลี้ยง Per Diem
                              <div className="exp-perdiem-sub">
                                {card.perDiemError ? (
                                  <span className="row-message row-message-error">
                                    ไม่สามารถคำนวณเบี้ยเลี้ยงได้ — {card.perDiemError}
                                  </span>
                                ) : card.dirty || !card.perDiemMonths ? (
                                  <span>ระบบจะคำนวณให้หลังกดบันทึก</span>
                                ) : (
                                  <span>{card.draft.days} วัน · เฉลี่ยจากเซิร์ฟเวอร์</span>
                                )}
                              </div>
                            </td>
                            <td>
                              <span className="exp-gl-chip">
                                {card.draft.side ? TRAVEL_GL_BY_TYPE_SIDE.per_diem[card.draft.side] : '—'}
                              </span>
                            </td>
                            {MONTH_KEYS.map((m) => {
                              const active = isTripMonthActive(card.draft.travel_months, m)
                              return (
                                <td key={m}>
                                  {active ? (
                                    <span
                                      className="exp-perdiem-value"
                                      title="คำนวณโดยเซิร์ฟเวอร์ — แก้ไขไม่ได้"
                                      data-testid={`per-diem-value-${m}-${card.localId}`}
                                    >
                                      {card.perDiemMonths ? formatThb(card.perDiemMonths[m] ?? 0) : '—'}
                                    </span>
                                  ) : (
                                    <span title="เดือนนี้ไม่ได้เลือกเดินทาง">—</span>
                                  )}
                                </td>
                              )
                            })}
                            <td className="exp-row-total">
                              {card.perDiemMonths
                                ? formatThb(Object.values(card.perDiemMonths).reduce((s, v) => s + v, 0))
                                : '—'}
                            </td>
                            <td />
                          </tr>
                          {MANUAL_TRAVEL_TYPES.map((type) => (
                            <tr key={type}>
                              <td className="exp-type-name">{TRAVEL_TYPE_LABEL_TH[type]}</td>
                              <td>
                                <span className="exp-gl-chip">
                                  {card.draft.side ? TRAVEL_GL_BY_TYPE_SIDE[type][card.draft.side] : '—'}
                                </span>
                              </td>
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
                              <td className="exp-row-total">{formatThb(manualLineTotal(card.manual[type]))}</td>
                              {/* No per-row save button — "บันทึก & ลงบัญชี" in the
                                * footer saves every dirty line in one click. This
                                * cell surfaces that one line's own outcome instead. */}
                              <td>
                                {card.manualStatus[type] === 'error' && (
                                  <span className="row-message row-message-error" data-testid={`manual-error-${type}-${card.localId}`}>
                                    {card.manualError[type]}
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      </div>

                      {/* รายละเอียด — no note/detail field exists anywhere in the
                        * trip data model (TripDraft/TripInput/TripListItem, or
                        * ManualLineDraft) yet. Rendered disabled per the task's
                        * explicit instruction rather than inventing a backend
                        * field or silently persisting nothing. */}
                      <div className="trip-detail-row">
                        <label className="trip-detail-label" htmlFor={`trip-detail-${card.localId}`}>
                          รายละเอียด
                        </label>
                        <input
                          id={`trip-detail-${card.localId}`}
                          className="detail-input"
                          type="text"
                          placeholder="ระบุรายละเอียด เช่น ค่าวีซ่า / ประกัน"
                          disabled
                          title="(ยังไม่รองรับ — mockup placeholder)"
                          aria-label={`trip-detail-note ${card.localId}`}
                        />
                      </div>
                  </>
                </div>
              </div>
              )
            })}
            </fieldset>
          )}
        </div>

        <div className="modal-foot">
          <div className="modal-foot-info">
            ทริป: {cards.length}
            {hasAnyError && (
              <span className="row-message row-message-error" data-testid="save-all-error-summary">
                {' '}
                · บางรายการบันทึกไม่สำเร็จ — ดูข้อความสีแดงในการ์ดที่มีปัญหา
              </span>
            )}
          </div>
          <div className="modal-actions">
            <button type="button" className="btn" disabled={loading || saving} onClick={onCancel}>
              ยกเลิก
            </button>
            {/* Disabled while load() is in-flight — its setCards(...) REPLACES the
             * array, so a card added before the data lands would be silently lost. */}
            <button type="button" className="btn" disabled={loading || saving} onClick={addTrip}>
              + เพิ่มทริป
            </button>
            <button
              type="button"
              className="btn btn-export"
              disabled={loading || saving || cards.length === 0}
              onClick={saveAll}
              data-testid="save-all"
            >
              {saving ? 'กำลังบันทึก…' : 'บันทึก & ลงบัญชี'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
