import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { raiseSessionExpired, SESSION_EXPIRED_MESSAGE } from '../api/sessionExpiry'
import { SessionExpiredDialog } from './SessionExpiredDialog'

// `raiseSessionExpired()` fires the store notify OUTSIDE a React event
// handler, so React 19's `useSyncExternalStore` re-render must be flushed
// via `act()` before assertions run — otherwise the DOM still reflects the
// pre-raise render.
function raise() {
  act(() => {
    raiseSessionExpired()
  })
}

describe('SessionExpiredDialog', () => {
  it('renders nothing until the latch flips', () => {
    render(<SessionExpiredDialog />)

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('renders the locked title/sentence verbatim and exactly one button once the latch flips', () => {
    render(<SessionExpiredDialog />)

    raise()

    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toBeInTheDocument()
    expect(screen.getByText('หมดเวลาการเข้าใช้งาน')).toBeInTheDocument()
    expect(screen.getByText(SESSION_EXPIRED_MESSAGE)).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'เข้าสู่ระบบใหม่' })).toBeInTheDocument()
  })

  it('has no role="alert" node and no .grid-error element (must not collide with existing getByRole("alert") / e2e locators)', () => {
    render(<SessionExpiredDialog />)
    raise()

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(document.querySelector('.grid-error')).not.toBeInTheDocument()
  })

  it('has no close (✕) button', () => {
    render(<SessionExpiredDialog />)
    raise()

    expect(screen.queryByRole('button', { name: /close/i })).not.toBeInTheDocument()
    expect(screen.queryByText('✕')).not.toBeInTheDocument()
  })

  it('Escape does not close the dialog', () => {
    render(<SessionExpiredDialog />)
    raise()

    fireEvent.keyDown(document.body, { key: 'Escape' })

    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })

  it('a backdrop click does not close the dialog', () => {
    render(<SessionExpiredDialog />)
    raise()

    const backdrop = screen.getByRole('alertdialog').parentElement as HTMLElement
    fireEvent.click(backdrop)

    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })

  it('focuses the dialog container, not the button, when it opens (a queued Enter must not fire navigation)', () => {
    render(<SessionExpiredDialog />)
    raise()

    expect(screen.getByRole('alertdialog')).toHaveFocus()
  })

  it('aria-labelledby/aria-describedby point at the title and body text', () => {
    render(<SessionExpiredDialog />)
    raise()

    const dialog = screen.getByRole('alertdialog')
    const labelledBy = dialog.getAttribute('aria-labelledby')
    const describedBy = dialog.getAttribute('aria-describedby')
    expect(labelledBy).toBeTruthy()
    expect(describedBy).toBeTruthy()
    expect(document.getElementById(labelledBy as string)).toHaveTextContent('หมดเวลาการเข้าใช้งาน')
    expect(document.getElementById(describedBy as string)).toHaveTextContent(SESSION_EXPIRED_MESSAGE)
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('the button navigates to the Easy Auth login redirect carrying the current href', () => {
    const originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, href: 'http://localhost/?dept=x&year=2026' },
    })

    render(<SessionExpiredDialog />)
    raise()

    fireEvent.click(screen.getByRole('button', { name: 'เข้าสู่ระบบใหม่' }))

    expect(window.location.href).toBe(
      '/.auth/login/aad?post_login_redirect_uri=' +
        encodeURIComponent('http://localhost/?dept=x&year=2026'),
    )

    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
  })
})
