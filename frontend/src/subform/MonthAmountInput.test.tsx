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

  it('strips a decimal point as the user types — no decimals allowed (2026-08-19, supersedes 7ba8f49)', () => {
    const onCommit = vi.fn()
    render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
    fireEvent.change(input, { target: { value: '51000.50' } })
    expect(input.value).toBe('5100050')
  })

  it('strips every dot when multiple are typed (1.2.3 -> 123, digits only)', () => {
    render(<MonthAmountInput value={0} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
    fireEvent.change(input, { target: { value: '1.2.3' } })
    expect(input.value).toBe('123')
  })

  it('strips letters and a leading minus sign as the user types', () => {
    render(<MonthAmountInput value={0} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
    fireEvent.change(input, { target: { value: '-45a6' } })
    expect(input.value).toBe('456')
  })

  it('calls onCommit with the parsed number on blur only when the value changed', () => {
    const onCommit = vi.fn()
    render(<MonthAmountInput value={500} onCommit={onCommit} ariaLabel="m01 row-1" />)
    const input = screen.getByLabelText('m01 row-1')
    fireEvent.blur(input)
    expect(onCommit).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { value: '700' } })
    fireEvent.blur(input)
    expect(onCommit).toHaveBeenCalledWith(700)
  })

  // jakkaritw, 2026-08-19: every Pending amount rounds to the nearest 100
  // (half-up) and is capped at 100,000,000 — applied on COMMIT (blur), never
  // per keystroke. Same rule as grid/MonthCell.tsx (shared via this
  // component). Per-diem never reaches this input at all — TripManager
  // renders per-diem months as a read-only <span> (see its own test file).
  describe('round-to-100 on commit (jakkaritw 2026-08-19)', () => {
    it('rounds a typed value on blur and REDRAWS the field to the corrected number (146 -> 100)', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '146' } })
      expect(input.value).toBe('146') // unrounded while typing
      fireEvent.blur(input)
      expect(input.value).toBe('100')
      expect(onCommit).toHaveBeenCalledWith(100)
    })

    it('the named half-up boundary rounds UP, not down (150 -> 200)', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '150' } })
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(200)
    })

    it('proves rounding happens on commit, not per keystroke: 1234 stays reachable, then becomes 1200 on blur', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '1234' } })
      expect(input.value).toBe('1234')
      fireEvent.blur(input)
      expect(input.value).toBe('1200')
      expect(onCommit).toHaveBeenCalledWith(1200)
    })

    it('clamps a value that rounds past the cap to 100,000,000, shown in the field', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '100000060' } })
      fireEvent.blur(input)
      expect(input.value).toBe('100000000')
      expect(onCommit).toHaveBeenCalledWith(100_000_000)
    })
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
