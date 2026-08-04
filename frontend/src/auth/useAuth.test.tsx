import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { isSessionExpired } from '../api/sessionExpiry'
import { useAuth } from './useAuth'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

/** `apiFetch` (`api/client.ts`) branches on `response.type ===
 * 'opaqueredirect' || response.status === 0` — the shape `fetch` returns for
 * ANY 3xx once `redirect: 'manual'` is set, since the browser erases status/
 * headers/Location before JS sees it. This is the one shape `jsonResponse`
 * above cannot produce (it never sets `type`). */
function opaqueRedirectResponse(): Response {
  return {
    ok: false,
    status: 0,
    type: 'opaqueredirect',
    json: async () => {
      throw new Error('opaque response body is unreadable')
    },
  } as Response
}

describe('useAuth', () => {
  const originalLocation = window.location

  beforeEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, href: 'http://localhost/?dept=x&year=2026' },
    })
  })

  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
    vi.unstubAllGlobals()
  })

  it('resolves the logged-in email from GET /me', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(200, { email: 'user@chememan.com', app_env: 'local' })),
    )

    const { result } = renderHook(() => useAuth())

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.email).toBe('user@chememan.com')
    expect(result.current.error).toBeNull()
  })

  it('redirects to the Easy Auth login page on a 401 (ADR-0004)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, {})))

    const { result } = renderHook(() => useAuth())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(window.location.href).toContain('/.auth/login/aad?post_login_redirect_uri=')
    expect(result.current.email).toBeNull()
  })

  it('surfaces a non-auth failure as an error instead of crashing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(502, {})))

    const { result } = renderHook(() => useAuth())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.email).toBeNull()
    expect(result.current.error).not.toBeNull()
  })

  it('flips the session-expiry latch when the boot GET /me hits a dead session', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(opaqueRedirectResponse()))

    const { result } = renderHook(() => useAuth())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(isSessionExpired()).toBe(true)
    expect(result.current.email).toBeNull()
  })
})
