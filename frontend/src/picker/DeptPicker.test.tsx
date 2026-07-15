import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { DepartmentRow } from '../api/types'
import { DeptPicker } from './DeptPicker'

const ROWS: DepartmentRow[] = [
  { cost_center: '10IT012000', department: 'Solution Delivery', division: 'Digital Technology Division', c_level: 'CTO' },
  { cost_center: '10IT012001', department: 'Solution Delivery', division: 'Digital Technology Division', c_level: 'CTO' },
  { cost_center: '10AC020000', department: 'Budgeting and Management Accounting', division: 'Budgeting and Cost Accounting Division', c_level: 'CFO' },
]

describe('DeptPicker', () => {
  it('shows a placeholder when nothing is selected', () => {
    render(<DeptPicker rows={ROWS} selected={null} onSelect={vi.fn()} />)
    expect(screen.getByText('— เลือกฝ่าย —')).toBeInTheDocument()
  })

  it('shows the selected department name on the trigger', () => {
    render(<DeptPicker rows={ROWS} selected="Solution Delivery" onSelect={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Solution Delivery/ })).toBeInTheDocument()
  })

  it('opens the panel and lists departments with their CC count', () => {
    render(<DeptPicker rows={ROWS} selected={null} onSelect={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /เลือกฝ่าย/ }))
    expect(screen.getByText('Solution Delivery')).toBeInTheDocument()
    expect(screen.getByText('2 CC')).toBeInTheDocument()
  })

  it('filters the list as the user types in the search box', () => {
    render(<DeptPicker rows={ROWS} selected={null} onSelect={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /เลือกฝ่าย/ }))
    fireEvent.change(screen.getByPlaceholderText('ค้นหาฝ่าย…'), { target: { value: 'budgeting' } })
    expect(screen.queryByText('Solution Delivery')).not.toBeInTheDocument()
    expect(screen.getByText('Budgeting and Management Accounting')).toBeInTheDocument()
  })

  it('calls onSelect and closes the panel when a department is clicked', () => {
    const onSelect = vi.fn()
    render(<DeptPicker rows={ROWS} selected={null} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /เลือกฝ่าย/ }))
    fireEvent.click(screen.getByText('Solution Delivery'))
    expect(onSelect).toHaveBeenCalledWith('Solution Delivery')
  })

  it('shows an empty-scope message when there are no departments at all', () => {
    render(<DeptPicker rows={[]} selected={null} onSelect={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /เลือกฝ่าย/ }))
    expect(screen.getByText(/ไม่พบฝ่าย/)).toBeInTheDocument()
  })
})
