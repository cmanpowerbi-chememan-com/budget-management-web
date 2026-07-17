import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useFillGlCount } from './useFillGlCount'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('useFillGlCount', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches GET /budget (no department filter) and counts distinct GL accounts for the Fill CCs', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse(200, [
        { cost_center: 'CC1', gl_account: 'GL1', sap: {}, board: {}, pending: {}, editable: true },
        { cost_center: 'CC1', gl_account: 'GL2', sap: {}, board: {}, pending: {}, editable: true },
        { cost_center: 'SEE-ONLY', gl_account: 'GL9', sap: {}, board: {}, pending: {}, editable: false },
      ]),
    )
    vi.stubGlobal('fetch', fetchSpy)

    const { result } = renderHook(() => useFillGlCount(2027, ['CC1']))

    expect(result.current.loading).toBe(true)
    expect(result.current.count).toBeNull()
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.count).toBe(2)
    const calledUrl = String(fetchSpy.mock.calls[0][0])
    expect(calledUrl).toContain('/budget?')
    expect(calledUrl).toContain('year=2027')
    expect(calledUrl).not.toContain('department=')
    expect(calledUrl).not.toContain('cost_center=')
  })

  it('skips the fetch and returns 0 when the caller has no Fill cost centers', () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    const { result } = renderHook(() => useFillGlCount(2027, []))

    expect(result.current.loading).toBe(false)
    expect(result.current.count).toBe(0)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('degrades to null (never a fabricated number, never crashes) on a failed request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(502, {})))

    const { result } = renderHook(() => useFillGlCount(2027, ['CC1']))
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.count).toBeNull()
  })
})
