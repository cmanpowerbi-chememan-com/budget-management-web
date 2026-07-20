import { afterEach, describe, expect, it, vi } from 'vitest'
import { deleteRow, fetchBudgetGrid, fetchDepartments, fetchGlAccounts, saveRow } from './budget'
import { ApiError } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('fetchBudgetGrid', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /budget with year and optional filters as query params', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, []))
    vi.stubGlobal('fetch', fetchSpy)

    await fetchBudgetGrid({ year: 2027, department: 'ฝ่ายบัญชี' })

    const calledUrl = String(fetchSpy.mock.calls[0][0])
    expect(calledUrl).toContain('/budget?')
    expect(calledUrl).toContain('year=2027')
    expect(calledUrl).toContain(encodeURIComponent('ฝ่ายบัญชี'))
  })

  it('omits department/cost_center params when not given', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, []))
    vi.stubGlobal('fetch', fetchSpy)

    await fetchBudgetGrid({ year: 2027 })

    const calledUrl = String(fetchSpy.mock.calls[0][0])
    expect(calledUrl).not.toContain('department=')
    expect(calledUrl).not.toContain('cost_center=')
  })

  it('returns the parsed rows on success', async () => {
    const rows = [{ cost_center: 'CC1', gl_account: 'GL1', editable: true }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, rows)))

    await expect(fetchBudgetGrid({ year: 2027 })).resolves.toEqual(rows)
  })
})

describe('fetchGlAccounts', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /budget/gl-accounts and returns the list', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, [{ gl_code: '1', is_special: false }]))
    vi.stubGlobal('fetch', fetchSpy)

    const result = await fetchGlAccounts()

    expect(String(fetchSpy.mock.calls[0][0])).toContain('/budget/gl-accounts')
    expect(result).toEqual([{ gl_code: '1', is_special: false }])
  })
})

describe('fetchDepartments', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /scope/departments', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, []))
    vi.stubGlobal('fetch', fetchSpy)

    await fetchDepartments()

    expect(String(fetchSpy.mock.calls[0][0])).toContain('/scope/departments')
  })
})

describe('saveRow', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('PUTs to /budget/rows with the full payload and returns the saved state', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse(200, { cost_center: 'CC1', gl_account: 'GL1', total_year: 100 }),
    )
    vi.stubGlobal('fetch', fetchSpy)

    const payload = {
      cost_center: 'CC1',
      gl_account: 'GL1',
      fiscal_year: 2027,
      m01: 100,
      m02: 0,
      m03: 0,
      m04: 0,
      m05: 0,
      m06: 0,
      m07: 0,
      m08: 0,
      m09: 0,
      m10: 0,
      m11: 0,
      m12: 0,
      remark: null,
      expected_updated_at: null,
    }

    const result = await saveRow(payload)

    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/budget/rows')
    expect((init as RequestInit).method).toBe('PUT')
    expect(JSON.parse((init as RequestInit).body as string)).toEqual(payload)
    expect(result.total_year).toBe(100)
  })

  it('propagates a 409 ApiError on lock conflict (caller decides refetch/message)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(409, { detail: 'changed by someone else' })),
    )

    await expect(
      saveRow({
        cost_center: 'CC1',
        gl_account: 'GL1',
        fiscal_year: 2027,
        m01: 0,
        m02: 0,
        m03: 0,
        m04: 0,
        m05: 0,
        m06: 0,
        m07: 0,
        m08: 0,
        m09: 0,
        m10: 0,
        m11: 0,
        m12: 0,
        remark: null,
        expected_updated_at: '2026-01-01T00:00:00Z',
      }),
    ).rejects.toBeInstanceOf(ApiError)
  })
})

describe('deleteRow', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('DELETEs /budget/rows with cost_center/gl_account/fiscal_year/expected_updated_at as query params', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    vi.stubGlobal('fetch', fetchSpy)

    const result = await deleteRow({
      costCenter: 'CC1', glAccount: 'GL1', fiscalYear: 2027, expectedUpdatedAt: '2026-01-01T00:00:00Z',
    })

    const [url, init] = fetchSpy.mock.calls[0]
    const calledUrl = String(url)
    expect(calledUrl).toContain('/budget/rows?')
    expect(calledUrl).toContain('cost_center=CC1')
    expect(calledUrl).toContain('gl_account=GL1')
    expect(calledUrl).toContain('fiscal_year=2027')
    expect(calledUrl).toContain(encodeURIComponent('2026-01-01T00:00:00Z'))
    expect((init as RequestInit).method).toBe('DELETE')
    expect(result.ok).toBe(true)
  })

  it('propagates a 409 ApiError on lock conflict', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(409, { detail: 'changed by someone else' })),
    )

    await expect(
      deleteRow({ costCenter: 'CC1', glAccount: 'GL1', fiscalYear: 2027, expectedUpdatedAt: '2026-01-01T00:00:00Z' }),
    ).rejects.toBeInstanceOf(ApiError)
  })
})
