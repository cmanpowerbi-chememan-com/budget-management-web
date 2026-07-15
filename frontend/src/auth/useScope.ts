import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import type { ScopeResponse, ScopeRole } from '../api/types'

export interface ScopeState {
  role: ScopeRole | null
  isAdmin: boolean
  fillCostCenters: string[]
  seeCostCenters: string[]
  loading: boolean
  error: string | null
}

const EMPTY_SCOPE = {
  role: null as ScopeRole | null,
  isAdmin: false,
  fillCostCenters: [] as string[],
  seeCostCenters: [] as string[],
}

/** Resolves the caller's RLS Fill/See cost-center scope by calling
 * `GET /scope` (ADR-0019, A3). A8+ uses this to filter/gate the grid;
 * A7 only surfaces it in the shell (role badge + CC counts). A failed
 * request degrades to an empty scope rather than crashing the shell —
 * the server is still the sole authority on access either way. */
export function useScope(): ScopeState {
  const [state, setState] = useState<ScopeState>({ ...EMPTY_SCOPE, loading: true, error: null })

  useEffect(() => {
    let cancelled = false

    apiFetch<ScopeResponse>('/scope')
      .then((data) => {
        if (cancelled) return
        setState({
          role: data.role,
          isAdmin: data.is_admin,
          fillCostCenters: data.fill_cost_centers,
          seeCostCenters: data.see_cost_centers,
          loading: false,
          error: null,
        })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const message = err instanceof Error ? err.message : 'โหลดสิทธิ์การเข้าถึงไม่สำเร็จ'
        setState({ ...EMPTY_SCOPE, loading: false, error: message })
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}
