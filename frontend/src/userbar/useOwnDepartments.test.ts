import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useOwnDepartments } from './useOwnDepartments'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('useOwnDepartments', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('fetches GET /scope/departments with admin_view_enabled=false always, when enabled', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse(200, [{ cost_center: '10CA013000', department: 'ฝ่ายบัญชี', division: 'Div A', c_level: null }]),
    )
    vi.stubGlobal('fetch', fetchSpy)

    const { result } = renderHook(() => useOwnDepartments(true))

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.departments).toHaveLength(1)
    const calledUrl = String(fetchSpy.mock.calls[0][0])
    expect(calledUrl).toContain('/scope/departments')
    expect(calledUrl).not.toContain('admin_view_enabled=true')
  })

  it('skips the fetch entirely when disabled (e.g. pure admin, no personal scope to show)', () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    const { result } = renderHook(() => useOwnDepartments(false))

    expect(result.current.loading).toBe(false)
    expect(result.current.departments).toEqual([])
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('degrades to an empty list (never crashes) on a failed request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(502, {})))

    const { result } = renderHook(() => useOwnDepartments(true))
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.departments).toEqual([])
  })
})
