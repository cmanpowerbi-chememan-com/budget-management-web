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
  /** The backend's raw `detail` string (FastAPI `HTTPException.detail`),
   * when the error response body was JSON and carried one. Per-row error
   * surfacing (A8) shows this alongside the generic Thai `message` — the
   * backend never returns a machine error *code* over the wire (only an
   * HTTP status + a human detail string), so callers must not assume a
   * fixed set of `detail` values; an unrecognised one is just displayed
   * as-is (never a crash). `undefined` when the body was empty/unparsable.
   * ONE recognised exception (A10 gap close): a 403 whose `detail` carries
   * `write_model.DepartmentLockedError`'s stable marker phrase gets a more
   * specific Thai `message` — see `messageForStatus` below. */
  readonly detail?: string

  constructor(status: number, message: string, detail?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
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

/** Stable marker substring inside `write_model.DepartmentLockedError`'s
 * message (`"<dept>/<year> is <status> — mid-approval or approved, editing
 * is locked"`, A10 gap close) — the ONE `detail` pattern this client
 * special-cases, since a plain Fill-scope 403 shares the same HTTP status
 * but needs a different Thai message. */
const DEPARTMENT_LOCKED_DETAIL_MARKER = 'mid-approval or approved, editing is locked'

function messageForStatus(status: number, detail?: string): string {
  if (status === 403) {
    if (detail?.includes(DEPARTMENT_LOCKED_DETAIL_MARKER)) {
      return 'ฝ่ายนี้อยู่ระหว่างรออนุมัติ/อนุมัติแล้ว — แก้ไขไม่ได้'
    }
    return 'ไม่มีสิทธิ์เข้าถึงข้อมูลนี้'
  }
  if (status === 409) return 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น กรุณาโหลดข้อมูลใหม่แล้วลองอีกครั้ง'
  if (status === 400) return 'คำขอไม่ถูกต้อง'
  if (status >= 500) return 'เซิร์ฟเวอร์ขัดข้อง กรุณาลองใหม่อีกครั้ง'
  return `คำขอไม่สำเร็จ (HTTP ${status})`
}

/** Best-effort parse of an error response's JSON body's `detail` field.
 * Never throws — an empty/non-JSON body (or a `detail` that isn't a
 * string) just yields `undefined`, so a malformed error body never masks
 * the original HTTP status as a crash. */
async function tryReadDetail(response: Response): Promise<string | undefined> {
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail?: unknown }).detail
      return typeof detail === 'string' ? detail : undefined
    }
  } catch {
    // empty or non-JSON body — no detail available
  }
  return undefined
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
    const detail = await tryReadDetail(response)
    throw new ApiError(response.status, messageForStatus(response.status, detail), detail)
  }

  return (await response.json()) as T
}
