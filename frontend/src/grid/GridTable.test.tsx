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

  it('shows an "เปิดฟอร์มย่อย" button for an editable special-GL row and calls onOpenSpecial with the row + group', () => {
    const onOpenSpecial = vi.fn()
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211900030', editable: true })]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onOpenSpecial={onOpenSpecial} />)
    const openBtn = screen.getByTestId('open-subform-CC1-5211900030')
    fireEvent.click(openBtn)
    expect(onOpenSpecial).toHaveBeenCalledWith(rows[0], 'Entertainment')
  })

  it('does not show the open-subform button for a non-editable (See-only) special-GL row', () => {
    const onOpenSpecial = vi.fn()
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211900030', editable: false })]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onOpenSpecial={onOpenSpecial} />)
    expect(screen.queryByTestId('open-subform-CC1-5211900030')).not.toBeInTheDocument()
    expect(screen.getByText('แก้ไขผ่านฟอร์มย่อย', { exact: false })).toBeInTheDocument()
  })

  it('renders a not-in-master GL row as READ-ONLY reference with the Thai marker, even when editable is true', () => {
    // Live trap this closes: SAP-led rows whose GL is outside the 142-account
    // master come back editable=true from /budget, but PUT /budget/rows would
    // 400 them ("not a recognised GL account") — they must render read-only.
    const rows = [
      makeRow({
        cost_center: 'CC1', gl_account: '5999999999', editable: true,
        sap: { ...blankLayer(), m01: 500 } as BudgetRow['sap'],
      }),
    ]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
    expect(screen.queryByTestId('pending-input-CC1-5999999999-m01')).not.toBeInTheDocument()
    expect(screen.getByTestId('sap-value-CC1-5999999999-m01')).toHaveTextContent('500')
    expect(screen.getByText('อ้างอิง — ยังไม่เปิดให้ตั้งงบ')).toBeInTheDocument()
  })

  it('a not-in-master row becomes editable automatically once the GL master gains the GL (dynamic, no special-casing)', () => {
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5999999999', editable: true })]
    const { rerender } = render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
    expect(screen.queryByTestId('pending-input-CC1-5999999999-m01')).not.toBeInTheDocument()

    const grownRef: GlAccount[] = [
      ...GL_REF,
      { gl_code: '5999999999', gl_group: 'New group', gl_name: 'GL ใหม่', is_special: false },
    ]
    rerender(<GridTable rows={rows} glRef={grownRef} onCommitMonth={vi.fn()} />)
    expect(screen.getByTestId('pending-input-CC1-5999999999-m01')).toBeInTheDocument()
    expect(screen.queryByText('อ้างอิง — ยังไม่เปิดให้ตั้งงบ')).not.toBeInTheDocument()
  })

  it('does NOT show the reference marker on a See-only (editable=false) not-in-master row — read-only as before', () => {
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5999999999', editable: false })]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
    expect(screen.queryByTestId('pending-input-CC1-5999999999-m01')).not.toBeInTheDocument()
    expect(screen.queryByText('อ้างอิง — ยังไม่เปิดให้ตั้งงบ')).not.toBeInTheDocument()
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

  it('renders real month names in the header, a group-head row above it, and a single now-month highlight (UI-parity 8a)', () => {
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)

    const table = screen.getByTestId('side-section-COST').querySelector('table.data-table') as HTMLTableElement
    const rowsEls = table.querySelectorAll('thead tr')
    expect(rowsEls).toHaveLength(2)
    expect(rowsEls[0]).toHaveClass('group-head-row')
    const monthGroupCell = rowsEls[0].querySelector('th[colspan="12"]')
    expect(monthGroupCell).not.toBeNull()

    const monthHeaders = rowsEls[1].querySelectorAll('th.month-col')
    expect(monthHeaders).toHaveLength(12)
    expect(monthHeaders[0].querySelector('.th-label')).toHaveTextContent('Jan')
    expect(monthHeaders[11].querySelector('.th-label')).toHaveTextContent('Dec')

    const nowHeaders = rowsEls[1].querySelectorAll('th.month-col.now')
    expect(nowHeaders).toHaveLength(1)
    expect([...monthHeaders].indexOf(nowHeaders[0] as Element)).toBe(new Date().getMonth())
  })
})
