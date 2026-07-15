import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { YearPicker } from './YearPicker'

describe('YearPicker', () => {
  it('renders the selected planning year', () => {
    render(<YearPicker year={2027} onChange={vi.fn()} />)
    expect(screen.getByRole('combobox')).toHaveValue('2027')
  })

  it('calls onChange with the picked year as a number', () => {
    const onChange = vi.fn()
    render(<YearPicker year={2027} onChange={onChange} />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2028' } })
    expect(onChange).toHaveBeenCalledWith(2028)
  })

  it('always includes the currently selected year even if outside the default window', () => {
    render(<YearPicker year={2099} onChange={vi.fn()} />)
    expect(screen.getByRole('combobox')).toHaveValue('2099')
  })
})
