import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchCountries, fetchTravelers } from './reference'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('fetchTravelers', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /reference/travelers with cost_center as a query param', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, []))
    vi.stubGlobal('fetch', fetchSpy)

    await fetchTravelers('CC1')

    const calledUrl = String(fetchSpy.mock.calls[0][0])
    expect(calledUrl).toContain('/reference/travelers?')
    expect(calledUrl).toContain('cost_center=CC1')
  })

  it('returns the parsed traveler list on success', async () => {
    const travelers = [{ empcode: '100123', name: 'สมชาย ทดสอบ', position: 'Officer' }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, travelers)))
    await expect(fetchTravelers('CC1')).resolves.toEqual(travelers)
  })
})

describe('fetchCountries', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /reference/countries with no params', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, []))
    vi.stubGlobal('fetch', fetchSpy)

    await fetchCountries()

    expect(String(fetchSpy.mock.calls[0][0])).toContain('/reference/countries')
  })

  it('returns the parsed country list on success', async () => {
    const countries = [
      { country: 'ประเทศไทย', country_group: 1 },
      { country: 'ญี่ปุ่น', country_group: 2 },
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, countries)))
    await expect(fetchCountries()).resolves.toEqual(countries)
  })
})
