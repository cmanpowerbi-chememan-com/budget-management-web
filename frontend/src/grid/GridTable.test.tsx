import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { BudgetRow, GlAccount } from '../api/types'
import { GridTable } from './GridTable'
import { blankLayer, makeRow } from './testUtils'

const GL_REF: GlAccount[] = [
  { gl_code: '5211800030', gl_group: 'Office expenses', gl_name: 'Office COST', is_special: false },
  { gl_code: '6211800030', gl_group: 'Office expenses', gl_name: 'Office SGA', is_special: false },
  { gl_code: '5211900030', gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true },
]

describe('GridTable', () => {
  it('renders all 3 layers for a row (SAP/Approved/Pending)', () => {
    const rows = [
      makeRow({
        cost_center: 'CC1', gl_account: '5211800030', editable: true,
        sap: { ...blankLayer(), m01: 100 } as BudgetRow['sap'],
        board: { ...blankLayer(), m01: 200, gl_name: null, gl_group: null, c_level: null, division: null, department: null } as BudgetRow['board'],
        pending: { ...blankLayer(), m01: 300, template: null, remark: null, gl_name: null, gl_group: null, c_level: null, division: null, department: null, updated_at: null } as BudgetRow['pending'],
      }),
    ]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
    expect(screen.getByTestId('sap-value-CC1-5211800030-m01')).toHaveTextContent('100')
    expect(screen.getByTestId('board-value-CC1-5211800030-m01')).toHaveTextContent('200')
    expect(screen.getByTestId('pending-cell-CC1-5211800030-m01')).toBeInTheDocument()
  })

  it('separates COST (5xxx) and SG&A (6xxx) into two sections that never combine totals', () => {
    const rows = [
      makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true, pending: { ...blankLayer({ m01: 100, total_year: 100 }), template: null, remark: null, gl_name: null, gl_group: null, c_level: null, division: null, department: null, updated_at: null } as BudgetRow['pending'] }),
      makeRow({ cost_center: 'CC1', gl_account: '6211800030', editable: true, pending: { ...blankLayer({ m01: 9999, total_year: 9999 }), template: null, remark: null, gl_name: null, gl_group: null, c_level: null, division: null, department: null, updated_at: null } as BudgetRow['pending'] }),
    ]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
    const costSection = screen.getByTestId('side-section-COST')
    const sgaSection = screen.getByTestId('side-section-SGA')
    expect(costSection).toHaveTextContent('100')
    expect(costSection).not.toHaveTextContent('9,999')
    expect(sgaSection).toHaveTextContent('9,999')
    expect(sgaSection).not.toHaveTextContent('100')
  })

  it('blocks direct edit on a special-GL row even when editable is true', () => {
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211900030', editable: true })]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
    expect(screen.queryByTestId('pending-input-CC1-5211900030-m01')).not.toBeInTheDocument()
    expect(screen.getAllByTitle('แก้ไขผ่านฟอร์มย่อย').length).toBeGreaterThan(0)
  })

  it('calls onCommitMonth with (row, month, value) when an editable Pending cell is changed', () => {
    const onCommitMonth = vi.fn()
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={onCommitMonth} />)
    const input = screen.getByTestId('pending-input-CC1-5211800030-m01')
    fireEvent.change(input, { target: { value: '750' } })
    fireEvent.blur(input)
    expect(onCommitMonth).toHaveBeenCalledWith(rows[0], 'm01', 750)
  })

  it('does not render an input for a non-editable row (See-only scope)', () => {
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: false })]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
    expect(screen.queryByTestId('pending-input-CC1-5211800030-m01')).not.toBeInTheDocument()
  })

  it('shows an empty state when there are no rows', () => {
    render(<GridTable rows={[]} glRef={GL_REF} onCommitMonth={vi.fn()} />)
    expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument()
  })

  it('shows a per-row error message when rowMessages carries one', () => {
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })]
    render(
      <GridTable
        rows={rows}
        glRef={GL_REF}
        onCommitMonth={vi.fn()}
        rowMessages={{ 'CC1|5211800030': { kind: 'error', text: 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น' } }}
      />,
    )
    expect(screen.getByText('ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น')).toBeInTheDocument()
  })
})
