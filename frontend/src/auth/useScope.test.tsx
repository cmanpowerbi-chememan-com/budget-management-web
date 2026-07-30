import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useScope } from './useScope'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('useScope', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('resolves Fill/See cost centers and role from GET /scope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(200, {
          email: 'user@chememan.com',
          is_admin: false,
          role: 'filler',
          fill_cost_centers: ['10CA013000'],
          see_cost_centers: ['10CA013000', '10CA013001'],
        }),
      ),
    )

    const { result } = renderHook(() => useScope())

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.role).toBe('filler')
    expect(result.current.isAdmin).toBe(false)
    expect(result.current.fillCostCenters).toEqual(['10CA013000'])
    expect(result.current.seeCostCenters).toEqual(['10CA013000', '10CA013001'])
    expect(result.current.email).toBe('user@chememan.com')
    expect(result.current.error).toBeNull()
  })

  it('falls back to an empty scope (never crashes) on a failed request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(502, {})))

    const { result } = renderHook(() => useScope())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.role).toBeNull()
    expect(result.current.fillCostCenters).toEqual([])
    expect(result.current.seeCostCenters).toEqual([])
    expect(result.current.email).toBeNull()
    expect(result.current.error).not.toBeNull()
  })
})
