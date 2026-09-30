import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NoticeToasts } from '../platform/NoticeToasts'
import { MonthCell } from './MonthCell'

describe('MonthCell', () => {
  it('renders a formatted read-only value when not editable', () => {
    render(<MonthCell value={1234} editable={false} onCommit={vi.fn()} label="Jan pending" />)
    expect(screen.getByText('1,234.00')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('renders zero as a dash placeholder when not editable', () => {
    render(<MonthCell value={0} editable={false} onCommit={vi.fn()} label="Jan pending" />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders an editable input carrying the raw value', () => {
    render(<MonthCell value={500} editable={true} onCommit={vi.fn()} label="Jan pending" />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    expect(input.value).toBe('500')
  })

  it('calls onCommit with the parsed number on blur when the value changed', () => {
    const onCommit = vi.fn()
    render(<MonthCell value={500} editable={true} onCommit={onCommit} label="Jan pending" />)
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: '700' } })
    fireEvent.blur(input)
    expect(onCommit).toHaveBeenCalledWith(700)
  })

  it('does not call onCommit on blur when the value is unchanged', () => {
    const onCommit = vi.fn()
    render(<MonthCell value={500} editable={true} onCommit={onCommit} label="Jan pending" />)
    const input = screen.getByRole('textbox')
    fireEvent.blur(input)
    expect(onCommit).not.toHaveBeenCalled()
  })

  it('strips non-numeric characters as the user types', () => {
    const onCommit = vi.fn()
    render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    fireEvent.change(input, { target: { value: '1a2b3' } })
    expect(input.value).toBe('123')
  })

  it('strips a decimal point as the user types — no decimals allowed (2026-08-19, supersedes 7ba8f49)', () => {
    const onCommit = vi.fn()
    render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    fireEvent.change(input, { target: { value: '100.5' } })
    expect(input.value).toBe('1,005')
  })

  it('strips every dot when multiple are typed (1.2.3 -> 123, digits only)', () => {
    const onCommit = vi.fn()
    render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    fireEvent.change(input, { target: { value: '1.2.3' } })
    expect(input.value).toBe('123')
  })

  it('strips a leading minus sign — negatives are not allowed', () => {
    const onCommit = vi.fn()
    render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    fireEvent.change(input, { target: { value: '-50' } })
    expect(input.value).toBe('50')
  })

  it('regression: a lone "." sanitizes to empty and commits 0, never NaN', () => {
    const onCommit = vi.fn()
    render(<MonthCell value={500} editable={true} onCommit={onCommit} label="Jan pending" />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    fireEvent.change(input, { target: { value: '.' } })
    expect(input.value).toBe('')
    fireEvent.blur(input)
    expect(onCommit).toHaveBeenCalledTimes(1)
    expect(onCommit).toHaveBeenCalledWith(0)
    expect(Number.isNaN(onCommit.mock.calls[0][0])).toBe(false)
  })

  it('regression: a lone "." on a cell already at 0 does not commit (0 === 0, unchanged)', () => {
    const onCommit = vi.fn()
    render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    fireEvent.change(input, { target: { value: '.' } })
    fireEvent.blur(input)
    expect(onCommit).not.toHaveBeenCalled()
  })

  it('resyncs the displayed value when the value prop changes externally (e.g. a conflict-refetch revert)', () => {
    const { rerender } = render(<MonthCell value={500} editable={true} onCommit={vi.fn()} label="Jan pending" />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    fireEvent.change(input, { target: { value: '999' } }) // user typed a stale edit, never committed
    rerender(<MonthCell value={777} editable={true} onCommit={vi.fn()} label="Jan pending" />)
    expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('777')
  })

  // jakkaritw, 2026-08-19: every Pending amount rounds to the nearest 100
  // (half-up) and is capped at 100,000,000 — applied on COMMIT (blur), never
  // per keystroke, so the field visibly shows the corrected number.
  describe('round-to-100 on commit (jakkaritw 2026-08-19)', () => {
    it('rounds a typed value on blur and REDRAWS the field to the corrected number (146 -> 100)', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '146' } })
      expect(input.value).toBe('146') // unrounded while typing — proves rounding is not per keystroke
      fireEvent.blur(input)
      expect(input.value).toBe('100')
      expect(onCommit).toHaveBeenCalledWith(100)
    })

    it('the named half-up boundary rounds UP, not down (150 -> 200)', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '150' } })
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(200)
    })

    it('a sub-50 units/tens value lands on 0 by design (jakkaritw: 5,6,7 / 10,20,30 unreachable)', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={500} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '30' } })
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(0)
    })

    it('proves rounding happens on commit, not per keystroke: typing 1234 stays reachable, then becomes 1200 on blur', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '1' } })
      expect(input.value).toBe('1')
      fireEvent.change(input, { target: { value: '12' } })
      expect(input.value).toBe('12')
      fireEvent.change(input, { target: { value: '123' } })
      expect(input.value).toBe('123')
      fireEvent.change(input, { target: { value: '1234' } })
      expect(input.value).toBe('1,234') // the 4th digit is still reachable — a per-keystroke round would have collapsed this to 100
      fireEvent.blur(input)
      expect(input.value).toBe('1,200')
      expect(onCommit).toHaveBeenCalledWith(1200)
    })

    it('accepts exactly the 100,000,000 cap', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '100000000' } })
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(100_000_000)
    })

    it('clamps a value that rounds past the cap to 100,000,000, shown in the field', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '100000060' } })
      fireEvent.blur(input)
      expect(input.value).toBe('100,000,000')
      expect(onCommit).toHaveBeenCalledWith(100_000_000)
    })
  })

  // 2026-08-29: the corrected number redrawn in the field was judged too easy
  // to miss, so a commit that CHANGED what was typed also raises a toast.
  // Rendered together with the real `NoticeToasts` host — asserting the
  // published text through the actual UI, not a spy on the bus.
  describe('rounding toast', () => {
    beforeEach(() => vi.useFakeTimers())
    afterEach(() => vi.useRealTimers())

    function renderCellWithToasts(value: number) {
      render(
        <>
          <MonthCell value={value} editable={true} onCommit={vi.fn()} label="Jan pending" />
          <NoticeToasts />
        </>,
      )
      return screen.getByRole('textbox')
    }

    it('announces a rounded amount', () => {
      const input = renderCellWithToasts(0)
      fireEvent.change(input, { target: { value: '146' } })
      fireEvent.blur(input)
      expect(screen.getByRole('status')).toHaveTextContent('กรอก 146 · ระบบปรับเป็น 100 (ปัดเศษเป็นหลักร้อย)')
    })

    it('announces a sub-100 amount landing on 0 with its own wording', () => {
      const input = renderCellWithToasts(0)
      fireEvent.change(input, { target: { value: '30' } })
      fireEvent.blur(input)
      expect(screen.getByRole('status')).toHaveTextContent('ระบบบันทึกเป็น 0 (กรอกได้ตั้งแต่ 100 ขึ้นไป)')
    })

    it('announces a rounded amount typed with a thousands comma (1,234 -> 1,200)', () => {
      const onCommit = vi.fn()
      render(
        <>
          <MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />
          <NoticeToasts />
        </>,
      )
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '1234' } })
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(1200)
      expect(screen.getByRole('status')).toHaveTextContent('กรอก 1,234 · ระบบปรับเป็น 1,200 (ปัดเศษเป็นหลักร้อย)')
    })

    it('announces the 100,000,000 cap with the typed amount grouped', () => {
      const input = renderCellWithToasts(0)
      fireEvent.change(input, { target: { value: '1000000000' } })
      fireEvent.blur(input)
      expect(screen.getByRole('status')).toHaveTextContent('กรอก 1,000,000,000 ซึ่งเกินเพดาน 100 ล้านต่อช่อง · ระบบบันทึกเป็น 100,000,000')
    })

    it('stays silent when the typed amount was already valid', () => {
      const input = renderCellWithToasts(0)
      fireEvent.change(input, { target: { value: '1200' } })
      fireEvent.blur(input)
      expect(screen.queryByRole('status')).not.toBeInTheDocument()
    })

    it('still announces when the rounded value equals what the cell already held (nothing commits, but the typing WAS corrected)', () => {
      const onCommit = vi.fn()
      render(
        <>
          <MonthCell value={100} editable={true} onCommit={onCommit} label="Jan pending" />
          <NoticeToasts />
        </>,
      )
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '146' } })
      fireEvent.blur(input)
      expect(onCommit).not.toHaveBeenCalled()
      expect(screen.getByRole('status')).toHaveTextContent('ระบบปรับเป็น 100')
    })
  })

  // jakkaritw, 2026-09-30, issue #37: every editable Pending money input shows
  // thousands commas WHILE typing. Only the text in the box changes — the
  // number handed to onCommit and the toast wording are exactly as before.
  describe('thousands commas in the input (issue #37)', () => {
    it('shows a stored amount grouped on first render', () => {
      render(<MonthCell value={46400} editable={true} onCommit={vi.fn()} label="Jan pending" />)
      expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('46,400')
    })

    it('groups live as the user types and commits the PLAIN number on blur', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '25000' } })
      expect(input.value).toBe('25,000')
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(25000)
      expect(input.value).toBe('25,000') // stays grouped after leaving the cell
    })

    it('the blur redraw after the round-to-100 correction is grouped too (1,234 -> 1,200)', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '1234' } })
      expect(input.value).toBe('1,234') // rounding is still commit-time only
      fireEvent.blur(input)
      expect(input.value).toBe('1,200')
      expect(onCommit).toHaveBeenCalledWith(1200)
    })

    it('accepts a pasted grouped amount ("25,000" -> 25000)', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '25,000' } })
      expect(input.value).toBe('25,000')
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(25000)
    })

    it('drops accidental leading zeros from the display (0025000 -> 25,000)', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '0025000' } })
      expect(input.value).toBe('25,000')
      fireEvent.blur(input)
      expect(onCommit).toHaveBeenCalledWith(25000)
    })

    it('an emptied cell stays empty while typing and becomes 0 on blur', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={1500} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '' } })
      expect(input.value).toBe('')
      fireEvent.blur(input)
      expect(input.value).toBe('0')
      expect(onCommit).toHaveBeenCalledWith(0)
    })

    it('shows the 100,000,000 cap grouped, and does not clamp per keystroke', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={0} editable={true} onCommit={onCommit} label="Jan pending" />)
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: '1000000000' } })
      expect(input.value).toBe('1,000,000,000') // beyond the cap, shown as typed
      fireEvent.blur(input)
      expect(input.value).toBe('100,000,000')
      expect(onCommit).toHaveBeenCalledWith(100_000_000)
    })

    it('re-syncs to grouped text when the SERVER-derived value changes', () => {
      const { rerender } = render(<MonthCell value={500} editable={true} onCommit={vi.fn()} label="Jan pending" />)
      rerender(<MonthCell value={1234500} editable={true} onCommit={vi.fn()} label="Jan pending" />)
      expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('1,234,500')
    })

    it('an untouched grouped cell blurs without committing', () => {
      const onCommit = vi.fn()
      render(<MonthCell value={46400} editable={true} onCommit={onCommit} label="Jan pending" />)
      fireEvent.blur(screen.getByRole('textbox'))
      expect(onCommit).not.toHaveBeenCalled()
    })

    describe('legacy fractional server value 999.25 (behaviour identical to before #37)', () => {
      beforeEach(() => vi.useFakeTimers())
      afterEach(() => vi.useRealTimers())

      it('re-displays as-is (no rounding, no .00) and blur commits 1000 with the same toast', () => {
        const onCommit = vi.fn()
        render(
          <>
            <MonthCell value={999.25} editable={true} onCommit={onCommit} label="Jan pending" />
            <NoticeToasts />
          </>,
        )
        const input = screen.getByRole('textbox') as HTMLInputElement
        expect(input.value).toBe('999.25')
        fireEvent.blur(input)
        expect(onCommit).toHaveBeenCalledWith(1000)
        expect(input.value).toBe('1,000')
        expect(screen.getByRole('status')).toHaveTextContent('กรอก 999 · ระบบปรับเป็น 1,000 (ปัดเศษเป็นหลักร้อย)')
      })

      it('groups a fractional legacy value without touching the decimals, and parses it back correctly (1,234.25 -> 1,200)', () => {
        const onCommit = vi.fn()
        render(<MonthCell value={1234.25} editable={true} onCommit={onCommit} label="Jan pending" />)
        const input = screen.getByRole('textbox') as HTMLInputElement
        expect(input.value).toBe('1,234.25')
        fireEvent.blur(input)
        expect(onCommit).toHaveBeenCalledWith(1200)
      })
    })

    describe('caret (real keystrokes via user-event)', () => {
      it('stays right after the typed digits when typing mid-number (no comma moves)', async () => {
        const user = userEvent.setup()
        render(<MonthCell value={1234} editable={true} onCommit={vi.fn()} label="Jan pending" />)
        const input = screen.getByRole('textbox') as HTMLInputElement
        await user.type(input, '50', { initialSelectionStart: 1, initialSelectionEnd: 1 })
        // "1|,234" + "5" + "0" -> 150,234 with the caret after the 0 that was just typed
        expect(input.value).toBe('150,234')
        expect(input.selectionStart).toBe(3)
      })

      it('keeps the caret right after a digit typed mid-number when the comma moves (1,234 -> 19,234)', async () => {
        const user = userEvent.setup()
        render(<MonthCell value={1234} editable={true} onCommit={vi.fn()} label="Jan pending" />)
        const input = screen.getByRole('textbox') as HTMLInputElement
        // caret sits right AFTER the comma ("1,|234"); the typed 9 makes the raw text
        // "1,9234", which regroups to "19,234" — the comma moves, so without the
        // explicit caret restore the browser would throw the caret to the end.
        await user.type(input, '9', { initialSelectionStart: 2, initialSelectionEnd: 2 })
        expect(input.value).toBe('19,234')
        expect(input.selectionStart).toBe(2)
      })

      it('keeps the caret after the last digit when a typed digit adds a new group (999 -> 9,999)', async () => {
        const user = userEvent.setup()
        render(<MonthCell value={999} editable={true} onCommit={vi.fn()} label="Jan pending" />)
        const input = screen.getByRole('textbox') as HTMLInputElement
        await user.type(input, '9')
        expect(input.value).toBe('9,999')
        expect(input.selectionStart).toBe(5)
      })

      it('Backspace right after a comma moves the caret left past it, and the next Backspace deletes the digit', async () => {
        const user = userEvent.setup()
        render(<MonthCell value={25000} editable={true} onCommit={vi.fn()} label="Jan pending" />)
        const input = screen.getByRole('textbox') as HTMLInputElement
        await user.type(input, '{Backspace}', { initialSelectionStart: 3, initialSelectionEnd: 3 })
        expect(input.value).toBe('25,000')
        expect(input.selectionStart).toBe(2)
        await user.keyboard('{Backspace}')
        expect(input.value).toBe('2,000')
        expect(input.selectionStart).toBe(1)
      })
    })
  })

  it('renders disabled with a tooltip when a special-GL row blocks direct edit', () => {
    render(
      <MonthCell
        value={100}
        editable={false}
        onCommit={vi.fn()}
        label="Jan pending"
        disabledReason="แก้ไขผ่านฟอร์มย่อย"
      />,
    )
    const el = screen.getByTitle('แก้ไขผ่านฟอร์มย่อย')
    expect(el).toBeInTheDocument()
  })
})
