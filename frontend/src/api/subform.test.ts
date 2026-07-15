import { afterEach, describe, expect, it, vi } from 'vitest'
import { createTrip, deleteDetailLine, deleteTrip, fetchDetailLines, fetchTrips, saveDetailLine, updateTrip } from './subform'
import { ApiError } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('fetchDetailLines', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /budget/detail with cost_center, gl_account, fiscal_year as query params', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, []))
    vi.stubGlobal('fetch', fetchSpy)

    await fetchDetailLines('CC1', 'GL1', 2027)

    const calledUrl = String(fetchSpy.mock.calls[0][0])
    expect(calledUrl).toContain('/budget/detail?')
    expect(calledUrl).toContain('cost_center=CC1')
    expect(calledUrl).toContain('gl_account=GL1')
    expect(calledUrl).toContain('fiscal_year=2027')
  })

  it('returns the parsed lines on success', async () => {
    const lines = [{ detail_id: 1, cost_center: 'CC1' }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, lines)))
    await expect(fetchDetailLines('CC1', 'GL1', 2027)).resolves.toEqual(lines)
  })
})

describe('saveDetailLine', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('PUTs to /budget/detail with the full payload', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { detail_id: 1 }))
    vi.stubGlobal('fetch', fetchSpy)

    const payload = {
      detail_id: null,
      cost_center: 'CC1',
      gl_account: 'GL1',
      fiscal_year: 2027,
      trip_id: null,
      line_label: null,
      meta_json: { ประเภทการรับรอง: 'Customer' },
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
      expected_updated_at: null,
    }

    await saveDetailLine(payload)

    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/budget/detail')
    expect((init as RequestInit).method).toBe('PUT')
    expect(JSON.parse((init as RequestInit).body as string)).toEqual(payload)
  })

  it('propagates a 409 ApiError on lock conflict', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, { detail: 'changed by someone else' })))
    await expect(
      saveDetailLine({
        detail_id: 1,
        cost_center: 'CC1',
        gl_account: 'GL1',
        fiscal_year: 2027,
        trip_id: null,
        line_label: null,
        meta_json: null,
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
        expected_updated_at: '2026-01-01T00:00:00Z',
      }),
    ).rejects.toBeInstanceOf(ApiError)
  })
})

describe('fetchTrips', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /budget/trip with cost_center and fiscal_year', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, []))
    vi.stubGlobal('fetch', fetchSpy)

    await fetchTrips('CC1', 2027)

    const calledUrl = String(fetchSpy.mock.calls[0][0])
    expect(calledUrl).toContain('/budget/trip?')
    expect(calledUrl).toContain('cost_center=CC1')
    expect(calledUrl).toContain('fiscal_year=2027')
  })
})

describe('createTrip', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('POSTs to /budget/trip with trip_id and expected_updated_at forced to null', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { trip_id: 10 }))
    vi.stubGlobal('fetch', fetchSpy)

    await createTrip({
      cost_center: 'CC1',
      fiscal_year: 2027,
      traveler_empcode: 'E1',
      destination: 'Japan',
      country_group: 2,
      days: 5,
      travel_months: ['02', '03'],
      purpose: null,
      side: 'COST',
    })

    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/budget/trip')
    expect((init as RequestInit).method).toBe('POST')
    const body = JSON.parse((init as RequestInit).body as string)
    expect(body.trip_id).toBeNull()
    expect(body.expected_updated_at).toBeNull()
    expect(body.traveler_empcode).toBe('E1')
  })
})

describe('updateTrip', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('PUTs to /budget/trip with the full payload including trip_id/expected_updated_at', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { trip_id: 10 }))
    vi.stubGlobal('fetch', fetchSpy)

    const payload = {
      trip_id: 10,
      cost_center: 'CC1',
      fiscal_year: 2027,
      traveler_empcode: 'E1',
      destination: 'Japan',
      country_group: 2 as const,
      days: 5,
      travel_months: ['02', '03'],
      purpose: null,
      side: 'COST' as const,
      expected_updated_at: '2026-01-01T00:00:00Z',
    }

    await updateTrip(payload)

    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/budget/trip')
    expect((init as RequestInit).method).toBe('PUT')
    expect(JSON.parse((init as RequestInit).body as string)).toEqual(payload)
  })
})

describe('deleteDetailLine', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('DELETEs /budget/detail with detail_id and expected_updated_at as query params', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    vi.stubGlobal('fetch', fetchSpy)

    await deleteDetailLine(5, '2026-01-01T00:00:00Z')

    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/budget/detail?')
    expect(String(url)).toContain('detail_id=5')
    expect(String(url)).toContain('expected_updated_at=')
    expect((init as RequestInit).method).toBe('DELETE')
  })

  it('propagates a 409 ApiError on a stale lock token', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, { detail: 'changed by someone else' })))
    await expect(deleteDetailLine(5, '2026-01-01T00:00:00Z')).rejects.toBeInstanceOf(ApiError)
  })
})

describe('deleteTrip', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('DELETEs /budget/trip with trip_id and expected_updated_at as query params', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    vi.stubGlobal('fetch', fetchSpy)

    await deleteTrip(7, '2026-01-01T00:00:00Z')

    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/budget/trip?')
    expect(String(url)).toContain('trip_id=7')
    expect(String(url)).toContain('expected_updated_at=')
    expect((init as RequestInit).method).toBe('DELETE')
  })

  it('propagates a 409 ApiError on a stale lock token', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(409, { detail: 'changed by someone else' })))
    await expect(deleteTrip(7, '2026-01-01T00:00:00Z')).rejects.toBeInstanceOf(ApiError)
  })
})
