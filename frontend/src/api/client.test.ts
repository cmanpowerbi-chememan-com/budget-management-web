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
})
