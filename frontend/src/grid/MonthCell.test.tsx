import { fireEvent, render, screen } from '@testing-library/react'
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
    expect(input.value).toBe('1005')
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
      expect(input.value).toBe('1234') // the 4th digit is still reachable — a per-keystroke round would have collapsed this to 100
      fireEvent.blur(input)
      expect(input.value).toBe('1200')
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
      expect(input.value).toBe('100000000')
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
