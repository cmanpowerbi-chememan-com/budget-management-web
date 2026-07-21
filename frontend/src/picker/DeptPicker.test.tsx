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

  it('Enter selects the department when the search narrows to exactly one match', () => {
    const onSelect = vi.fn()
    render(<DeptPicker rows={ROWS} selected={null} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /เลือกฝ่าย/ }))
    const search = screen.getByPlaceholderText('ค้นหาฝ่าย…')
    fireEvent.change(search, { target: { value: 'budgeting' } })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith('Budgeting and Management Accounting')
    // panel closed after the pick
    expect(screen.queryByPlaceholderText('ค้นหาฝ่าย…')).not.toBeInTheDocument()
  })

  it('Enter does nothing while more than one department matches', () => {
    const onSelect = vi.fn()
    render(<DeptPicker rows={ROWS} selected={null} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /เลือกฝ่าย/ }))
    const search = screen.getByPlaceholderText('ค้นหาฝ่าย…')
    fireEvent.change(search, { target: { value: 'division' } }) // matches both divisions
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('Escape closes the panel without selecting', () => {
    const onSelect = vi.fn()
    render(<DeptPicker rows={ROWS} selected={null} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /เลือกฝ่าย/ }))
    fireEvent.keyDown(screen.getByPlaceholderText('ค้นหาฝ่าย…'), { key: 'Escape' })
    expect(screen.queryByPlaceholderText('ค้นหาฝ่าย…')).not.toBeInTheDocument()
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('shows an empty-scope message when there are no departments at all', () => {
    render(<DeptPicker rows={[]} selected={null} onSelect={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /เลือกฝ่าย/ }))
    expect(screen.getByText(/ไม่พบฝ่าย/)).toBeInTheDocument()
  })

  it('shows a รออนุมัติ badge on the trigger when the selected department is pending the caller\'s approval', () => {
    render(
      <DeptPicker
        rows={ROWS}
        selected="Solution Delivery"
        onSelect={vi.fn()}
        pendingApprovalDepartments={new Set(['Solution Delivery'])}
      />,
    )
    expect(screen.getByTestId('dept-picker-pending-badge')).toBeInTheDocument()
  })

  it('does not show the badge when the selected department is not pending', () => {
    render(
      <DeptPicker
        rows={ROWS}
        selected="Solution Delivery"
        onSelect={vi.fn()}
        pendingApprovalDepartments={new Set(['Budgeting and Management Accounting'])}
      />,
    )
    expect(screen.queryByTestId('dept-picker-pending-badge')).not.toBeInTheDocument()
  })

  it('shows a รออนุมัติ badge next to each pending department in the list', () => {
    render(
      <DeptPicker
        rows={ROWS}
        selected={null}
        onSelect={vi.fn()}
        pendingApprovalDepartments={new Set(['Solution Delivery'])}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /เลือกฝ่าย/ }))
    const row = screen.getByText('Solution Delivery').closest('button')
    expect(row).not.toBeNull()
    expect(row!.textContent).toContain('รออนุมัติ')
  })
})
