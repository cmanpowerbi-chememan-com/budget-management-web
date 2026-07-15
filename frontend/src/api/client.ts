/** Typed API client for the FastAPI backend (ADR-0002).
 *
 * Centralizes two things every caller needs identically:
 * - Entra Easy Auth's convention (ADR-0004): the platform injects identity
 *   server-side; a 401 here just means "not logged in yet" and the fix is
 *   redirecting to `/.auth/login/aad`. The deep-link (ADR-0016) is
 *   convenience-only — this redirect never grants access, the server still
 *   decides on every request.
 * - Consistent error shapes for 403/5xx so hooks never each reinvent fetch
 *   error handling.
 */

const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Builds the Easy Auth login redirect URL, carrying the current page back
 * as `post_login_redirect_uri` so the user returns to where they were
 * (deep-link query params included). Pure — no navigation side effect,
 * kept separate from `apiFetch` so it is trivially unit-testable. */
export function buildLoginRedirectUrl(currentHref: string): string {
  return `/.auth/login/aad?post_login_redirect_uri=${encodeURIComponent(currentHref)}`
}

function defaultOnUnauthorized(): void {
  window.location.href = buildLoginRedirectUrl(window.location.href)
}

function messageForStatus(status: number): string {
  if (status === 403) return 'ไม่มีสิทธิ์เข้าถึงข้อมูลนี้'
  if (status >= 500) return 'เซิร์ฟเวอร์ขัดข้อง กรุณาลองใหม่อีกครั้ง'
  return `คำขอไม่สำเร็จ (HTTP ${status})`
}

export interface ApiFetchOptions extends RequestInit {
  /** Called on a 401 response, before ApiError is thrown. Defaults to
   * redirecting to the Easy Auth login page — tests inject a spy instead
   * of letting jsdom navigate. */
  onUnauthorized?: () => void
}

/** Calls the backend and returns the parsed JSON body, or throws
 * `ApiError`. A 401 triggers `onUnauthorized` (real redirect by default)
 * before throwing, so callers never need to special-case auth. */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { onUnauthorized = defaultOnUnauthorized, ...init } = options

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { credentials: 'include', ...init })
  } catch {
    throw new ApiError(0, 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ต')
  }

  if (response.status === 401) {
    onUnauthorized()
    throw new ApiError(401, 'ยังไม่ได้เข้าสู่ระบบ')
  }

  if (!response.ok) {
    throw new ApiError(response.status, messageForStatus(response.status))
  }

  return (await response.json()) as T
}
