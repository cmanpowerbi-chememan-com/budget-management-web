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

/** Stable marker substrings inside `deadline.PastDeadlineError`'s message
 * (`"the submission deadline for fiscal_year=<Y> has passed"`, raised by both
 * `write_model.py`'s per-item write guards and `approval.py`'s submit gate —
 * same shared `app/deadline.py` implementation, ADR-0012). Split in two
 * because the fiscal year is interpolated in the middle of the string.
 * E2E edge-states 4.5 caught this: before this fix, a past-deadline save
 * fell through to the generic "no permission" message, which is misleading
 * (the user DOES have permission — the cycle is simply closed). */
const PAST_DEADLINE_DETAIL_PREFIX = 'the submission deadline for fiscal_year='
const PAST_DEADLINE_DETAIL_SUFFIX = 'has passed'

function messageForStatus(status: number, detail?: string): string {
  if (status === 403) {
    if (detail?.includes(DEPARTMENT_LOCKED_DETAIL_MARKER)) {
      return 'ฝ่ายนี้อยู่ระหว่างรออนุมัติ/อนุมัติแล้ว — แก้ไขไม่ได้'
    }
    if (detail?.includes(PAST_DEADLINE_DETAIL_PREFIX) && detail.includes(PAST_DEADLINE_DETAIL_SUFFIX)) {
      return 'พ้นกำหนดส่งงบประมาณของปีนี้แล้ว — กรุณาติดต่อผู้ดูแลระบบ'
    }
    return 'ไม่มีสิทธิ์เข้าถึงข้อมูลนี้'
  }
  if (status === 409) return 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น กรุณาโหลดข้อมูลใหม่แล้วลองอีกครั้ง'
  if (status === 400) return 'คำขอไม่ถูกต้อง'
  if (status >= 500) return 'เซิร์ฟเวอร์ขัดข้อง กรุณาลองใหม่อีกครั้ง'
  return `คำขอไม่สำเร็จ (HTTP ${status})`
}

/** How many Pydantic validation entries to spell out before collapsing the
 * rest into "และอีก N รายการ" — the first 1-2 name the culprit; more is noise. */
const MAX_VALIDATION_ENTRIES_SHOWN = 2

/** FastAPI prefixes each validation `loc` with the parameter source — users
 * know their fields, not HTTP transport locations, so it is dropped. */
const VALIDATION_LOC_SOURCES = new Set(['body', 'query', 'path', 'header', 'cookie'])

/** "body.months.m01" → "months.m01"; null when loc is absent/unusable. */
function fieldNameFromLoc(loc: unknown): string | null {
  if (!Array.isArray(loc)) return null
  const parts = loc.filter((p): p is string | number => typeof p === 'string' || typeof p === 'number')
  if (parts.length > 1 && VALIDATION_LOC_SOURCES.has(String(parts[0]))) parts.shift()
  return parts.length > 0 ? parts.join('.') : null
}

/** Thai reason for one Pydantic v2 error `type` (+ its `ctx` bound where the
 * number makes the message actionable). Covers the constraint types this
 * backend's models actually declare (`write_model.py`: ge/le on days and
 * country_group, lt on month amounts, max_length on strings, Literal on
 * template/side, required fields). An unmapped type falls back to the
 * entry's own English `msg` — still names field + reason, never bare 422. */
function thaiValidationReason(type: unknown, ctx: unknown, msg: unknown): string | null {
  const bound = (key: string): number | string | null => {
    if (ctx && typeof ctx === 'object' && key in ctx) {
      const value = (ctx as Record<string, unknown>)[key]
      if (typeof value === 'number' || typeof value === 'string') return value
    }
    return null
  }
  switch (type) {
    case 'missing':
      return 'จำเป็นต้องระบุ'
    case 'greater_than_equal': {
      const ge = bound('ge')
      if (ge === 0) return 'ต้องไม่ติดลบ'
      return ge !== null ? `ต้องไม่ต่ำกว่า ${ge}` : 'ค่าต่ำกว่าที่กำหนด'
    }
    case 'greater_than': {
      const gt = bound('gt')
      return gt !== null ? `ต้องมากกว่า ${gt}` : 'ค่าต่ำกว่าที่กำหนด'
    }
    case 'less_than_equal': {
      const le = bound('le')
      return le !== null ? `ต้องไม่เกิน ${le}` : 'ค่าเกินกำหนด'
    }
    case 'less_than': {
      const lt = bound('lt')
      return lt !== null ? `ค่าเกินกำหนด (ต้องน้อยกว่า ${lt})` : 'ค่าเกินกำหนด'
    }
    case 'string_too_long': {
      const maxLength = bound('max_length')
      return maxLength !== null ? `ยาวเกินกำหนด (ไม่เกิน ${maxLength} ตัวอักษร)` : 'ยาวเกินกำหนด'
    }
    case 'int_parsing':
    case 'int_type':
    case 'float_parsing':
    case 'float_type':
    case 'decimal_parsing':
      return 'ต้องเป็นตัวเลข'
    case 'literal_error':
    case 'enum':
      return 'ค่าไม่อยู่ในตัวเลือกที่กำหนด'
    default:
      return typeof msg === 'string' && msg ? msg : null
  }
}

/** Summarizes a FastAPI 422 `detail` array ([{loc, msg, type, ctx}, ...])
 * into ONE Thai sentence naming the offending field(s) and why — e.g.
 * "ข้อมูลไม่ถูกต้อง: days — ต้องไม่ติดลบ". `undefined` when the value is
 * not that shape (string detail, absent, malformed) so the caller can keep
 * the generic message; never throws. */
function summarizeValidationDetail(rawDetail: unknown): string | undefined {
  if (!Array.isArray(rawDetail) || rawDetail.length === 0) return undefined
  const parts: string[] = []
  for (const entry of rawDetail) {
    if (parts.length >= MAX_VALIDATION_ENTRIES_SHOWN) break
    if (!entry || typeof entry !== 'object') continue
    const { loc, msg, type, ctx } = entry as { loc?: unknown; msg?: unknown; type?: unknown; ctx?: unknown }
    const field = fieldNameFromLoc(loc)
    const reason = thaiValidationReason(type, ctx, msg)
    if (field && reason) parts.push(`${field} — ${reason}`)
    else if (field ?? reason) parts.push((field ?? reason) as string)
  }
  if (parts.length === 0) return undefined
  const remaining = rawDetail.length - MAX_VALIDATION_ENTRIES_SHOWN
  const suffix = remaining > 0 ? ` และอีก ${remaining} รายการ` : ''
  return `ข้อมูลไม่ถูกต้อง: ${parts.join(' · ')}${suffix}`
}

/** Best-effort parse of an error response's JSON body's `detail` field,
 * returned RAW (string for a plain HTTPException, array for a Pydantic
 * 422, `undefined` when absent). Never throws — an empty/non-JSON body
 * just yields `undefined`, so a malformed error body never masks the
 * original HTTP status as a crash. */
async function tryReadDetail(response: Response): Promise<unknown> {
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      return (body as { detail?: unknown }).detail
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
    const rawDetail = await tryReadDetail(response)
    const detail = typeof rawDetail === 'string' ? rawDetail : undefined
    // A 422 (FastAPI/Pydantic validation) carries `detail` as an array of
    // {loc, msg, type, ctx} — name the field(s)/reason instead of "HTTP 422";
    // every other status (and an unparseable 422) keeps its existing message.
    const message =
      (response.status === 422 ? summarizeValidationDetail(rawDetail) : undefined) ??
      messageForStatus(response.status, detail)
    throw new ApiError(response.status, message, detail)
  }

  return (await response.json()) as T
}
