/** Typed calls to the `/reference/*` endpoints (traveler + country masters
 * for the Trip Manager dropdowns), built on the shared `apiFetch`. Mirrors
 * `budget.ts`/`subform.ts`'s shape: one function per endpoint, no caching. */
import { apiFetch } from './client'
import type { CountryOption, TravelerOption } from './types'

/** `GET /reference/travelers?cost_center=` — who can be picked as the
 * traveler for a trip on this cost center (label = name, value = empcode;
 * `position` is displayed read-only and drives per-diem server-side). */
export function fetchTravelers(costCenter: string): Promise<TravelerOption[]> {
  const search = new URLSearchParams({ cost_center: costCenter })
  return apiFetch<TravelerOption[]>(`/reference/travelers?${search.toString()}`)
}

/** `GET /reference/countries` — destination country master (groups 1
 * domestic / 2 asian only; group 3 "อื่นๆ (Other)" is appended client-side). */
export function fetchCountries(): Promise<CountryOption[]> {
  return apiFetch<CountryOption[]>('/reference/countries')
}
