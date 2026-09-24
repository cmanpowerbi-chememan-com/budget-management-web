import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog'
import { confirmDialog } from './confirm'

describe('ConfirmDialog', () => {
  it('shows the exact message with no browser hostname anywhere, and resolves true on OK', async () => {
    render(<ConfirmDialog />)

    let result: boolean | undefined
    act(() => {
      confirmDialog('ลบไฟล์ "images.jpg" ออกจากโฟลเดอร์นี้?', { danger: true }).then((v) => {
        result = v
      })
    })

    const dialog = screen.getByTestId('confirm-dialog')
    expect(dialog).toHaveAttribute('role', 'dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByTestId('confirm-message')).toHaveTextContent('ลบไฟล์ "images.jpg" ออกจากโฟลเดอร์นี้?')
    // The whole point of this component: no native window.confirm host line
    // ("<hostname> says") can appear, because nothing here is a native dialog.
    expect(dialog.textContent).not.toMatch(/says|azurecontainerapps|localhost/i)

    fireEvent.click(screen.getByTestId('confirm-ok'))
    await act(async () => {})
    expect(result).toBe(true)
  })

  it('resolves false when Cancel is clicked, and leaves no dialog behind', async () => {
    render(<ConfirmDialog />)

    let result: boolean | undefined
    act(() => {
      confirmDialog('ลบรายการนี้?').then((v) => {
        result = v
      })
    })

    fireEvent.click(screen.getByTestId('confirm-cancel'))
    await act(async () => {})

    expect(result).toBe(false)
    expect(screen.queryByTestId('confirm-dialog')).not.toBeInTheDocument()
  })

  it('resolves false on Escape', async () => {
    render(<ConfirmDialog />)

    let result: boolean | undefined
    act(() => {
      confirmDialog('ลบรายการนี้?').then((v) => {
        result = v
      })
    })

    fireEvent.keyDown(screen.getByTestId('confirm-dialog'), { key: 'Escape' })
    await act(async () => {})

    expect(result).toBe(false)
    expect(screen.queryByTestId('confirm-dialog')).not.toBeInTheDocument()
  })

  it('resolves true on Enter', async () => {
    render(<ConfirmDialog />)

    let result: boolean | undefined
    act(() => {
      confirmDialog('ลบรายการนี้?').then((v) => {
        result = v
      })
    })

    fireEvent.keyDown(screen.getByTestId('confirm-dialog'), { key: 'Enter' })
    await act(async () => {})

    expect(result).toBe(true)
  })

  it('preserves \\n as separate lines (white-space: pre-line on the message element)', () => {
    render(<ConfirmDialog />)

    act(() => {
      void confirmDialog('ลบรายการนี้? (CC001 · 5120100010)\nลบแล้วเรียกคืนไม่ได้')
    })

    const message = screen.getByTestId('confirm-message')
    expect(message.textContent).toBe('ลบรายการนี้? (CC001 · 5120100010)\nลบแล้วเรียกคืนไม่ได้')
    expect(message.className).toContain('confirm-dialog-message')
  })

  it('uses the default Thai labels when none are given, and custom labels when given', () => {
    render(<ConfirmDialog />)

    act(() => {
      void confirmDialog('ยืนยัน?')
    })
    expect(screen.getByTestId('confirm-ok')).toHaveTextContent('ตกลง')
    expect(screen.getByTestId('confirm-cancel')).toHaveTextContent('ยกเลิก')

    fireEvent.click(screen.getByTestId('confirm-cancel'))

    act(() => {
      void confirmDialog('ลบทริปนี้ทั้งหมด?', { confirmLabel: 'ลบ', cancelLabel: 'ยกเลิก', danger: true })
    })
    expect(screen.getByTestId('confirm-ok')).toHaveTextContent('ลบ')
    expect(screen.getByTestId('confirm-ok').className).toContain('btn-danger')
  })

  it('a second request while one is open resolves the first as false and shows the newer one', async () => {
    render(<ConfirmDialog />)

    let firstResult: boolean | undefined
    let secondResult: boolean | undefined
    act(() => {
      confirmDialog('คำถามแรก').then((v) => {
        firstResult = v
      })
    })
    act(() => {
      confirmDialog('คำถามที่สอง').then((v) => {
        secondResult = v
      })
    })

    await act(async () => {})
    expect(firstResult).toBe(false)
    expect(secondResult).toBeUndefined()
    expect(screen.getByTestId('confirm-message')).toHaveTextContent('คำถามที่สอง')

    fireEvent.click(screen.getByTestId('confirm-ok'))
    await act(async () => {})
    expect(secondResult).toBe(true)
  })

  it('falls back to window.confirm when no host is mounted (unit tests rendering a lone component keep working)', async () => {
    const spy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    const result = await confirmDialog('ลบไฟล์ "a.pdf" ออกจากโฟลเดอร์นี้?')

    expect(spy).toHaveBeenCalledWith('ลบไฟล์ "a.pdf" ออกจากโฟลเดอร์นี้?')
    expect(result).toBe(true)
    spy.mockRestore()
  })

  // BUG FIX (jakkaritw, prd report 2026-09-24): pressing the mouse inside the
  // dialog and releasing over the dim backdrop used to fire a native `click`
  // on the backdrop itself — the browser's common-ancestor rule for a
  // cross-element press/release — which the old `e.target === e.currentTarget`
  // check couldn't tell apart from a real backdrop click, silently resolving
  // the confirm as `false`. Fixed by `useBackdropDismiss`
  // (src/platform/backdropDismiss.ts), which only dismisses when the PRESS
  // and the RELEASE both land on the backdrop itself.
  describe('backdrop drag-release guard (bug fix 2026-09-24)', () => {
    function backdrop(): HTMLElement {
      const el = document.querySelector('.modal-backdrop')
      if (!el) throw new Error('modal-backdrop not found')
      return el as HTMLElement
    }

    it('a press that starts inside the dialog and a click that lands on the backdrop (drag-release) does not resolve false', async () => {
      render(<ConfirmDialog />)

      let result: boolean | undefined
      act(() => {
        confirmDialog('ลบรายการนี้?').then((v) => {
          result = v
        })
      })

      fireEvent.mouseDown(screen.getByTestId('confirm-dialog'))
      fireEvent.mouseUp(backdrop())
      fireEvent.click(backdrop())
      await act(async () => {})

      expect(result).toBeUndefined()
      expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument()
    })

    it('a press and click that both land on the backdrop resolve false (clean backdrop click still works)', async () => {
      render(<ConfirmDialog />)

      let result: boolean | undefined
      act(() => {
        confirmDialog('ลบรายการนี้?').then((v) => {
          result = v
        })
      })

      fireEvent.mouseDown(backdrop())
      fireEvent.mouseUp(backdrop())
      fireEvent.click(backdrop())
      await act(async () => {})

      expect(result).toBe(false)
      expect(screen.queryByTestId('confirm-dialog')).not.toBeInTheDocument()
    })
  })
})
