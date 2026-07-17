import { useEffect, useState } from 'react'
import { fetchDepartments } from '../api/budget'
import type { DepartmentRow } from '../api/types'

export interface OwnDepartmentsState {
  departments: DepartmentRow[]
  loading: boolean
}

/** The caller's OWN `GET /scope/departments` rows — always fetched with
 * `admin_view_enabled=false`, independent of whatever admin-view toggle
 * `BudgetGrid` is in. The header always reflects the caller's real
 * personal scope (a dual-role admin's own ฝ่าย never changes just because
 * they flip the grid's admin toggle). Pass `enabled=false` to skip the
 * fetch entirely — pure admins (ADR-0014, no Fill/See CCs at all) have no
 * personal scope for the header to show. */
export function useOwnDepartments(enabled: boolean): OwnDepartmentsState {
  const [state, setState] = useState<OwnDepartmentsState>({ departments: [], loading: enabled })

  useEffect(() => {
    if (!enabled) {
      setState({ departments: [], loading: false })
      return
    }

    let cancelled = false
    setState({ departments: [], loading: true })

    fetchDepartments(false)
      .then((data) => {
        if (!cancelled) setState({ departments: data, loading: false })
      })
      .catch(() => {
        if (!cancelled) setState({ departments: [], loading: false })
      })

    return () => {
      cancelled = true
    }
  }, [enabled])

  return state
}
