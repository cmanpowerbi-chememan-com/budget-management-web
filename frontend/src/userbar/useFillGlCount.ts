import { useEffect, useState } from 'react'
import { fetchBudgetGrid } from '../api/budget'
import { countDistinctFillGlAccounts } from './model'

export interface FillGlCountState {
  /** `null` while loading OR after a failed fetch — the header shows "…"
   * while `loading` and "—" on failure, never a fabricated number. */
  count: number | null
  loading: boolean
}

/** Distinct GL accounts across the caller's Fill cost centers, for the
 * header's "GL Codes" pill. Sourced from the SAME `GET /budget` endpoint
 * the grid already calls (no backend change) — fetched ONCE for the given
 * year with no department/cost_center filter, independent of whatever
 * ฝ่าย/year the user later picks in the grid below (this is a scope
 * indicator, not a live grid stat). Skips the fetch entirely when the
 * caller has no Fill CCs (See-only/no-scope callers, or a pure admin). */
export function useFillGlCount(year: number, fillCostCenters: string[]): FillGlCountState {
  const key = fillCostCenters.join(',')
  const [state, setState] = useState<FillGlCountState>({ count: null, loading: fillCostCenters.length > 0 })

  useEffect(() => {
    if (fillCostCenters.length === 0) {
      setState({ count: 0, loading: false })
      return
    }

    let cancelled = false
    setState({ count: null, loading: true })

    fetchBudgetGrid({ year, adminViewEnabled: false })
      .then((rows) => {
        if (cancelled) return
        setState({ count: countDistinctFillGlAccounts(rows, fillCostCenters), loading: false })
      })
      .catch(() => {
        if (cancelled) return
        setState({ count: null, loading: false })
      })

    return () => {
      cancelled = true
    }
    // fillCostCenters is compared via `key` (its joined value) — the array
    // reference itself changes every parent render, `key` doesn't.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, key])

  return state
}
