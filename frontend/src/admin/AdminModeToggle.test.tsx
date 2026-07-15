import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AdminModeToggle } from './AdminModeToggle'

describe('AdminModeToggle', () => {
  it('reflects the enabled state', () => {
    render(<AdminModeToggle enabled onChange={vi.fn()} />)
    expect(screen.getByTestId('admin-mode-checkbox')).toBeChecked()
  })

  it('calls onChange with the new value when toggled', () => {
    const onChange = vi.fn()
    render(<AdminModeToggle enabled={false} onChange={onChange} />)
    fireEvent.click(screen.getByTestId('admin-mode-checkbox'))
    expect(onChange).toHaveBeenCalledWith(true)
  })
})
