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

  it('maps a past_deadline 403 (deadline.PastDeadlineError) to a specific Thai message distinct from department_locked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(403, { detail: 'the submission deadline for fiscal_year=2027 has passed' }),
      ),
    )

    await expect(apiFetch('/budget/rows')).rejects.toMatchObject({
      status: 403,
      message: 'พ้นกำหนดส่งงบประมาณของปีนี้แล้ว — กรุณาติดต่อผู้ดูแลระบบ',
    })
  })

  // FIX #3 — a FastAPI/Pydantic 422 carries `detail` as an ARRAY of
  // {loc, msg, type, ctx} entries; render field + Thai reason instead of
  // the bare "คำขอไม่สำเร็จ (HTTP 422)".
  describe('422 Pydantic validation mapping', () => {
    it('maps a ge=0 violation to a Thai message naming the field (body prefix dropped)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(422, {
            detail: [
              {
                loc: ['body', 'days'],
                msg: 'Input should be greater than or equal to 0',
                type: 'greater_than_equal',
                ctx: { ge: 0 },
              },
            ],
          }),
        ),
      )

      await expect(apiFetch('/budget/trip')).rejects.toMatchObject({
        status: 422,
        message: 'ข้อมูลไม่ถูกต้อง: days — ต้องไม่ติดลบ',
      })
    })

    it('maps a missing required field to จำเป็นต้องระบุ', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(422, {
            detail: [{ loc: ['body', 'traveler_empcode'], msg: 'Field required', type: 'missing' }],
          }),
        ),
      )

      await expect(apiFetch('/budget/trip')).rejects.toMatchObject({
        status: 422,
        message: 'ข้อมูลไม่ถูกต้อง: traveler_empcode — จำเป็นต้องระบุ',
      })
    })

    it('maps a month over-limit (lt bound) to ค่าเกินกำหนด with the bound', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(422, {
            detail: [
              {
                loc: ['body', 'm01'],
                msg: 'Input should be less than 100000000000',
                type: 'less_than',
                ctx: { lt: 100000000000 },
              },
            ],
          }),
        ),
      )

      await expect(apiFetch('/budget/rows')).rejects.toMatchObject({
        status: 422,
        message: 'ข้อมูลไม่ถูกต้อง: m01 — ค่าเกินกำหนด (ต้องน้อยกว่า 100000000000)',
      })
    })

    it('falls back to the entry\'s own msg for an unmapped validation type (still names the field)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(422, {
            detail: [{ loc: ['body', 'side'], msg: 'Value error, side must be COST or SGA', type: 'value_error' }],
          }),
        ),
      )

      await expect(apiFetch('/budget/trip')).rejects.toMatchObject({
        status: 422,
        message: 'ข้อมูลไม่ถูกต้อง: side — Value error, side must be COST or SGA',
      })
    })

    it('summarizes only the first 2 entries and counts the rest', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          jsonResponse(422, {
            detail: [
              { loc: ['body', 'days'], msg: 'Input should be greater than or equal to 0', type: 'greater_than_equal', ctx: { ge: 0 } },
              { loc: ['body', 'country_group'], msg: 'Input should be less than or equal to 3', type: 'less_than_equal', ctx: { le: 3 } },
              { loc: ['body', 'traveler_empcode'], msg: 'Field required', type: 'missing' },
            ],
          }),
        ),
      )

      await expect(apiFetch('/budget/trip')).rejects.toMatchObject({
        status: 422,
        message: 'ข้อมูลไม่ถูกต้อง: days — ต้องไม่ติดลบ · country_group — ต้องไม่เกิน 3 และอีก 1 รายการ',
      })
    })

    it('keeps the generic message when a 422 has no usable detail (absent or unparseable)', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(422, {})))

      await expect(apiFetch('/budget/trip')).rejects.toMatchObject({
        status: 422,
        message: 'คำขอไม่สำเร็จ (HTTP 422)',
      })
    })

    it('keeps the generic message for a 422 whose detail is a plain string (detail still captured)', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(422, { detail: 'manual 422 string' })))

      await expect(apiFetch('/budget/trip')).rejects.toMatchObject({
        status: 422,
        message: 'คำขอไม่สำเร็จ (HTTP 422)',
        detail: 'manual 422 string',
      })
    })
  })
})
