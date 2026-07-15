import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, buildLoginRedirectUrl } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('buildLoginRedirectUrl', () => {
  it('carries the current page as post_login_redirect_uri (Easy Auth convention, ADR-0004)', () => {
    const current = 'http://localhost/?dept=ฝ่ายบัญชี&year=2026'
    expect(buildLoginRedirectUrl(current)).toBe(
      `/.auth/login/aad?post_login_redirect_uri=${encodeURIComponent(current)}`,
    )
  })
})

describe('apiFetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns the parsed JSON body on a 200 response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { hello: 'world' })))

    await expect(apiFetch('/health')).resolves.toEqual({ hello: 'world' })
  })

  it('on a 401, calls onUnauthorized then throws a 401 ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, {})))
    const onUnauthorized = vi.fn()

    await expect(apiFetch('/me', { onUnauthorized })).rejects.toThrow(ApiError)
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('maps a 403 response to a forbidden ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(403, {})))

    await expect(apiFetch('/budget')).rejects.toMatchObject({ status: 403 })
  })

  it('maps a 5xx response to a server-error ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(502, {})))

    await expect(apiFetch('/budget')).rejects.toMatchObject({ status: 502 })
  })

  it('maps a network failure to a connectivity ApiError instead of throwing raw', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    )

    await expect(apiFetch('/health')).rejects.toMatchObject({ status: 0 })
  })

  it('maps a 409 response to a conflict ApiError with a Thai message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, { detail: 'row changed' })))

    await expect(apiFetch('/budget/rows')).rejects.toMatchObject({ status: 409 })
  })

  it('captures the backend detail string from an error response body (per-row error surfacing)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(403, { detail: 'CC1 is not in your Fill scope' })),
    )

    await expect(apiFetch('/budget/rows')).rejects.toMatchObject({
      status: 403,
      detail: 'CC1 is not in your Fill scope',
    })
  })

  it('tolerates an error response with an unparsable/empty body (detail undefined, never crashes)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => {
          throw new Error('not json')
        },
      } as unknown as Response),
    )

    await expect(apiFetch('/budget/rows')).rejects.toMatchObject({ status: 400, detail: undefined })
  })

  it('maps a department_locked 403 (A10 gap close) to a specific Thai message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(403, { detail: 'ฝ่ายบัญชี/2027 is PENDING_APPROVER1 — mid-approval or approved, editing is locked' }),
      ),
    )

    await expect(apiFetch('/budget/rows')).rejects.toMatchObject({
      status: 403,
      message: 'ฝ่ายนี้อยู่ระหว่างรออนุมัติ/อนุมัติแล้ว — แก้ไขไม่ได้',
    })
  })

  it('keeps the generic forbidden Thai message for a plain (non-department-locked) 403', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(403, { detail: 'CC1 is not in your Fill scope' })),
    )

    await expect(apiFetch('/budget/rows')).rejects.toMatchObject({
      status: 403,
      message: 'ไม่มีสิทธิ์เข้าถึงข้อมูลนี้',
    })
  })
})
