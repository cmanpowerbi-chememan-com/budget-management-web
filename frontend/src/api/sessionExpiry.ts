/** Session-expiry latch — shared between `api/client.ts` (plain module, no
 * React) and `auth/SessionExpiredDialog.tsx` (the React consumer).
 *
 * A dead Easy Auth session (the 14h cookie expired, ADR-0004) makes every
 * in-flight request fail at once — the grid alone fires many concurrent
 * calls. This latch is "first-call-wins": the first failure flips it and
 * notifies subscribers; every later failure still throws its own
 * `ApiError` (see client.ts) but is a no-op here, so N concurrent failures
 * raise exactly ONE dialog instead of N.
 *
 * Lives in `api/` (not `auth/`) because it is derived purely from a fetch
 * `Response` shape, same as `ApiError`/`buildLoginRedirectUrl` next to it —
 * `auth/` holds the React-facing pieces (hooks, the dialog component). */

export const SESSION_EXPIRED_MESSAGE =
  'หมดเวลาการเข้าใช้งาน (ระบบให้ล็อกอินได้ครั้งละ 14 ชั่วโมง) กรุณา login ใหม่อีกครั้ง'

type Listener = () => void

let expired = false
const listeners = new Set<Listener>()

/** Flips the latch and notifies subscribers. No-op after the first call. */
export function raiseSessionExpired(): void {
  if (expired) return
  expired = true
  for (const listener of listeners) listener()
}

export function isSessionExpired(): boolean {
  return expired
}

/** Registers `listener`, returns an unsubscribe function — shape expected
 * by React's `useSyncExternalStore`. */
export function subscribeSessionExpired(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Test-only reset. Module state otherwise leaks between tests in the same
 * file (vitest isolates per FILE, not per test) — call from a shared
 * `afterEach` (see `frontend/src/test/setup.ts`). */
export function resetSessionExpiredForTests(): void {
  expired = false
  listeners.clear()
}
