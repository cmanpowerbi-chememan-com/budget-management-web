import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useAdminViewToggle } from './useAdminViewToggle'

describe('useAdminViewToggle', () => {
  afterEach(() => {
    window.sessionStorage.clear()
  })

  it('defaults to OFF (ADR-0014: admin powers are opt-in, not always-on)', () => {
    const { result } = renderHook(() => useAdminViewToggle())
    expect(result.current[0]).toBe(false)
  })

  it('flips on and persists to sessionStorage', () => {
    const { result } = renderHook(() => useAdminViewToggle())
    act(() => result.current[1](true))
    expect(result.current[0]).toBe(true)
    expect(window.sessionStorage.getItem('budget-admin-view-enabled')).toBe('true')
  })

  it('a fresh hook instance reads the persisted value back', () => {
    const first = renderHook(() => useAdminViewToggle())
    act(() => first.result.current[1](true))

    const second = renderHook(() => useAdminViewToggle())
    expect(second.result.current[0]).toBe(true)
  })
})
