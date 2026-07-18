import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { BudgetRow, GlAccount } from '../api/types'
import { COLUMN_WIDTH_MIN, COLUMN_WIDTHS_STORAGE_KEY } from './model'
import { GridTable } from './GridTable'
import { blankLayer, makeRow } from './testUtils'

const GL_REF: GlAccount[] = [
  { gl_code: '5211800030', gl_group: 'Office expenses', gl_name: 'Office COST', is_special: false },
  { gl_code: '6211800030', gl_group: 'Office expenses', gl_name: 'Office SGA', is_special: false },
  { gl_code: '5211900030', gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true },
]

function getTable(testId: string): HTMLTableElement {
  return screen.getByTestId(testId).querySelector('table.data-table') as HTMLTableElement
}

function getIdentityThs(table: HTMLTableElement): HTMLTableCellElement[] {
  const colRow = table.querySelector('thead tr.col-row') as HTMLTableRowElement
  return [...colRow.querySelectorAll('th.frz')] as HTMLTableCellElement[]
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

    it('renders a col-filter-spacer under the Status th and every month th', () => {
      render(<GridTable rows={filterRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const table = screen.getByTestId('side-section-COST').querySelector('table.data-table') as HTMLTableElement
      const colRow = table.querySelector('thead tr.col-row') as HTMLTableRowElement
      const ths = [...colRow.querySelectorAll('th')]
      const statusTh = ths.find((th) => th.querySelector('.th-label')?.textContent === 'Status')
      expect(statusTh?.querySelector('.col-filter-spacer')).toBeInTheDocument()
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
      const [costCc, costGl] = getIdentityThs(costTable)
      const [sgaCc, sgaGl] = getIdentityThs(sgaTable)

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
    })

    it('a saved localStorage width WINS over the fit-to-content default on mount (does not get auto-overwritten)', () => {
      window.localStorage.setItem(COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify({ cc: 222, gl: 111, glGroup: 99 }))
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const costCc = getIdentityThs(getTable('side-section-COST'))[0]
      expect(costCc.style.width).toBe('222px')
    })

    it('a manual drag override is NOT clobbered by a later data change (rows prop changes)', () => {
      const { rerender } = render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const handle = screen.getAllByTestId('col-resize-cc')[0]
      fireEvent.mouseDown(handle, { clientX: 0 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: 275, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: 275, bubbles: true }))
      const draggedWidth = getIdentityThs(getTable('side-section-COST'))[0].style.width

      // A brand-new rows array (new reference, as a real refetch would
      // produce) must NOT trigger a re-measure that overwrites the user's
      // explicit choice.
      const newRows = [makeRow({ cost_center: 'CC-DIFFERENT', gl_account: '5211800030', editable: true })]
      rerender(<GridTable rows={newRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      expect(getIdentityThs(getTable('side-section-COST'))[0].style.width).toBe(draggedWidth)
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

    it('renders a drag handle on each of the 3 identity columns, in both side-tables', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      expect(screen.getAllByTestId('col-resize-cc')).toHaveLength(2) // COST + SGA tables
      expect(screen.getAllByTestId('col-resize-gl')).toHaveLength(2)
      expect(screen.getAllByTestId('col-resize-glgroup')).toHaveLength(2)
    })

    it('dragging the Cost Center handle widens the column, updates --frz2/--frz3, and keeps both tables aligned', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const handle = screen.getAllByTestId('col-resize-cc')[0]
      // Read the fit-to-content STARTING width dynamically (point 8d made
      // this a measured default, not a hardcoded 130) — the drag delta is
      // what this test actually cares about.
      const startCc = parseInt(getIdentityThs(getTable('side-section-COST'))[0].style.width, 10)
      const startGl = parseInt(getIdentityThs(getTable('side-section-COST'))[1].style.width, 10)

      fireEvent.mouseDown(handle, { clientX: 100 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: 150, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: 150, bubbles: true }))

      const costTable = getTable('side-section-COST')
      const sgaTable = getTable('side-section-SGA')
      const costCcTh = getIdentityThs(costTable)[0]
      const sgaCcTh = getIdentityThs(sgaTable)[0]

      expect(costCcTh.style.width).toBe(`${startCc + 50}px`) // +50px drag
      expect(sgaCcTh.style.width).toBe(`${startCc + 50}px`) // shared state — both tables stay aligned
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
      expect(getIdentityThs(getTable('side-section-COST'))[0].style.width).toBe('800px')

      fireEvent.mouseDown(handle, { clientX: 0 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: -5000, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: -5000, bubbles: true }))
      expect(getIdentityThs(getTable('side-section-COST'))[0].style.width).toBe('60px')
    })

    it('"Reset columns" re-measures fit-to-content (NOT a hardcoded 130/150/150), incl. --frz2 tracking it, and clears the localStorage override', () => {
      render(<GridTable rows={bothSidesRows} glRef={GL_REF} onCommitMonth={vi.fn()} />)
      const handle = screen.getAllByTestId('col-resize-cc')[0]
      const startCc = parseInt(getIdentityThs(getTable('side-section-COST'))[0].style.width, 10)
      fireEvent.mouseDown(handle, { clientX: 0 })
      fireEvent(window, new MouseEvent('mousemove', { clientX: 300, bubbles: true }))
      fireEvent(window, new MouseEvent('mouseup', { clientX: 300, bubbles: true }))
      expect(getIdentityThs(getTable('side-section-COST'))[0].style.width).toBe(`${startCc + 300}px`)
      expect(window.localStorage.getItem(COLUMN_WIDTHS_STORAGE_KEY)).not.toBeNull() // drag persisted an override

      fireEvent.click(screen.getByTestId('reset-columns-btn'))

      const costTable = getTable('side-section-COST')
      // Re-measured fit-to-content — in jsdom (no real text layout) that is
      // deterministically the padding-only floor, i.e. COLUMN_WIDTH_MIN; a
      // real browser (Playwright verify) gets the true content-fitted value.
      expect(getIdentityThs(costTable)[0].style.width).toBe(`${startCc}px`)
      expect(costTable.style.getPropertyValue('--frz2')).toBe(`${startCc}px`)
      expect(window.localStorage.getItem(COLUMN_WIDTHS_STORAGE_KEY)).toBeNull() // override cleared, not re-saved
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
})
