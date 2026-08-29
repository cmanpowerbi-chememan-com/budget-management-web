import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NoticeToasts, NOTICE_TTL_MS } from './NoticeToasts'
import { publishNotice } from './notice'

describe('NoticeToasts', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders nothing until something is published (no empty container in the DOM)', () => {
    render(<NoticeToasts />)
    expect(screen.queryByTestId('notice-stack')).not.toBeInTheDocument()
  })

  it('shows a published notice, announced politely rather than as an alert', () => {
    render(<NoticeToasts />)

    act(() => publishNotice('กรอก 146 · ระบบปรับเป็น 100 (ปัดเศษเป็นหลักร้อย)'))

    const toast = screen.getByRole('status')
    expect(toast).toHaveTextContent('กรอก 146 · ระบบปรับเป็น 100 (ปัดเศษเป็นหลักร้อย)')
    expect(toast).toHaveAttribute('aria-live', 'polite')
  })

  it('auto-dismisses after the TTL', () => {
    render(<NoticeToasts />)

    act(() => publishNotice('ข้อความแรก'))
    expect(screen.getByRole('status')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(NOTICE_TTL_MS)
    })

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('keeps only the 3 newest — a fast typist correcting cell after cell never buries the screen', () => {
    render(<NoticeToasts />)

    act(() => {
      publishNotice('หนึ่ง')
      publishNotice('สอง')
      publishNotice('สาม')
      publishNotice('สี่')
    })

    const toasts = screen.getAllByRole('status')
    expect(toasts).toHaveLength(3)
    expect(toasts.map((t) => t.textContent)).toEqual(['สอง✕', 'สาม✕', 'สี่✕'])
  })

  it('dismisses on the close button without waiting for the TTL', () => {
    render(<NoticeToasts />)

    act(() => publishNotice('ปิดฉันสิ'))
    fireEvent.click(screen.getByRole('button', { name: 'ปิดข้อความ' }))

    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('stops listening once unmounted (a late publish must not update a dead component)', () => {
    const { unmount } = render(<NoticeToasts />)
    unmount()

    expect(() => act(() => publishNotice('หลังจาก unmount'))).not.toThrow()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
