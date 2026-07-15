/** Typed calls to the A9 subform endpoints (5 special-GL detail groups +
 * Trip Manager), built on the shared `apiFetch`. Mirrors `budget.ts`'s
 * shape: one function per endpoint, no local caching/state. */
import { apiFetch } from './client'
import type { DetailLineInput, DetailLineState, TripInput, TripListItem, TripState } from './types'

/** `GET /budget/detail` — existing lines for one (cost_center, gl_account,
 * fiscal_year) key. Used both by the 5 non-travel special-GL subforms
 * (their whole list) and by Trip Manager (per travel type × side GL, to
 * find the manually-entered lines already attached to a `trip_id`). */
export function fetchDetailLines(costCenter: string, glAccount: string, fiscalYear: number): Promise<DetailLineState[]> {
  const search = new URLSearchParams({ cost_center: costCenter, gl_account: glAccount, fiscal_year: String(fiscalYear) })
  return apiFetch<DetailLineState[]>(`/budget/detail?${search.toString()}`)
}

/** `PUT /budget/detail` — create (`detail_id: null`) or update one special-GL
 * detail line. Throws `ApiError` on 400/403/409 — the caller (DetailSubform)
 * surfaces it against that one row only. */
export function saveDetailLine(payload: DetailLineInput): Promise<DetailLineState> {
  return apiFetch<DetailLineState>('/budget/detail', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** `GET /budget/trip` — every trip for one (cost_center, fiscal_year), both
 * COST and SGA sides together; each trip carries its own `side`. */
export function fetchTrips(costCenter: string, fiscalYear: number): Promise<TripListItem[]> {
  const search = new URLSearchParams({ cost_center: costCenter, fiscal_year: String(fiscalYear) })
  return apiFetch<TripListItem[]>(`/budget/trip?${search.toString()}`)
}

/** `POST /budget/trip` — create a new trip (per-diem derived server-side). */
export function createTrip(payload: Omit<TripInput, 'trip_id' | 'expected_updated_at'>): Promise<TripState> {
  return apiFetch<TripState>('/budget/trip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...payload, trip_id: null, expected_updated_at: null }),
  })
}

/** `PUT /budget/trip` — update an existing trip (optimistic lock via
 * `expected_updated_at`; a `side` flip re-homes its lines server-side). */
export function updateTrip(payload: TripInput): Promise<TripState> {
  return apiFetch<TripState>('/budget/trip', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** `DELETE /budget/detail` — remove one special-GL detail line by id.
 * `expectedUpdatedAt` is the same optimistic-lock token every other write
 * carries; a stale token throws `ApiError(409)` and deletes nothing. The
 * server recomputes the parent cell (kept, zeroed) after the delete — the
 * caller should refetch/refresh after this resolves. */
export function deleteDetailLine(detailId: number, expectedUpdatedAt: string): Promise<{ ok: boolean }> {
  const search = new URLSearchParams({ detail_id: String(detailId), expected_updated_at: expectedUpdatedAt })
  return apiFetch<{ ok: boolean }>(`/budget/detail?${search.toString()}`, { method: 'DELETE' })
}

/** `DELETE /budget/trip` — remove one trip AND every one of its lines
 * (per-diem + the 3 manual expense types) in a single call; the server
 * recomputes all 4 of that side's travel-GL parent cells. */
export function deleteTrip(tripId: number, expectedUpdatedAt: string): Promise<{ ok: boolean }> {
  const search = new URLSearchParams({ trip_id: String(tripId), expected_updated_at: expectedUpdatedAt })
  return apiFetch<{ ok: boolean }>(`/budget/trip?${search.toString()}`, { method: 'DELETE' })
}
