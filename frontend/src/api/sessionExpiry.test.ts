import { describe, expect, it, vi } from 'vitest'
import { isSessionExpired, raiseSessionExpired, subscribeSessionExpired } from './sessionExpiry'

describe('sessionExpiry latch', () => {
  it('starts un-expired', () => {
    expect(isSessionExpired()).toBe(false)
  })

  it('flips to expired and notifies a subscriber on the first raise', () => {
    const listener = vi.fn()
    subscribeSessionExpired(listener)

    raiseSessionExpired()

    expect(isSessionExpired()).toBe(true)
    expect(listener).toHaveBeenCalledOnce()
  })

  it('is first-call-wins: N concurrent raises notify a subscriber exactly once', () => {
    const listener = vi.fn()
    subscribeSessionExpired(listener)

    raiseSessionExpired()
    raiseSessionExpired()
    raiseSessionExpired()

    expect(listener).toHaveBeenCalledOnce()
  })

  it('unsubscribe stops further notifications', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeSessionExpired(listener)
    unsubscribe()

    raiseSessionExpired()

    expect(listener).not.toHaveBeenCalled()
  })
})
