import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NoticeToasts } from '../platform/NoticeToasts'
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
    expect(input.value).toBe('5,100,050')
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
      expect(input.value).toBe('1,234')
      fireEvent.blur(input)
      expect(input.value).toBe('1,200')
      expect(onCommit).toHaveBeenCalledWith(1200)
    })

    it('clamps a value that rounds past the cap to 100,000,000, shown in the field', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '100000060' } })
      fireEvent.blur(input)
      expect(input.value).toBe('100,000,000')
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

  // jakkaritw, 2026-09-30, issue #37: every editable Pending money input shows
  // thousands commas WHILE typing. Only the text in the box changes — the
  // number handed to onCommit and the toast wording are exactly as before.
  describe('thousands commas in the input (issue #37)', () => {
    it('shows a stored amount grouped on first render', () => {
      render(<MonthAmountInput value={46400} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
      expect((screen.getByLabelText('m01 row-1') as HTMLInputElement).value).toBe('46,400')
    })

    it('groups live as the user types and commits the PLAIN number on blur', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '25000' } })
      expect(input.value).toBe('25,000')
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(25000)
      expect(input.value).toBe('25,000') // stays grouped after leaving the cell
    })

    it('the blur redraw after the round-to-100 correction is grouped too (1,234 -> 1,200)', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '1234' } })
      expect(input.value).toBe('1,234') // rounding is still commit-time only
      fireEvent.blur(input)
      expect(input.value).toBe('1,200')
      expect(onCommit).toHaveBeenCalledWith(1200)
    })

    it('accepts a pasted grouped amount ("25,000" -> 25000)', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '25,000' } })
      expect(input.value).toBe('25,000')
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(25000)
    })

    it('drops accidental leading zeros from the display (0025000 -> 25,000)', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '0025000' } })
      expect(input.value).toBe('25,000')
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(25000)
    })

    it('an emptied cell stays empty while typing and becomes 0 on blur', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={1500} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '' } })
      expect(input.value).toBe('')
      fireEvent.blur(input)
      expect(input.value).toBe('0')
      expect(onCommit).toHaveBeenCalledWith(0)
    })

    it('shows the 100,000,000 cap grouped, and does not clamp per keystroke', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={0} onCommit={onCommit} ariaLabel="m01 row-1" />)
      const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '1000000000' } })
      expect(input.value).toBe('1,000,000,000') // beyond the cap, shown as typed
      fireEvent.blur(input)
      expect(input.value).toBe('100,000,000')
      expect(onCommit).toHaveBeenCalledWith(100_000_000)
    })

    it('re-syncs to grouped text when the SERVER-derived value changes', () => {
      const { rerender } = render(<MonthAmountInput value={500} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
      rerender(<MonthAmountInput value={1234500} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
      expect((screen.getByLabelText('m01 row-1') as HTMLInputElement).value).toBe('1,234,500')
    })

    it('an untouched grouped cell blurs without committing', () => {
      const onCommit = vi.fn()
      render(<MonthAmountInput value={46400} onCommit={onCommit} ariaLabel="m01 row-1" />)
      fireEvent.blur(screen.getByLabelText('m01 row-1'))
      expect(onCommit).not.toHaveBeenCalled()
    })

    describe('legacy fractional server value 999.25 (behaviour identical to before #37)', () => {
      beforeEach(() => vi.useFakeTimers())
      afterEach(() => vi.useRealTimers())

      it('re-displays as-is (no rounding, no .00) and blur commits 1000 with the same toast', () => {
        const onCommit = vi.fn()
        render(
          <>
            <MonthAmountInput value={999.25} onCommit={onCommit} ariaLabel="m01 row-1" />
            <NoticeToasts />
          </>,
        )
        const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
        expect(input.value).toBe('999.25')
        fireEvent.blur(input)
        expect(onCommit).toHaveBeenCalledWith(1000)
        expect(input.value).toBe('1,000')
        expect(screen.getByRole('status')).toHaveTextContent('กรอก 999 · ระบบปรับเป็น 1,000 (ปัดเศษเป็นหลักร้อย)')
      })

      it('groups a fractional legacy value without touching the decimals, and parses it back at 1/100 not 100x (1,234.25 -> 1,200)', () => {
        const onCommit = vi.fn()
        render(<MonthAmountInput value={1234.25} onCommit={onCommit} ariaLabel="m01 row-1" />)
        const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
        expect(input.value).toBe('1,234.25')
        fireEvent.blur(input)
        expect(onCommit).toHaveBeenCalledWith(1200)
      })
    })

    describe('caret (real keystrokes via user-event)', () => {
      it('stays right after the typed digit when typing mid-number and when a comma appears', async () => {
        const user = userEvent.setup()
        render(<MonthAmountInput value={1234} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
        const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
        await user.type(input, '50', { initialSelectionStart: 1, initialSelectionEnd: 1 })
        // "1|,234" + "5" + "0" -> 150,234 with the caret after the 0 that was just typed
        expect(input.value).toBe('150,234')
        expect(input.selectionStart).toBe(3)
      })

      it('keeps the caret right after a digit typed mid-number when the comma moves (1,234 -> 19,234)', async () => {
        const user = userEvent.setup()
        render(<MonthAmountInput value={1234} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
        const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
        // caret sits right AFTER the comma ("1,|234"); the typed 9 makes the raw text
        // "1,9234", which regroups to "19,234" — the comma moves, so without the
        // explicit caret restore the browser would throw the caret to the end.
        await user.type(input, '9', { initialSelectionStart: 2, initialSelectionEnd: 2 })
        expect(input.value).toBe('19,234')
        expect(input.selectionStart).toBe(2)
      })

      it('keeps the caret after the last digit when a typed digit adds a new group (999 -> 9,999)', async () => {
        const user = userEvent.setup()
        render(<MonthAmountInput value={999} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
        const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
        await user.type(input, '9')
        expect(input.value).toBe('9,999')
        expect(input.selectionStart).toBe(5)
      })

      it('Backspace right after a comma moves the caret left past it, and the next Backspace deletes the digit', async () => {
        const user = userEvent.setup()
        render(<MonthAmountInput value={25000} onCommit={vi.fn()} ariaLabel="m01 row-1" />)
        const input = screen.getByLabelText('m01 row-1') as HTMLInputElement
        await user.type(input, '{Backspace}', { initialSelectionStart: 3, initialSelectionEnd: 3 })
        expect(input.value).toBe('25,000')
        expect(input.selectionStart).toBe(2)
        await user.keyboard('{Backspace}')
        expect(input.value).toBe('2,000')
        expect(input.selectionStart).toBe(1)
      })
    })
  })

  // 2026-08-29: the subform/Trip-Manager inputs raise the SAME rounding toast
  // as the grid's own cells — one rule, one message, two entry points.
  describe('rounding toast', () => {
    beforeEach(() => vi.useFakeTimers())
    afterEach(() => vi.useRealTimers())

    it('announces a rounded amount from inside a subform too', () => {
      render(
        <>
          <MonthAmountInput value={0} onCommit={vi.fn()} ariaLabel="m01 row-1" />
          <NoticeToasts />
        </>,
      )
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '1234' } })
      fireEvent.blur(input)
      expect(screen.getByRole('status')).toHaveTextContent('กรอก 1,234 · ระบบปรับเป็น 1,200 (ปัดเศษเป็นหลักร้อย)')
    })

    it('announces the 100,000,000 cap with the typed amount grouped', () => {
      render(
        <>
          <MonthAmountInput value={0} onCommit={vi.fn()} ariaLabel="m01 row-1" />
          <NoticeToasts />
        </>,
      )
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '1000000000' } })
      fireEvent.blur(input)
      expect(screen.getByRole('status')).toHaveTextContent('กรอก 1,000,000,000 ซึ่งเกินเพดาน 100 ล้านต่อช่อง · ระบบบันทึกเป็น 100,000,000')
    })

    it('stays silent for an already-valid amount', () => {
      render(
        <>
          <MonthAmountInput value={0} onCommit={vi.fn()} ariaLabel="m01 row-1" />
          <NoticeToasts />
        </>,
      )
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '5000' } })
      fireEvent.blur(input)
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    })
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
