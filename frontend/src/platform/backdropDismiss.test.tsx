import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useBackdropDismiss } from './backdropDismiss'

/** Minimal harness mirroring every real caller's shape (`.modal-backdrop` >
 * one inner element) — isolates the hook's own contract from any particular
 * modal's other logic (all 4 real callers are exercised end-to-end in their
 * own component test files). */
function Harness({ onDismiss }: { onDismiss: () => void }) {
  const handlers = useBackdropDismiss(onDismiss)
  return (
    <div data-testid="backdrop" {...handlers}>
      <div data-testid="inner">inner</div>
    </div>
  )
}

describe('useBackdropDismiss', () => {
  it('dismisses when both the press and the click land on the backdrop itself (a genuine backdrop click)', () => {
    const onDismiss = vi.fn()
    render(<Harness onDismiss={onDismiss} />)
    const backdrop = screen.getByTestId('backdrop')

    fireEvent.mouseDown(backdrop)
    fireEvent.mouseUp(backdrop)
    fireEvent.click(backdrop)

    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('does not dismiss when the press started inside the child but the click lands on the backdrop (drag-release misclick)', () => {
    const onDismiss = vi.fn()
    render(<Harness onDismiss={onDismiss} />)
    const backdrop = screen.getByTestId('backdrop')
    const inner = screen.getByTestId('inner')

    fireEvent.mouseDown(inner)
    fireEvent.click(backdrop)

    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('does not dismiss the REVERSE drag — press on the backdrop, release inside the child, click lands on the backdrop', () => {
    const onDismiss = vi.fn()
    render(<Harness onDismiss={onDismiss} />)
    const backdrop = screen.getByTestId('backdrop')
    const inner = screen.getByTestId('inner')

    fireEvent.mouseDown(backdrop)
    fireEvent.mouseUp(inner)
    fireEvent.click(backdrop)

    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('does not dismiss a click that starts and ends inside the child', () => {
    const onDismiss = vi.fn()
    render(<Harness onDismiss={onDismiss} />)
    const inner = screen.getByTestId('inner')

    fireEvent.mouseDown(inner)
    fireEvent.click(inner)

    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('resets the flag after every click — a later bare click on the backdrop (no new press) does not dismiss again', () => {
    const onDismiss = vi.fn()
    render(<Harness onDismiss={onDismiss} />)
    const backdrop = screen.getByTestId('backdrop')

    fireEvent.mouseDown(backdrop)
    fireEvent.mouseUp(backdrop)
    fireEvent.click(backdrop) // genuine dismiss
    expect(onDismiss).toHaveBeenCalledTimes(1)

    fireEvent.click(backdrop) // bare click, no new mousedown/mouseup
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
