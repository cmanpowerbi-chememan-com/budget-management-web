import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MonthAmountInput } from './MonthAmountInput'

// Same draft-string-then-commit shape as grid/MonthCell.tsx's editable
// input (bug-subform-no-decimals, 2026-08-19) — this component is what
// DetailSubform's month cells and TripManager's manual travel-line month
// cells now share, replacing their old `Number(raw.replace(/[^0-9]/g,''))`
// onChange, which stripped the decimal point AND coerced to a number on
// every keystroke (so even after allowing the dot, "51000." could never
// reach "51000.50" — the coercion collapsed it back to 51000 immediately).
describe('MonthAmountInput', () => {
  it('renders the raw value in the input', () => {
    render(<MonthAmountInput value={500} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
    expect(input.value).toBe('500')
  })

  it('preserves the decimal point when typing a fractional value (bug: was stripped)', () => {
    const onCommit = vi.fn()
    render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
    fireEvent.change(input, { target: { value: '51000.50' } })
    expect(input.value).toBe('51000.50')
    fireEvent.blur(input)
    expect(onCommit).toHaveBeenCalledWith(51000.5)
  })

  it('does not destroy a partially-typed decimal ("51000.") mid-typing', () => {
    render(<MonthAmountInput value={0} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
    fireEvent.change(input, { target: { value: '51000.' } })
    expect(input.value).toBe('51000.')
  })

  it('keeps only the first decimal point when multiple dots are typed', () => {
    render(<MonthAmountInput value={0} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
    fireEvent.change(input, { target: { value: '1.2.3' } })
    expect(input.value).toBe('1.23')
  })

  it('strips letters and a leading minus sign as the user types', () => {
    render(<MonthAmountInput value={0} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
    fireEvent.change(input, { target: { value: '-45a6' } })
    expect(input.value).toBe('456')
  })

  it('caps typed input to at most 2 decimal places', () => {
    render(<MonthAmountInput value={0} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
    fireEvent.change(input, { target: { value: '100.567' } })
    expect(input.value).toBe('100.56')
  })

  it('calls onCommit with the parsed number on blur only when the value changed', () => {
    const onCommit = vi.fn()
    render(<MonthAmountInput value={500} onCommit={onCommit} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1')
    fireEvent.blur(input)
    expect(onCommit).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { value: '750' } })
    fireEvent.blur(input)
    expect(onCommit).toHaveBeenCalledWith(750)
  })

  it('regression: a lone "." commits 0, never NaN', () => {
    const onCommit = vi.fn()
    render(<MonthAmountInput value={500} onCommit={onCommit} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1')
    fireEvent.change(input, { target: { value: '.' } })
    fireEvent.blur(input)
    expect(onCommit).toHaveBeenCalledWith(0)
    expect(Number.isNaN(onCommit.mock.calls[0][0])).toBe(false)
  })

  it('resyncs the displayed draft when the value prop changes externally (e.g. a save or a conflict-refetch)', () => {
    const { rerender } = render(<MonthAmountInput value={500} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
    fireEvent.change(input, { target: { value: '999' } }) // stale local edit, never committed
    rerender(<MonthAmountInput value={777} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
    expect((screen.getByLabelText('m01 row-1') as HTMLInputElement).value).toBe('777')
  })

  it('passes through className/testId/disabled unchanged (preserves subform styling + contrast baseline selectors)', () => {
    render(
      <MonthAmountInput
        value={0}
        onCommit={vi.fn()}
        ariaLabel="m01 row-1"
        className="detail-input month-input"
        testId="month-m01-row-1"
        disabled
      />,
    )
    const input = screen.getByTestId('month-m01-row-1')
    expect(input).toHaveClass('detail-input', 'month-input')
    expect(input).toBeDisabled()
  })
})
