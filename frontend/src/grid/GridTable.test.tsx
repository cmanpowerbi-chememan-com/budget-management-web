import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetRow, GlAccount } from '../api/types'
import { COLUMN_WIDTH_MIN, COLUMN_WIDTHS_STORAGE_KEY } from './model'
import { GridTable } from './GridTable'
import { blankLayer, makeRow, sapLayer } from './testUtils'

const GL_REF: GlAccount[] = [
  { gl_code: '5211800030', gl_group: 'Office expenses', gl_name: 'Office COST', is_special: false },
  { gl_code: '6211800030', gl_group: 'Office expenses', gl_name: 'Office SGA', is_special: false },
  { gl_code: '5211900030', gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true },
  { gl_code: '5210400010', gl_group: 'Travelling Expense', gl_name: 'Per diem', is_special: false },
]

function getTable(testId: string): HTMLTableElement {
  return screen.getByTestId(testId).querySelector('table.data-table') as HTMLTableElement
}

/** The identity-column widths live on the <colgroup>'s first 4 <col>
 * elements (fixed table layout — a width on the col-row <th> is ignored),
 * so that's where width assertions must read. */
function getIdentityCols(table: HTMLTableElement): HTMLTableColElement[] {
  return ([...table.querySelectorAll('colgroup col')] as HTMLTableColElement[]).slice(0, 4)
}

function getTotalYearCol(table: HTMLTableElement): HTMLTableColElement {
  return table.querySelector('colgroup col.total-year-col') as HTMLTableColElement
}

function getMonthCols(table: HTMLTableElement): HTMLTableColElement[] {
  return [...table.querySelectorAll('colgroup col.m-col:not(.total-year-col)')] as HTMLTableColElement[]
}

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
    fireEvent.change(input, { target: { value: '700' } })
    fireEvent.blur(input)
    expect(onCommitMonth).toHaveBeenCalledWith(rows[0], 'm01', 700)
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

  it('shows the locked "🔒 ดูรายละเอียด" variant (still clickable) for a non-editable special-GL row (ADR-0013 read-only lock)', () => {
    const onOpenSpecial = vi.fn()
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211900030', editable: false })]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onOpenSpecial={onOpenSpecial} />)
    const openBtn = screen.getByTestId('open-subform-CC1-5211900030')
    expect(openBtn).toHaveTextContent('🔒 ดูรายละเอียด')
    expect(openBtn).toHaveClass('special-open-btn-locked')
    expect(openBtn).toHaveAttribute('title', 'อ่านอย่างเดียว — แก้ไม่ได้ในสถานะนี้')
    fireEvent.click(openBtn)
    expect(onOpenSpecial).toHaveBeenCalledWith(rows[0], 'Entertainment')
  })

  describe('trailing "ลบ" (delete) column', () => {
    it('shows the delete button for a deletable row (editable, no SAP/Approved, non-Travelling) and calls onDeleteRow with the row', () => {
      const onDeleteRow = vi.fn()
      const base = makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })
      // A deletable row is a persisted pending row — updated_at must be non-null.
      const rows = [{ ...base, pending: { ...base.pending, updated_at: '2026-01-01T00:00:00Z' } }]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onDeleteRow={onDeleteRow} />)
      const deleteBtn = screen.getByTestId('delete-row-CC1-5211800030')
      fireEvent.click(deleteBtn)
      expect(onDeleteRow).toHaveBeenCalledWith(rows[0])
    })

    it('does not show the delete button when onDeleteRow is not provided', () => {
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      expect(screen.queryByTestId('delete-row-CC1-5211800030')).not.toBeInTheDocument()
    })

    it('does not show the delete button for a non-editable (See-only) row', () => {
      const onDeleteRow = vi.fn()
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: false })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onDeleteRow={onDeleteRow} />)
      expect(screen.queryByTestId('delete-row-CC1-5211800030')).not.toBeInTheDocument()
    })

    it('does not show the delete button when the row has a SAP value in any month', () => {
      const onDeleteRow = vi.fn()
      const base = makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })
      const rows = [{ ...base, sap: { ...base.sap, m01: 100 } }]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onDeleteRow={onDeleteRow} />)
      expect(screen.queryByTestId('delete-row-CC1-5211800030')).not.toBeInTheDocument()
    })

    it('does not show the delete button when the row has an Approved (board) value in any month', () => {
      const onDeleteRow = vi.fn()
      const base = makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })
      const rows = [{ ...base, board: { ...base.board, m01: 100 } }]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onDeleteRow={onDeleteRow} />)
      expect(screen.queryByTestId('delete-row-CC1-5211800030')).not.toBeInTheDocument()
    })

    it('does not show the delete button for a Travelling Expense row, even when editable with no SAP/Approved', () => {
      const onDeleteRow = vi.fn()
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5210400010', editable: true })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onDeleteRow={onDeleteRow} />)
      expect(screen.queryByTestId('delete-row-CC1-5210400010')).not.toBeInTheDocument()
    })
  })

  it('renders a not-in-master GL row as READ-ONLY, with no reference marker (server now hides such rows entirely — 2026-07-18 GL-visibility rule)', () => {
    // Historical trap this used to close: before the GL-visibility rule, a
    // SAP-led row whose GL was outside the master could come back
    // editable=true from /budget, and PUT /budget/rows would 400 it ("not a
    // recognised GL account"). The backend now drops such rows from the API
    // response entirely (read_model.merge_budget_rows' master_gl_codes
    // filter), so this is only a defense-in-depth check on the component
    // itself: `isEditableCell`'s glInMaster guard still blocks the input if
    // such a row ever reaches GridTable, but the UI no longer shows the
    // (now-unreachable) "อ้างอิง — ยังไม่เปิดให้ตั้งงบ" text for it.
    const rows = [
      makeRow({
        cost_center: 'CC1', gl_account: '5999999999', editable: true,
        sap: { ...blankLayer(), m01: 500 } as BudgetRow['sap'],
      }),
    ]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
    expect(screen.queryByTestId('pending-input-CC1-5999999999-m01')).not.toBeInTheDocument()
    expect(screen.getByTestId('sap-value-CC1-5999999999-m01')).toHaveTextContent('500')
    expect(screen.queryByText('อ้างอิง — ยังไม่เปิดให้ตั้งงบ')).not.toBeInTheDocument()
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
  })

  it('a See-only (editable=false) not-in-master row also stays read-only', () => {
    const rows = [makeRow({ cost_center: 'CC1', gl_account: '5999999999', editable: false })]
    render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
    expect(screen.queryByTestId('pending-input-CC1-5999999999-m01')).not.toBeInTheDocument()
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

  describe('column filters (UI-parity point 8b)', () => {
    const filterRows = [
      makeRow({ cost_center: 'CC1-North', gl_account: '5211800030', editable: true }),
      makeRow({ cost_center: 'CC2-South', gl_account: '5211900030', editable: true }),
    ]

    it('reduces the visible transaction rows to only the matching cost center', () => {
      render(<GridTable rows={filterRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      expect(screen.getByTestId('txn-CC1-North-5211800030')).toBeInTheDocument()
      expect(screen.getByTestId('txn-CC2-South-5211900030')).toBeInTheDocument()

      fireEvent.change(screen.getByTestId('filter-cc'), { target: { value: 'North' } })

      expect(screen.getByTestId('txn-CC1-North-5211800030')).toBeInTheDocument()
      expect(screen.queryByTestId('txn-CC2-South-5211900030')).not.toBeInTheDocument()
    })

    it('filters by gl_group and clearing the filter restores all rows', () => {
      render(<GridTable rows={filterRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      fireEvent.change(screen.getByTestId('filter-glgroup'), { target: { value: 'Entertainment' } })
      expect(screen.queryByTestId('txn-CC1-North-5211800030')).not.toBeInTheDocument()
      expect(screen.getByTestId('txn-CC2-South-5211900030')).toBeInTheDocument()

      fireEvent.change(screen.getByTestId('filter-glgroup'), { target: { value: '' } })
      expect(screen.getByTestId('txn-CC1-North-5211800030')).toBeInTheDocument()
      expect(screen.getByTestId('txn-CC2-South-5211900030')).toBeInTheDocument()
    })

    it('recomputes the subtotal for the filtered set', () => {
      const twoInSameGroup = [
        makeRow({
          cost_center: 'CC1', gl_account: '5211800030', editable: true,
          pending: { ...blankLayer({ m01: 100, total_year: 100 }), template: null, remark: null, gl_name: null, gl_group: null, c_level: null, division: null, department: null, updated_at: null } as BudgetRow['pending'],
        }),
        makeRow({
          cost_center: 'CC2', gl_account: '5211800030', editable: true,
          pending: { ...blankLayer({ m01: 900, total_year: 900 }), template: null, remark: null, gl_name: null, gl_group: null, c_level: null, division: null, department: null, updated_at: null } as BudgetRow['pending'],
        }),
      ]
      render(<GridTable rows={twoInSameGroup} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const costSection = screen.getByTestId('side-section-COST')
      expect(costSection).toHaveTextContent('1,000') // both rows, subtotal = 100 + 900

      fireEvent.change(screen.getByTestId('filter-cc'), { target: { value: 'CC1' } })
      expect(costSection).not.toHaveTextContent('1,000')
      expect(costSection).toHaveTextContent('100')
    })

    it('renders the side grand total as 3 layer rows, each summing every shown cc+gl row month by month', () => {
      const mkLayer = (m01: number, m02: number) => ({ ...blankLayer({ m01, m02, total_year: m01 + m02 }) })
      const rows = [
        makeRow({
          cost_center: 'CC1', gl_account: '5211800030', editable: true,
          sap: mkLayer(100, 1) as BudgetRow['sap'],
          board: { ...mkLayer(200, 2), gl_name: null, gl_group: null, c_level: null, division: null, department: null } as BudgetRow['board'],
          pending: { ...mkLayer(300, 3), template: null, remark: null, gl_name: null, gl_group: null, c_level: null, division: null, department: null, updated_at: null } as BudgetRow['pending'],
        }),
        makeRow({
          cost_center: 'CC2', gl_account: '5211800030', editable: true,
          sap: mkLayer(10, 0) as BudgetRow['sap'],
          board: { ...mkLayer(20, 0), gl_name: null, gl_group: null, c_level: null, division: null, department: null } as BudgetRow['board'],
          pending: { ...mkLayer(30, 0), template: null, remark: null, gl_name: null, gl_group: null, c_level: null, division: null, department: null, updated_at: null } as BudgetRow['pending'],
        }),
        // One SGA row — the 3-layer grand total must exist on BOTH sides.
        makeRow({
          cost_center: 'CC1', gl_account: '6211800030', editable: true,
          sap: mkLayer(7, 0) as BudgetRow['sap'],
        }),
      ]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      for (const side of ['COST', 'SGA'] as const) {
        const section = screen.getByTestId(`side-section-${side}`)
        expect(within(section).getByText('รวมทั้งหมด · SAP · ใช้จริง')).toBeInTheDocument()
        expect(within(section).getByText('รวมทั้งหมด · Approved · งบ')).toBeInTheDocument()
        expect(within(section).getByText('รวมทั้งหมด · Pending · รออนุมัติ')).toBeInTheDocument()
      }

      const cost = screen.getByTestId('side-section-COST')
      const sapTotal = within(cost).getByText('รวมทั้งหมด · SAP · ใช้จริง').closest('tr') as HTMLElement
      expect(within(sapTotal).getByText('110.00')).toBeInTheDocument() // m01: 100 + 10
      expect(within(sapTotal).getByText('1.00')).toBeInTheDocument() // m02: 1 + 0
      const boardTotal = within(cost).getByText('รวมทั้งหมด · Approved · งบ').closest('tr') as HTMLElement
      expect(within(boardTotal).getByText('220.00')).toBeInTheDocument()
      const pendingTotal = within(cost).getByText('รวมทั้งหมด · Pending · รออนุมัติ').closest('tr') as HTMLElement
      expect(within(pendingTotal).getByText('330.00')).toBeInTheDocument()
      expect(within(pendingTotal).queryByText('110.00')).not.toBeInTheDocument() // layers must not bleed into each other

      const sga = screen.getByTestId('side-section-SGA')
      const sgaSapTotal = within(sga).getByText('รวมทั้งหมด · SAP · ใช้จริง').closest('tr') as HTMLElement
      // Year-total cell = 7 (m01=7 → total_year=7 shows in BOTH cells now).
      expect(sgaSapTotal.querySelector('td.total-year-cell')).toHaveTextContent('7')
    })

    it('shows a รวมทั้งปี (year-total) column BEFORE Jan on data rows and on every subtotal row', () => {
      const rows = [
        makeRow({
          cost_center: 'CC1', gl_account: '5211800030', editable: true,
          sap: blankLayer({ m01: 100, m02: 1, total_year: 101 }) as BudgetRow['sap'],
          board: { ...blankLayer({ m01: 200, total_year: 200 }), gl_name: null, gl_group: null, c_level: null, division: null, department: null } as BudgetRow['board'],
          pending: { ...blankLayer({ m03: 40, total_year: 40 }), template: null, remark: null, gl_name: null, gl_group: null, c_level: null, division: null, department: null, updated_at: null } as BudgetRow['pending'],
        }),
      ]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      // Row-level year totals, one per layer.
      expect(screen.getByTestId('sap-value-CC1-5211800030-year')).toHaveTextContent('101')
      expect(screen.getByTestId('board-value-CC1-5211800030-year')).toHaveTextContent('200')
      expect(screen.getByTestId('pending-cell-CC1-5211800030-year')).toHaveTextContent('40')

      // The year cell sits immediately before the Jan (m01) cell in each layer row.
      const sapYear = screen.getByTestId('sap-value-CC1-5211800030-year')
      expect(sapYear.nextElementSibling).toBe(screen.getByTestId('sap-value-CC1-5211800030-m01'))
      const pendingYear = screen.getByTestId('pending-cell-CC1-5211800030-year')
      expect(pendingYear.nextElementSibling).toBe(screen.getByTestId('pending-cell-CC1-5211800030-m01'))

      // Header: รวมทั้งปี label + a Jan–Dec th before the 12 month th's.
      const table = screen.getByTestId('side-section-COST').querySelector('table.data-table') as HTMLTableElement
      expect(table.querySelector('th.total-year-col .th-label')).toHaveTextContent('Jan–Dec')
      const colRow = table.querySelector('thead tr.col-row') as HTMLTableRowElement
      const ths = [...colRow.querySelectorAll('th')]
      const yearTh = colRow.querySelector('th.total-year-col') as HTMLTableCellElement
      expect(ths.indexOf(yearTh)).toBe(ths.findIndex((th) => th.classList.contains('month-col')) - 1)
      expect(table.querySelector('th.total-year-head .th-label')).toHaveTextContent('รวมทั้งปี')

      // Subtotal rows carry the year total too (group subtotal pending = 40).
      const groupSubtotal = within(table as unknown as HTMLElement).getByText(/รวม Office expenses/).closest('tr') as HTMLElement
      expect(groupSubtotal.querySelector('td.total-year-cell')).toHaveTextContent('40')
      const grandSap = within(table as unknown as HTMLElement).getByText('รวมทั้งหมด · SAP · ใช้จริง').closest('tr') as HTMLElement
      expect(grandSap.querySelector('td.total-year-cell')).toHaveTextContent('101')
    })

    it('filters by the STATUS column — keeps only rows whose matched layer has a value', () => {
      const base = makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })
      const withSap = { ...base, sap: { ...base.sap, m01: 100 } }
      const noSap = makeRow({ cost_center: 'CC2', gl_account: '5211800030', editable: true })
      render(<GridTable rows={[withSap, noSap]} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      fireEvent.change(screen.getByTestId('filter-status'), { target: { value: 'sap' } })

      expect(screen.getByTestId('txn-CC1-5211800030')).toBeInTheDocument()
      expect(screen.queryByTestId('txn-CC2-5211800030')).not.toBeInTheDocument()
    })

    it('shows an empty-filtered message and keeps the filter input editable when nothing matches', () => {
      render(<GridTable rows={filterRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      fireEvent.change(screen.getByTestId('filter-cc'), { target: { value: 'no-such-cc' } })

      expect(screen.getAllByText('ไม่มีรายการที่ตรงกับตัวกรอง').length).toBeGreaterThan(0)
      const ccInput = screen.getByTestId('filter-cc') as HTMLInputElement
      expect(ccInput).toBeInTheDocument()
      expect(ccInput.value).toBe('no-such-cc')

      fireEvent.change(ccInput, { target: { value: '' } })
      expect(screen.getByTestId('txn-CC1-North-5211800030')).toBeInTheDocument()
    })

    it('applies the same shared filter to both the COST and SGA tables', () => {
      const bothSides = [
        makeRow({ cost_center: 'CC1-North', gl_account: '5211800030', editable: true }),
        makeRow({ cost_center: 'CC1-North', gl_account: '6211800030', editable: true }),
        makeRow({ cost_center: 'CC2-South', gl_account: '5211900030', editable: true }),
      ]
      render(<GridTable rows={bothSides} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      // Both side-tables render their own `filter-cc` input (one per table),
      // but both are bound to the SAME `colFilters` state — changing either
      // one filters both tables identically.
      fireEvent.change(screen.getAllByTestId('filter-cc')[0], { target: { value: 'North' } })

      expect(screen.getByTestId('txn-CC1-North-5211800030')).toBeInTheDocument()
      expect(screen.getByTestId('txn-CC1-North-6211800030')).toBeInTheDocument()
      expect(screen.queryByTestId('txn-CC2-South-5211900030')).not.toBeInTheDocument()
    })

    it('renders a col-filter input under the Status th and a col-filter-spacer under every month th', () => {
      render(<GridTable rows={filterRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const table = screen.getByTestId('side-section-COST').querySelector('table.data-table') as HTMLTableElement
      const colRow = table.querySelector('thead tr.col-row') as HTMLTableRowElement
      const ths = [...colRow.querySelectorAll('th')]
      const statusTh = ths.find((th) => th.querySelector('.th-label')?.textContent === 'Status')
      // Status got its own filter input (2026-07-21) — months keep spacers.
      expect(statusTh?.querySelector('[data-testid="filter-status"]')).toBeInTheDocument()
      const monthThs = colRow.querySelectorAll('th.month-col')
      expect(monthThs).toHaveLength(12)
      monthThs.forEach((th) => expect(th.querySelector('.col-filter-spacer')).toBeInTheDocument())
    })
  })

  describe('fit-to-content default column widths (UI-parity point 8d)', () => {
    afterEach(() => {
      window.localStorage.clear()
    })

    const bothSidesRows = [
      makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true }),
      makeRow({ cost_center: 'CC1', gl_account: '6211800030', editable: true }),
    ]

    it('defaults the identity columns to a content-fitted width, not the old 130/150/150 — both tables aligned, frz tracking it', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const costTable = getTable('side-section-COST')
      const sgaTable = getTable('side-section-SGA')
      const [costCc, costGl] = getIdentityCols(costTable)
      const [sgaCc, sgaGl] = getIdentityCols(sgaTable)

      // jsdom never lays out real text (every measurement reads 0), so the
      // fit-to-content pass deterministically floors to COLUMN_WIDTH_MIN —
      // which is still strictly LESS than the old hardcoded 130px default,
      // proving this is no longer a fixed constant. A real browser
      // (Playwright verify) measures actual text and lands above this floor.
      expect(parseInt(costCc.style.width, 10)).toBe(COLUMN_WIDTH_MIN)
      expect(parseInt(costCc.style.width, 10)).toBeLessThan(130)
      expect(costCc.style.width).toBe(sgaCc.style.width) // both tables agree
      expect(costGl.style.width).toBe(sgaGl.style.width)

      expect(costTable.style.getPropertyValue('--frz2')).toBe(costCc.style.width)
      expect(costTable.style.getPropertyValue('--frz3')).toBe(
        `${parseInt(costCc.style.width, 10) + parseInt(costGl.style.width, 10)}px`,
      )
      // Remark joined the frozen identity columns — frz4 sits at its left
      // edge (cc + gl + glGroup).
      const costGlGroup = getIdentityCols(costTable)[2]
      expect(costTable.style.getPropertyValue('--frz4')).toBe(
        `${parseInt(costCc.style.width, 10) + parseInt(costGl.style.width, 10) + parseInt(costGlGroup.style.width, 10)}px`,
      )
    })

    it('a saved localStorage width WINS over the fit-to-content default on mount (does not get auto-overwritten)', () => {
      window.localStorage.setItem(COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify({ cc: 222, gl: 111, glGroup: 99 }))
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const costCc = getIdentityCols(getTable('side-section-COST'))[0]
      expect(costCc.style.width).toBe('222px')
    })

    it('a manual drag override is NOT clobbered by a later data change (rows prop changes)', () => {
      const { rerender } = render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const handle = screen.getAllByTestId('col-resize-cc')[0]
      fireEvent.mouseDown(handle, { clientX: 0 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: 275, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: 275, bubbles: true }))
      const draggedWidth = getIdentityCols(getTable('side-section-COST'))[0].style.width

      // A brand-new rows array (new reference, as a real refetch would
      // produce) must NOT trigger a re-measure that overwrites the user's
      // explicit choice.
      const newRows = [makeRow({ cost_center: 'CC-DIFFERENT', gl_account: '5211800030', editable: true })]
      rerender(<GridTable rows={newRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      expect(getIdentityCols(getTable('side-section-COST'))[0].style.width).toBe(draggedWidth)
    })
  })

  describe('money column width — total row never overflows into the next cell (bug fix 2026-08-20)', () => {
    const bothSidesRows = [
      makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true }),
      makeRow({ cost_center: 'CC1', gl_account: '6211800030', editable: true }),
    ]

    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('defaults month/total-year columns to the unchanged CSS floor (98px/112px) when nothing overflows', () => {
      // jsdom never lays out real text (every measurement reads 0, same
      // caveat the identity-column fit-to-content tests document above) —
      // this pins the deterministic floor so a real browser's growth (proved
      // in e2e/edge-states.spec.ts 4.7) is a pure ADDITION on top, never a
      // silent regression to a smaller default.
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const table = getTable('side-section-COST')
      expect(getTotalYearCol(table).style.width).toBe('112px')
      getMonthCols(table).forEach((col) => expect(col.style.width).toBe('98px'))
    })

    it('the grand-total row now wraps its money text in a .month-value span, same as every data-row cell', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const cost = screen.getByTestId('side-section-COST')
      const grandSapRow = within(cost).getByText('รวมทั้งหมด · SAP · ใช้จริง').closest('tr') as HTMLElement
      const yearCell = grandSapRow.querySelector('td.total-year-cell') as HTMLElement
      // Before the fix this was a bare text node directly in the <td> — a
      // subtotal figure was invisible to any content-aware measurement
      // because there was no element to measure at all.
      expect(yearCell.querySelector('span.month-value')).not.toBeNull()
    })

    it('a huge rendered total-year figure grows col.total-year-col beyond the 112px floor (stubbed real-browser geometry)', () => {
      // Simulates what e2e/edge-states.spec.ts 4.7 proves against a real
      // browser: stub every .month-value pill's natural width the way a
      // real font would render it (proportional to its own text length),
      // so a 12-digit total measures far wider than an ordinary figure.
      vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
        const width = this.classList?.contains('month-value') ? this.textContent!.length * 8 : 0
        return { width, height: 0, top: 0, left: 0, right: width, bottom: 0, x: 0, y: 0, toJSON: () => undefined }
      })
      const rows = [
        makeRow({
          cost_center: 'CC1',
          gl_account: '5211800030',
          editable: true,
          sap: sapLayer({ total_year: 121394056573.9, m01: 3601222.21 }),
        }),
      ]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      const table = getTable('side-section-COST')
      // "121,394,056,573.90" = 19 chars * 8px = 152px stubbed width; fitColumnWidth
      // adds the 32px cell-padding allowance -> 184px, well past the 112px floor.
      expect(parseInt(getTotalYearCol(table).style.width, 10)).toBeGreaterThan(112)
      // Every month col shares ONE width (the widest candidate across the
      // whole grid) — still floors correctly for the untouched columns.
      getMonthCols(table).forEach((col) => expect(parseInt(col.style.width, 10)).toBeGreaterThanOrEqual(98))
    })
  })

  describe('column resize & reset (UI-parity point 8c)', () => {
    afterEach(() => {
      window.localStorage.clear()
    })

    const bothSidesRows = [
      makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true }),
      makeRow({ cost_center: 'CC1', gl_account: '6211800030', editable: true }),
    ]

    it('renders a drag handle on each of the 4 identity columns, in both side-tables', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      expect(screen.getAllByTestId('col-resize-cc')).toHaveLength(2) // COST + SGA tables
      expect(screen.getAllByTestId('col-resize-gl')).toHaveLength(2)
      expect(screen.getAllByTestId('col-resize-glgroup')).toHaveLength(2)
      expect(screen.getAllByTestId('col-resize-remark')).toHaveLength(2)
    })

    it('dragging the Cost Center handle widens the column, updates --frz2/--frz3, and keeps both tables aligned', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const handle = screen.getAllByTestId('col-resize-cc')[0]
      // Read the fit-to-content STARTING width dynamically (point 8d made
      // this a measured default, not a hardcoded 130) — the drag delta is
      // what this test actually cares about.
      const startCc = parseInt(getIdentityCols(getTable('side-section-COST'))[0].style.width, 10)
      const startGl = parseInt(getIdentityCols(getTable('side-section-COST'))[1].style.width, 10)

      fireEvent.mouseDown(handle, { clientX: 100 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: 150, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: 150, bubbles: true }))

      const costTable = getTable('side-section-COST')
      const sgaTable = getTable('side-section-SGA')
      const costCcCol = getIdentityCols(costTable)[0]
      const sgaCcCol = getIdentityCols(sgaTable)[0]

      expect(costCcCol.style.width).toBe(`${startCc + 50}px`) // +50px drag
      expect(sgaCcCol.style.width).toBe(`${startCc + 50}px`) // shared state — both tables stay aligned
      expect(costTable.style.getPropertyValue('--frz2')).toBe(`${startCc + 50}px`)
      expect(costTable.style.getPropertyValue('--frz3')).toBe(`${startCc + 50 + startGl}px`)
      expect(sgaTable.style.getPropertyValue('--frz2')).toBe(`${startCc + 50}px`)
      expect(sgaTable.style.getPropertyValue('--frz3')).toBe(`${startCc + 50 + startGl}px`)
    })

    it('clamps a huge drag to the 800px maximum and a large-negative drag to the 60px minimum', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const handle = screen.getAllByTestId('col-resize-cc')[0]

      fireEvent.mouseDown(handle, { clientX: 0 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: 5000, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: 5000, bubbles: true }))
      expect(getIdentityCols(getTable('side-section-COST'))[0].style.width).toBe('800px')

      fireEvent.mouseDown(handle, { clientX: 0 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: -5000, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: -5000, bubbles: true }))
      expect(getIdentityCols(getTable('side-section-COST'))[0].style.width).toBe('60px')
    })

    it('"Reset columns" re-measures fit-to-content (NOT a hardcoded 130/150/150), incl. --frz2 tracking it, and clears the localStorage override', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const handle = screen.getAllByTestId('col-resize-cc')[0]
      const startCc = parseInt(getIdentityCols(getTable('side-section-COST'))[0].style.width, 10)
      fireEvent.mouseDown(handle, { clientX: 0 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: 300, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: 300, bubbles: true }))
      expect(getIdentityCols(getTable('side-section-COST'))[0].style.width).toBe(`${startCc + 300}px`)
      expect(window.localStorage.getItem(COLUMN_WIDTHS_STORAGE_KEY)).not.toBeNull() // drag persisted an override

      // The button renders once per side-section now (beside each heading,
      // not in a standalone row) — but colWidths is still ONE shared state,
      // so either button must reset both tables.
      expect(screen.getByTestId('reset-columns-btn-SGA')).toBeInTheDocument()
      fireEvent.click(screen.getByTestId('reset-columns-btn-COST'))

      const costTable = getTable('side-section-COST')
      // Re-measured fit-to-content — in jsdom (no real text layout) that is
      // deterministically the padding-only floor, i.e. COLUMN_WIDTH_MIN; a
      // real browser (Playwright verify) gets the true content-fitted value.
      expect(getIdentityCols(costTable)[0].style.width).toBe(`${startCc}px`)
      expect(costTable.style.getPropertyValue('--frz2')).toBe(`${startCc}px`)
      expect(window.localStorage.getItem(COLUMN_WIDTHS_STORAGE_KEY)).toBeNull() // override cleared, not re-saved
    })

    it('the SGA reset button also clears the shared colWidths override (same state as COST)', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const handle = screen.getAllByTestId('col-resize-cc')[0]
      const startCc = parseInt(getIdentityCols(getTable('side-section-COST'))[0].style.width, 10)
      fireEvent.mouseDown(handle, { clientX: 0 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: 300, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: 300, bubbles: true }))

      fireEvent.click(screen.getByTestId('reset-columns-btn-SGA'))

      const sgaTable = getTable('side-section-SGA')
      expect(getIdentityCols(sgaTable)[0].style.width).toBe(`${startCc}px`)
      expect(window.localStorage.getItem(COLUMN_WIDTHS_STORAGE_KEY)).toBeNull()
    })

    it('adds is-dragging to ONLY the handle being dragged (mockup accent-hairline parity)', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const ccHandle = screen.getAllByTestId('col-resize-cc')[0]
      const glHandle = screen.getAllByTestId('col-resize-gl')[0]

      fireEvent.mouseDown(ccHandle, { clientX: 0 })
      expect(ccHandle).toHaveClass('is-dragging')
      expect(glHandle).not.toHaveClass('is-dragging')

      fireEvent(window, new MouseEvent('mouseup', { clientX: 0, bubbles: true }))
      expect(ccHandle).not.toHaveClass('is-dragging')
    })

    it('adds body.col-dragging while a drag is in flight and removes it on mouseup', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const handle = screen.getAllByTestId('col-resize-cc')[0]
      fireEvent.mouseDown(handle, { clientX: 0 })
      expect(document.body.classList.contains('col-dragging')).toBe(true)
      fireEvent(window, new MouseEvent('mouseup', { clientX: 0, bubbles: true }))
      expect(document.body.classList.contains('col-dragging')).toBe(false)
    })

    it('does not leak window-level drag listeners after unmount mid-drag', () => {
      const removeSpy = vi.spyOn(window, 'removeEventListener')
      const { unmount } = render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const handle = screen.getAllByTestId('col-resize-cc')[0]
      fireEvent.mouseDown(handle, { clientX: 0 }) // start a drag, never fire mouseup
      unmount()
      const removedTypes = removeSpy.mock.calls.map((call) => call[0])
      expect(removedTypes).toEqual(expect.arrayContaining(['mousemove', 'mouseup']))
      expect(document.body.classList.contains('col-dragging')).toBe(false)
      removeSpy.mockRestore()
    })
  })

  describe('remark column (mockup 0002.3 lines 1163-1166 / 2246-2249)', () => {
    afterEach(() => {
      window.localStorage.clear()
    })

    const pendingWithRemark = (remark: string | null) =>
      ({
        ...blankLayer(),
        template: null, remark, gl_name: null, gl_group: null, c_level: null, division: null, department: null, updated_at: null,
      }) as BudgetRow['pending']

    it('renders a Remark header with a col-filter input between GL Group and Status', () => {
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const table = screen.getByTestId('side-section-COST').querySelector('table.data-table') as HTMLTableElement
      const labels = [...table.querySelectorAll('thead tr.col-row th .th-label')].map((el) => el.textContent)
      expect(labels.slice(0, 5)).toEqual(['Cost Center', 'GL Code', 'GL Group', 'Remark', 'Status'])
      expect(screen.getByTestId('filter-remark')).toBeInTheDocument()
    })

    it('is the 4th FROZEN identity column: frz-4 header + body cell, drag-resize widens the colgroup col', () => {
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const table = screen.getByTestId('side-section-COST').querySelector('table.data-table') as HTMLTableElement

      const remarkTh = [...table.querySelectorAll('thead tr.col-row th')].find(
        (th) => th.querySelector('.th-label')?.textContent === 'Remark',
      ) as HTMLTableCellElement
      expect(remarkTh).toHaveClass('frz', 'frz-4')
      const remarkBodyCell = table.querySelector('td.remark-cell') as HTMLTableCellElement
      expect(remarkBodyCell).toHaveClass('frz', 'frz-4')

      const remarkCol = getIdentityCols(table)[3]
      const startWidth = parseInt(remarkCol.style.width, 10)
      const handle = screen.getByTestId('col-resize-remark')
      fireEvent.mouseDown(handle, { clientX: 100 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: 180, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: 180, bubbles: true }))
      expect(getIdentityCols(table)[3].style.width).toBe(`${startWidth + 80}px`)
    })

    it('shows an editable input for an editable row and commits the trimmed text on blur', () => {
      const onCommitRemark = vi.fn()
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onCommitRemark={onCommitRemark} />)
      const input = screen.getByTestId('remark-input-CC1-5211800030')
      fireEvent.change(input, { target: { value: '  อุปกรณ์สำนักงาน IT  ' } })
      fireEvent.blur(input)
      expect(onCommitRemark).toHaveBeenCalledWith(rows[0], 'อุปกรณ์สำนักงาน IT')
    })

    it('does not commit when the remark is unchanged on blur', () => {
      const onCommitRemark = vi.fn()
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true, pending: pendingWithRemark('เดิม') })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onCommitRemark={onCommitRemark} />)
      const input = screen.getByTestId('remark-input-CC1-5211800030')
      expect((input as HTMLInputElement).value).toBe('เดิม')
      fireEvent.blur(input)
      expect(onCommitRemark).not.toHaveBeenCalled()
    })

    it('renders read-only remark text for a See-only row (no input)', () => {
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: false, pending: pendingWithRemark('งบกลาง') })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onCommitRemark={vi.fn()} />)
      expect(screen.queryByTestId('remark-input-CC1-5211800030')).not.toBeInTheDocument()
      expect(screen.getByTestId('remark-text-CC1-5211800030')).toHaveTextContent('งบกลาง')
    })

    it('renders read-only remark for a special-GL row even when editable (backend rejects /budget/rows for special GLs)', () => {
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211900030', editable: true, pending: pendingWithRemark('เลี้ยงรับรอง') })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onCommitRemark={vi.fn()} />)
      expect(screen.queryByTestId('remark-input-CC1-5211900030')).not.toBeInTheDocument()
      expect(screen.getByTestId('remark-text-CC1-5211900030')).toHaveTextContent('เลี้ยงรับรอง')
    })

    it('filters rows by remark text across both side-tables', () => {
      const rows = [
        makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true, pending: pendingWithRemark('Notebook lease') }),
        makeRow({ cost_center: 'CC2', gl_account: '6211800030', editable: true, pending: pendingWithRemark('ที่ปรึกษาระบบ') }),
      ]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      // One filter-remark input per side-table, both bound to the same
      // shared colFilters state — typing in the first filters both tables.
      fireEvent.change(screen.getAllByTestId('filter-remark')[0], { target: { value: 'note' } })
      expect(screen.getByTestId('txn-CC1-5211800030')).toBeInTheDocument()
      expect(screen.queryByTestId('txn-CC2-6211800030')).not.toBeInTheDocument()

      fireEvent.change(screen.getAllByTestId('filter-remark')[0], { target: { value: '' } })
      expect(screen.getByTestId('txn-CC1-5211800030')).toBeInTheDocument()
      expect(screen.getByTestId('txn-CC2-6211800030')).toBeInTheDocument()
    })
  })

  describe('compact mode ("ซ่อนคอลัมน์" toggle on the Status header — jakkaritw-approved 2026-07-21)', () => {
    const bothSidesRows = [
      makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true }), // COST, Office expenses
      makeRow({ cost_center: 'CC1', gl_account: '6211800030', editable: true }), // SGA, Office expenses
    ]

    // Both side-tables (COST/SGA) render their own copy of the collapse/
    // expand button (same convention as filter-cc/col-resize-cc elsewhere in
    // this file) — clicking ANY of them flips the ONE shared columnsCollapsed
    // state, which is exactly what proves both tables toggle together.
    function clickFirstCollapseButton() {
      fireEvent.click(screen.getAllByTestId('collapse-columns-btn')[0])
    }
    function clickFirstExpandButton() {
      fireEvent.click(screen.getAllByTestId('expand-columns-btn')[0])
    }

    it('shows the collapse button (one per side-table) in expanded state, with GL Group/Remark/Status content visible', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      expect(screen.getAllByTestId('collapse-columns-btn')).toHaveLength(2)
      expect(screen.queryAllByTestId('expand-columns-btn')).toHaveLength(0)
      expect(screen.getAllByText('Office expenses').length).toBeGreaterThan(0)
      expect(screen.getByTestId('remark-text-CC1-5211800030')).toBeInTheDocument()
      expect(screen.getAllByText('SAP · ใช้จริง').length).toBeGreaterThan(0)
    })

    it('clicking collapse hides GL Group/Remark/Status but keeps CC/GL/month values, and swaps the toggle button', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      clickFirstCollapseButton()

      // Scoped to the visible side-section — the hidden fit-to-content
      // measurer (UI-parity 8d) always renders "Office expenses" as a width
      // candidate regardless of compact mode, which is unrelated to this
      // feature and would otherwise false-negative a document-wide query.
      expect(within(screen.getByTestId('side-section-COST')).queryByText('Office expenses')).not.toBeInTheDocument()
      expect(screen.queryByTestId('remark-text-CC1-5211800030')).not.toBeInTheDocument()
      expect(screen.queryByText('SAP · ใช้จริง')).not.toBeInTheDocument()
      expect(screen.queryAllByTestId('collapse-columns-btn')).toHaveLength(0)
      expect(screen.getAllByTestId('expand-columns-btn')).toHaveLength(2)

      expect(screen.getByTestId('txn-CC1-5211800030')).toHaveTextContent('5211800030')
      expect(screen.getByTestId('sap-value-CC1-5211800030-m01')).toBeInTheDocument()
    })

    it('clicking expand restores GL Group/Remark/Status', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      clickFirstCollapseButton()
      clickFirstExpandButton()

      expect(screen.getAllByTestId('collapse-columns-btn')).toHaveLength(2)
      expect(screen.queryAllByTestId('expand-columns-btn')).toHaveLength(0)
      expect(screen.getAllByText('Office expenses').length).toBeGreaterThan(0)
      expect(screen.getByTestId('remark-text-CC1-5211800030')).toBeInTheDocument()
      expect(screen.getAllByText('SAP · ใช้จริง').length).toBeGreaterThan(0)
    })

    it('one click collapses BOTH side tables (COST and SGA)', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      clickFirstCollapseButton()

      expect(screen.getByTestId('txn-CC1-5211800030')).toBeInTheDocument() // COST row
      expect(screen.getByTestId('txn-CC1-6211800030')).toBeInTheDocument() // SGA row
      expect(screen.queryByText('SAP · ใช้จริง')).not.toBeInTheDocument()
      expect(screen.queryByTestId('remark-text-CC1-6211800030')).not.toBeInTheDocument()
    })

    it('a special editable row in compact mode shows the ↗ button in the GL cell and fires onOpenSpecial', () => {
      const onOpenSpecial = vi.fn()
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211900030', editable: true })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onOpenSpecial={onOpenSpecial} />)
      clickFirstCollapseButton()

      const openBtn = screen.getByTestId('open-subform-CC1-5211900030')
      fireEvent.click(openBtn)
      expect(onOpenSpecial).toHaveBeenCalledWith(rows[0], 'Entertainment')
    })

    it('a non-editable (See-only) special row shows the locked 🔒 icon button (still clickable) in compact mode', () => {
      const onOpenSpecial = vi.fn()
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211900030', editable: false })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} onOpenSpecial={onOpenSpecial} />)
      clickFirstCollapseButton()

      const openBtn = screen.getByTestId('open-subform-CC1-5211900030')
      expect(openBtn).toHaveTextContent('🔒')
      expect(openBtn).toHaveClass('special-open-btn-locked')
      fireEvent.click(openBtn)
      expect(onOpenSpecial).toHaveBeenCalledWith(rows[0], 'Entertainment')
    })

    it('Pending month inputs stay editable and commit still fires in compact mode', () => {
      const onCommitMonth = vi.fn()
      const rows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={onCommitMonth} />)
      clickFirstCollapseButton()

      const input = screen.getByTestId('pending-input-CC1-5211800030-m01')
      fireEvent.change(input, { target: { value: '700' } })
      fireEvent.blur(input)
      expect(onCommitMonth).toHaveBeenCalledWith(rows[0], 'm01', 700)
    })

    it('a glGroup filter stays applied after collapsing (a filter on a now-hidden column is not cleared)', () => {
      const rows = [
        makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true }), // Office expenses
        makeRow({ cost_center: 'CC2', gl_account: '5211900030', editable: true }), // Entertainment
      ]
      render(<GridTable rows={rows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      fireEvent.change(screen.getAllByTestId('filter-glgroup')[0], { target: { value: 'Entertainment' } })
      expect(screen.queryByTestId('txn-CC1-5211800030')).not.toBeInTheDocument()
      expect(screen.getByTestId('txn-CC2-5211900030')).toBeInTheDocument()

      clickFirstCollapseButton()

      expect(screen.queryByTestId('txn-CC1-5211800030')).not.toBeInTheDocument()
      expect(screen.getByTestId('txn-CC2-5211900030')).toBeInTheDocument()
    })

    it('the subtotal row still renders its label in compact mode', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      clickFirstCollapseButton()
      expect(screen.getAllByText(/รวม/).length).toBeGreaterThan(0)
    })
  })

  describe('fullscreen toggle (⤢ top-left of the group-head band — jakkaritw-approved 2026-07-31)', () => {
    const bothSidesRows = [
      makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true }), // COST, Office expenses
      makeRow({ cost_center: 'CC1', gl_account: '6211800030', editable: true }), // SGA, Office expenses
    ]

    function groupHeadRow(sectionTestId: string): HTMLTableRowElement {
      return screen.getByTestId(sectionTestId).querySelector('tr.group-head-row') as HTMLTableRowElement
    }

    it('renders one enter-fullscreen-btn per side-table, inside the group-head row\'s first frozen th', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} onToggleFullscreen={vi.fn()} />)
      // One per side-table, exactly like collapse-columns-btn — either copy
      // flips the ONE shared state (owned by BudgetGrid).
      expect(screen.getAllByTestId('enter-fullscreen-btn')).toHaveLength(2)
      for (const section of ['side-section-COST', 'side-section-SGA']) {
        const firstTh = groupHeadRow(section).querySelector('th.frz.frz-1') as HTMLElement
        expect(within(firstTh).getByTestId('enter-fullscreen-btn')).toBeInTheDocument()
      }
    })

    it('clicking it calls onToggleFullscreen exactly once', () => {
      const onToggleFullscreen = vi.fn()
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} onToggleFullscreen={onToggleFullscreen} />)
      fireEvent.click(screen.getAllByTestId('enter-fullscreen-btn')[0])
      expect(onToggleFullscreen).toHaveBeenCalledTimes(1)
    })

    it('isFullscreen swaps to the exit button with pressed state and the Esc-hint label', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} isFullscreen onToggleFullscreen={vi.fn()} />)
      expect(screen.queryAllByTestId('enter-fullscreen-btn')).toHaveLength(0)
      const exitBtns = screen.getAllByTestId('exit-fullscreen-btn')
      expect(exitBtns).toHaveLength(2)
      expect(exitBtns[0]).toHaveAttribute('aria-pressed', 'true')
      expect(exitBtns[0]).toHaveAttribute('aria-label', 'ย่อกลับขนาดปกติ (Esc)')
    })

    it('is still rendered in BOTH column modes — after collapsing it sits in the colSpan=2 band th', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} onToggleFullscreen={vi.fn()} />)
      fireEvent.click(screen.getAllByTestId('collapse-columns-btn')[0])
      expect(screen.getAllByTestId('enter-fullscreen-btn')).toHaveLength(2)
      const firstTh = groupHeadRow('side-section-COST').querySelector('th.frz.frz-1') as HTMLElement
      expect(firstTh).toHaveAttribute('colspan', '2')
      expect(within(firstTh).getByTestId('enter-fullscreen-btn')).toBeInTheDocument()
    })

    it('structural guard: the button is a CHILD of the existing th — group-head cell counts and colSpans are unchanged', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} onToggleFullscreen={vi.fn()} />)
      // Expanded: [identity colSpan=4][Status][รวมทั้งปี][months colSpan=12][action]
      const expanded = groupHeadRow('side-section-COST')
      expect(expanded.cells).toHaveLength(5)
      expect(expanded.cells[0]).toHaveAttribute('colspan', '4')

      fireEvent.click(screen.getAllByTestId('collapse-columns-btn')[0])
      // Collapsed: [identity colSpan=2][รวมทั้งปี][months colSpan=12][action]
      const collapsed = groupHeadRow('side-section-COST')
      expect(collapsed.cells).toHaveLength(4)
      expect(collapsed.cells[0]).toHaveAttribute('colspan', '2')
    })

    it('without the fullscreen props (existing call style) the button still renders and clicking it does not throw', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const btn = screen.getAllByTestId('enter-fullscreen-btn')[0]
      expect(btn).toHaveAttribute('aria-pressed', 'false')
      expect(() => fireEvent.click(btn)).not.toThrow()
    })
  })

  describe('last-table measured max-height (replaces hardcoded 380px/260px reserve)', () => {
    const bothSidesRows = [
      makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true }), // COST, Office expenses
      makeRow({ cost_center: 'CC1', gl_account: '6211800030', editable: true }), // SGA, Office expenses
    ]
    const onlyCostRows = [makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true })]

    const ORIGINAL_INNER_HEIGHT = window.innerHeight

    function setInnerHeight(px: number) {
      Object.defineProperty(window, 'innerHeight', { value: px, configurable: true })
    }

    /** jsdom never lays out real geometry (`getBoundingClientRect` always
     * reports zeros) — stub it on one element so the measured-reserve math
     * has a real, known number to compute from. Returns the spy so callers
     * can also assert call counts (proves whether a recompute actually
     * re-read the element, not just that the final number looks right). */
    function stubHeight(el: Element, height: number) {
      return vi.spyOn(el, 'getBoundingClientRect').mockReturnValue({
        height, width: 0, top: 0, left: 0, right: 0, bottom: 0, x: 0, y: 0, toJSON: () => undefined,
      })
    }

    /** jsdom has no `ResizeObserver` at all, so the RO branch in GridTable
     * (`typeof ResizeObserver !== 'undefined'`) is otherwise never
     * exercised. Minimal stub, scoped to this describe block only via
     * `vi.stubGlobal` in `beforeEach`/`vi.unstubAllGlobals` in `afterEach`
     * below — never added to `src` or to the shared `test/setup.ts`. */
    class FakeResizeObserver {
      static instances: FakeResizeObserver[] = []
      readonly disconnect = vi.fn()
      private readonly callback: ResizeObserverCallback
      constructor(callback: ResizeObserverCallback) {
        this.callback = callback
        FakeResizeObserver.instances.push(this)
      }
      observe() {
        /* no-op — GridTable's callback (`recompute`) ignores the target and
           re-reads live DOM state instead, so nothing to track here. */
      }
      unobserve() {}
      /** Simulates the browser reporting an observed size change. */
      trigger() {
        this.callback([], this as unknown as ResizeObserver)
      }
    }

    beforeEach(() => {
      FakeResizeObserver.instances = []
      vi.stubGlobal('ResizeObserver', FakeResizeObserver)
    })

    /** GridTable measures `.nav` / the approval bar (`.approval-bar`,
     * falling back to `[data-testid="approval-bar"]`) / the shared
     * `.budget-grid` ancestor via `document.querySelector` — all three
     * normally live in BudgetGrid, one level up. GridTable is unit-tested
     * in isolation here, so build a minimal stand-in for that page-level
     * chrome and clean it up in `afterEach` below. The approval bar carries
     * BOTH the class and the testid, matching the real
     * `ApprovalActionBar.tsx` (which renders both on every branch). */
    function mountChrome({
      navHeight,
      approvalHeight,
      budgetGridMarginBottom,
      budgetGridPaddingBottom,
    }: {
      navHeight: number
      approvalHeight: number
      /** `.budget-grid`'s own margin-bottom (normal mode, global.css:471 =
       * 60px in production) — set as an inline style so `getComputedStyle`
       * can read it back. */
      budgetGridMarginBottom?: number
      /** `.budget-grid.is-fullscreen`'s padding-bottom (fullscreen mode,
       * global.css:488 = 28px in production). */
      budgetGridPaddingBottom?: number
    }) {
      const budgetGrid = document.createElement('div')
      budgetGrid.className = 'budget-grid'
      if (budgetGridMarginBottom !== undefined) budgetGrid.style.marginBottom = `${budgetGridMarginBottom}px`
      if (budgetGridPaddingBottom !== undefined) budgetGrid.style.paddingBottom = `${budgetGridPaddingBottom}px`
      document.body.appendChild(budgetGrid)
      const nav = document.createElement('div')
      nav.className = 'nav'
      stubHeight(nav, navHeight)
      document.body.appendChild(nav)
      const approvalBar = document.createElement('div')
      approvalBar.className = 'approval-bar'
      approvalBar.setAttribute('data-testid', 'approval-bar')
      const approvalSpy = stubHeight(approvalBar, approvalHeight)
      budgetGrid.appendChild(approvalBar)
      return { budgetGrid, approvalBar, approvalSpy }
    }

    afterEach(() => {
      document.querySelectorAll('.nav, .budget-grid').forEach((el) => el.remove())
      setInnerHeight(ORIGINAL_INNER_HEIGHT)
      vi.restoreAllMocks()
      vi.unstubAllGlobals()
    })

    it('applies a computed inline max-height to the LAST rendered section only, leaving the earlier one on the CSS cap', () => {
      setInnerHeight(1000)
      mountChrome({ navHeight: 64, approvalHeight: 80 })
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      const costWrap = screen.getByTestId('side-section-COST').querySelector('.table-wrap') as HTMLElement
      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      // 1000 - (64 nav + 80 approval bar + 0 measured margins/heading-row in
      // this bare jsdom DOM) = 856.
      expect(sgaWrap.style.maxHeight).toBe('856px')
      expect(costWrap.style.maxHeight).toBe('')
    })

    it('when only one section has rows, THAT section is treated as last and gets the computed max-height', () => {
      setInnerHeight(1000)
      mountChrome({ navHeight: 64, approvalHeight: 80 })
      render(<GridTable rows={onlyCostRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      expect(screen.queryByTestId('side-section-SGA')).not.toBeInTheDocument()
      const costWrap = screen.getByTestId('side-section-COST').querySelector('.table-wrap') as HTMLElement
      expect(costWrap.style.maxHeight).toBe('856px')
    })

    it('falls back to the CSS cap (no inline max-height) when the approval bar is not in the DOM', () => {
      // No mountChrome() — no `.nav`/approval-bar exist, matching an
      // isolated GridTable render or a page where no ฝ่าย is selected yet.
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)

      const costWrap = screen.getByTestId('side-section-COST').querySelector('.table-wrap') as HTMLElement
      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      expect(costWrap.style.maxHeight).toBe('')
      expect(sgaWrap.style.maxHeight).toBe('')
    })

    it('recomputes on window resize', () => {
      setInnerHeight(1000)
      mountChrome({ navHeight: 64, approvalHeight: 80 })
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      expect(sgaWrap.style.maxHeight).toBe('856px')

      setInnerHeight(700)
      fireEvent(window, new Event('resize'))
      // 700 - 144 (same 64+80 reserve) = 556.
      expect(sgaWrap.style.maxHeight).toBe('556px')
    })

    it('fullscreen mode omits the .nav height from the reserve (the overlay paints over nav at inset:0)', () => {
      setInnerHeight(1000)
      mountChrome({ navHeight: 64, approvalHeight: 80 })
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} isFullscreen onToggleFullscreen={vi.fn()} />)

      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      // 1000 - (0 nav, skipped in fullscreen + 80 approval bar) = 920.
      expect(sgaWrap.style.maxHeight).toBe('920px')
    })

    it('reads .budget-grid margin-bottom into the reserve in normal mode (GATE FIX1) — padding-bottom is ignored here', () => {
      setInnerHeight(1000)
      mountChrome({ navHeight: 64, approvalHeight: 80, budgetGridMarginBottom: 60, budgetGridPaddingBottom: 28 })
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      // 1000 - (64 nav + 80 approval bar + 60 .budget-grid margin-bottom) =
      // 796. Before GATE FIX1 this term was omitted entirely (would have
      // read 856px, ~60px too tall).
      expect(sgaWrap.style.maxHeight).toBe('796px')
    })

    it('swaps to .budget-grid padding-bottom in fullscreen mode (GATE FIX1) — margin-bottom is ignored there', () => {
      setInnerHeight(1000)
      mountChrome({ navHeight: 64, approvalHeight: 80, budgetGridMarginBottom: 60, budgetGridPaddingBottom: 28 })
      render(
        <GridTable
          rows={bothSidesRows}
          glRef={GL_REF}
          onCommitMonth={vi.fn()}
          isFullscreen
          onToggleFullscreen={vi.fn()}
        />,
      )
      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      // 1000 - (0 nav, skipped in fullscreen + 80 approval bar + 28
      // .budget-grid padding-bottom) = 892. Before GATE FIX1 this would
      // have read 920px, ~28px too tall.
      expect(sgaWrap.style.maxHeight).toBe('892px')
    })

    it('finds the approval bar by its real .approval-bar class with no data-testid at all (GATE FIX3) — a testid rename can never silently drop back to the CSS cap', () => {
      setInnerHeight(1000)
      const budgetGrid = document.createElement('div')
      budgetGrid.className = 'budget-grid'
      document.body.appendChild(budgetGrid)
      const nav = document.createElement('div')
      nav.className = 'nav'
      stubHeight(nav, 64)
      document.body.appendChild(nav)
      const approvalBar = document.createElement('div')
      approvalBar.className = 'approval-bar' // deliberately no data-testid
      stubHeight(approvalBar, 80)
      budgetGrid.appendChild(approvalBar)

      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      // Same 856px as the testid-carrying mountChrome tests — proves the
      // class selector alone is sufficient, the testid is not load-bearing.
      expect(sgaWrap.style.maxHeight).toBe('856px')
    })

    it('falls back cleanly (no inline max-height) when reserved > 0 but the viewport is shorter than the reserve', () => {
      setInnerHeight(100)
      mountChrome({ navHeight: 64, approvalHeight: 80 })
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      // reserved = 144 > 0, available = 100 - 144 = -44 <= 0 — must fall
      // back to the CSS cap, never set a negative/zero max-height.
      expect(sgaWrap.style.maxHeight).toBe('')
    })

    it('recomputes when the ResizeObserver reports the approval bar changed size (test gap L5)', () => {
      setInnerHeight(1000)
      const { approvalBar } = mountChrome({ navHeight: 64, approvalHeight: 80 })
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      expect(sgaWrap.style.maxHeight).toBe('856px')

      const ro = FakeResizeObserver.instances.at(-1)
      expect(ro).toBeDefined()

      // The approval bar grows (e.g. the reject panel opens) — re-stub its
      // height, then fire the observer callback the same way a real
      // ResizeObserver would when it detects the change. `act()` is
      // required here: unlike `fireEvent`, a raw manual call is not
      // dispatched through React's own event handling, so the resulting
      // `setState` is otherwise left batched/unflushed at assertion time
      // (React 18 automatic batching outside act/fireEvent).
      stubHeight(approvalBar, 140)
      act(() => {
        ro!.trigger()
      })

      // 1000 - (64 nav + 140 approval bar) = 796.
      expect(sgaWrap.style.maxHeight).toBe('796px')
    })

    it('recomputes when the approval bar mounts or unmounts later (MutationObserver, direct-child only — GATE FIX2)', async () => {
      setInnerHeight(1000)
      const budgetGrid = document.createElement('div')
      budgetGrid.className = 'budget-grid'
      document.body.appendChild(budgetGrid)
      const nav = document.createElement('div')
      nav.className = 'nav'
      stubHeight(nav, 64)
      document.body.appendChild(nav)

      // No approval bar yet — mirrors "no ฝ่าย selected" before it mounts.
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      expect(sgaWrap.style.maxHeight).toBe('')

      const approvalBar = document.createElement('div')
      approvalBar.className = 'approval-bar'
      stubHeight(approvalBar, 80)
      budgetGrid.appendChild(approvalBar) // direct-child add of .budget-grid

      await waitFor(() => expect(sgaWrap.style.maxHeight).toBe('856px'))

      budgetGrid.removeChild(approvalBar) // direct-child remove

      await waitFor(() => expect(sgaWrap.style.maxHeight).toBe(''))
    })

    it('ignores a mutation nested inside the approval bar itself (GATE FIX2 — subtree:false, no longer a forced reflow on every table edit)', async () => {
      setInnerHeight(1000)
      const { approvalBar, approvalSpy } = mountChrome({ navHeight: 64, approvalHeight: 80 })
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const sgaWrap = screen.getByTestId('side-section-SGA').querySelector('.table-wrap') as HTMLElement
      expect(sgaWrap.style.maxHeight).toBe('856px')
      const callsBeforeMutation = approvalSpy.mock.calls.length

      // A mutation NESTED inside the approval bar (standing in for typing
      // in a column filter, or a per-row save message appearing, deep
      // inside `.budget-grid`) is not a direct-child mutation of
      // `.budget-grid` itself and must NOT trigger a recompute.
      const note = document.createElement('span')
      note.textContent = 'typing in a column filter'
      approvalBar.appendChild(note)

      await new Promise((resolve) => setTimeout(resolve, 0))
      expect(approvalSpy.mock.calls.length).toBe(callsBeforeMutation)
    })

    it('removes the resize listener, ResizeObserver, and MutationObserver on unmount (test gap L5)', () => {
      setInnerHeight(1000)
      mountChrome({ navHeight: 64, approvalHeight: 80 })
      const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener')
      const mutationDisconnectSpy = vi.spyOn(MutationObserver.prototype, 'disconnect')

      const { unmount } = render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const ro = FakeResizeObserver.instances.at(-1)
      expect(ro).toBeDefined()

      unmount()

      expect(removeEventListenerSpy).toHaveBeenCalledWith('resize', expect.any(Function))
      expect(mutationDisconnectSpy).toHaveBeenCalled()
      expect(ro!.disconnect).toHaveBeenCalled()
    })
  })

  describe('ADR-0026 hidden SAP months', () => {
    const HIDDEN_TOOLTIP = 'ข้อมูล SAP เดือนนี้ยังไม่ครบ จึงยังไม่แสดง'
    const janToMarRow = makeRow({
      cost_center: 'CC1', gl_account: '5211800030', editable: true,
      sap: sapLayer({
        m01: 157832827, m02: 153166038, m03: 129700892,
        m04: null, m05: null, m06: null, m07: null, m08: null, m09: null, m10: null, m11: null, m12: null,
      }),
      board: { ...blankLayer({ m04: 4000, total_year: 4000 }), gl_name: null, gl_group: null, c_level: null, division: null, department: null } as BudgetRow['board'],
      pending: { ...blankLayer({ m04: 7000, total_year: 7000 }), template: null, remark: null, gl_name: null, gl_group: null, c_level: null, division: null, department: null, updated_at: null } as BudgetRow['pending'],
    })

    it('renders a hidden SAP month as a muted en-dash with a Thai explanation, not a number', () => {
      render(<GridTable rows={[janToMarRow]} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const cell = screen.getByTestId('sap-value-CC1-5211800030-m04')
      const pill = cell.querySelector('.month-value') as HTMLElement
      expect(pill).toHaveTextContent('–')
      expect(pill.className).toContain('month-hidden')
      expect(pill).toHaveAttribute('title', HIDDEN_TOOLTIP)
    })

    it('keeps the complete months showing their real numbers', () => {
      render(<GridTable rows={[janToMarRow]} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      expect(screen.getByTestId('sap-value-CC1-5211800030-m03')).toHaveTextContent('129,700,892')
    })

    it('never touches the Approved or Pending cell of the same month', () => {
      render(<GridTable rows={[janToMarRow]} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      expect(screen.getByTestId('board-value-CC1-5211800030-m04')).toHaveTextContent('4,000')
      expect(screen.getByTestId('pending-input-CC1-5211800030-m04')).toHaveValue('7000')
    })

    it('labels the SAP grand total with the months it covers', () => {
      render(<GridTable rows={[janToMarRow]} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      expect(screen.getByTestId('side-section-COST')).toHaveTextContent('รวมทั้งหมด · SAP · ใช้จริง (Jan–Mar)')
    })

    it('keeps the SAP grand total unlabelled when every month is shown', () => {
      const allVisible = makeRow({ cost_center: 'CC1', gl_account: '5211800030', editable: true, sap: sapLayer({ m01: 100 }) })
      render(<GridTable rows={[allVisible]} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const section = screen.getByTestId('side-section-COST')
      expect(section).toHaveTextContent('รวมทั้งหมด · SAP · ใช้จริง')
      expect(section).not.toHaveTextContent('(Jan–')
    })

    it('explains on the row year-total that it covers the complete months only', () => {
      render(<GridTable rows={[janToMarRow]} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const yearCell = screen.getByTestId('sap-value-CC1-5211800030-year')
      expect(yearCell.querySelector('.month-value')).toHaveAttribute('title', 'รวมเฉพาะเดือนที่ข้อมูลครบ: Jan–Mar')
    })
  })
})
