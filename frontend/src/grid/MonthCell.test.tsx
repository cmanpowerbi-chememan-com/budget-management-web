import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MonthCell } from './MonthCell'

describe('MonthCell', () => {
  it('renders a formatted read-only value when not editable', () => {
    render(<MonthCell value={1234} editable={false} onCommit={vi.fn()} label="Jan pending" />)
    expect(screen.getByText('1,234')).toBeInTheDocument()
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
    fireEvent.change(input, { target: { value: '750' } })
    fireEvent.blur(input)
    expect(onCommit).toHaveBeenCalledWith(750)
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

  it('resyncs the displayed value when the value prop changes externally (e.g. a conflict-refetch revert)', () => {
    const { rerender } = render(<MonthCell value={500} editable={true} onCommit={vi.fn()} label="Jan pending" />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    fireEvent.change(input, { target: { value: '999' } }) // user typed a stale edit, never committed
    rerender(<MonthCell value={777} editable={true} onCommit={vi.fn()} label="Jan pending" />)
    expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('777')
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
