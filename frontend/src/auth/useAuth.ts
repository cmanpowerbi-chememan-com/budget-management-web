import { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import type { MeResponse } from '../api/types'

export interface AuthState {
  email: string | null
  loading: boolean
  error: string | null
}

/** Resolves the logged-in user by calling `GET /me` on mount (ADR-0004).
 * The platform (Entra Easy Auth) already validated the session before the
 * request reached the backend; a 401 here means "not logged in" and
 * `apiFetch` already redirects to the Easy Auth login page — this hook
 * only surfaces the resulting state to the shell. */
export function useAuth(): AuthState {
  const [state, setState] = useState<AuthState>({ email: null, loading: true, error: null })

  useEffect(() => {
    let cancelled = false

    apiFetch<MeResponse>('/me')
      .then((data) => {
        if (!cancelled) setState({ email: data.email, loading: false, error: null })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const message = err instanceof Error ? err.message : 'โหลดข้อมูลผู้ใช้ไม่สำเร็จ'
        setState({ email: null, loading: false, error: message })
      })

    return () => {
      cancelled = true
    }
  }, [])

  return state
}
