import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { BudgetRow, GlAccount } from '../api/types'
import { AddTransactionForm } from './AddTransactionForm'
import { makeRow } from './testUtils'

const GL_REF: GlAccount[] = [
  { gl_code: '5211800030', gl_group: 'Office expenses', gl_name: 'Office COST', is_special: false },
  { gl_code: '5211900030', gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true },
]

function makeExistingRow(cc: string, gl: string): BudgetRow {
  return makeRow({ cost_center: cc, gl_account: gl, editable: true })
}

/** The GL picker is a searchable combobox — focusing the input opens the
 * option list; clicking an option is what selects the GL (free text alone
 * never counts as a selection). */
function openGlList() {
  fireEvent.focus(screen.getByLabelText('GL Code'))
}

function pickGlOption(name: string | RegExp) {
  openGlList()
  fireEvent.click(screen.getByRole('option', { name }))
}

describe('AddTransactionForm', () => {
  it('renders a Cost Center select limited to the Fill scope', () => {
    render(
      <AddTransactionForm
        fillCostCenters={['CC1', 'CC2']}
        glRef={GL_REF}
        existingRows={[]}
        onAdd={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    const ccSelect = screen.getByLabelText('Cost Center')
    expect(ccSelect).toHaveTextContent('CC1')
    expect(ccSelect).toHaveTextContent('CC2')
  })

  it('excludes special-GL accounts from the GL picker options', () => {
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    openGlList()
    expect(screen.getByRole('option', { name: /5211800030/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /5211900030/ })).not.toBeInTheDocument()
  })

  it('marks an admin-only GL with a badge in the picker label (GL edit_by lock, design v2)', () => {
    const glRefWithAdminGl: GlAccount[] = [
      ...GL_REF,
      { gl_code: '5210100010', gl_group: 'Insurance Premium', gl_name: 'Ins Premium', is_special: false, edit_by: 'admin' },
    ]
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={glRefWithAdminGl} existingRows={[]} onAdd={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    openGlList()
    expect(screen.getByRole('option', { name: '5210100010 — Ins Premium (เฉพาะแอดมิน)' })).toBeInTheDocument()
    // a normal GL (edit_by absent, or 'user') never gets the badge
    expect(screen.queryByRole('option', { name: /5211800030 — Office COST \(เฉพาะแอดมิน\)/ })).not.toBeInTheDocument()
  })

  it('typing filters the options by code or name; no match shows an empty hint', () => {
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    const glInput = screen.getByLabelText('GL Code')

    openGlList()
    fireEvent.change(glInput, { target: { value: 'office' } })
    expect(screen.getByRole('option', { name: /5211800030/ })).toBeInTheDocument()

    fireEvent.change(glInput, { target: { value: 'zzz' } })
    // CC <select> also has native "option" roles — scope to the GL listbox.
    expect(within(screen.getByRole('listbox')).queryByRole('option')).not.toBeInTheDocument()
    expect(screen.getByText('ไม่พบ GL Code ที่ค้นหา')).toBeInTheDocument()
  })

  it('Enter picks the first filtered match; free text alone never selects a GL', () => {
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    const glInput = screen.getByLabelText('GL Code') as HTMLInputElement

    openGlList()
    fireEvent.change(glInput, { target: { value: 'office' } })
    fireEvent.keyDown(glInput, { key: 'Enter' })

    expect(glInput.value).toBe('5211800030 — Office COST')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument() // list closed after pick
  })

  it('shows a validation error and does not call onAdd for a duplicate (CC, GL) row', () => {
    const onAdd = vi.fn()
    render(
      <AddTransactionForm
        fillCostCenters={['CC1']}
        glRef={GL_REF}
        existingRows={[makeExistingRow('CC1', '5211800030')]}
        onAdd={onAdd}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    fireEvent.change(screen.getByLabelText('Cost Center'), { target: { value: 'CC1' } })
    pickGlOption(/5211800030/)
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))
    expect(screen.getByText('รายการนี้มีอยู่ในตารางแล้ว')).toBeInTheDocument()
    expect(onAdd).not.toHaveBeenCalled()
  })

  it('calls onAdd with the chosen (CC, GL) when valid, and closes the form on success', async () => {
    const onAdd = vi.fn().mockResolvedValue({ ok: true })
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    fireEvent.change(screen.getByLabelText('Cost Center'), { target: { value: 'CC1' } })
    pickGlOption(/5211800030/)
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(onAdd).toHaveBeenCalledWith('CC1', '5211800030'))
    await waitFor(() => expect(screen.queryByLabelText('Cost Center')).not.toBeInTheDocument())
  })

  it('shows the server error and keeps the form open when onAdd resolves not-ok', async () => {
    const onAdd = vi.fn().mockResolvedValue({ ok: false, errorTh: 'สร้างรายการไม่สำเร็จ' })
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    fireEvent.change(screen.getByLabelText('Cost Center'), { target: { value: 'CC1' } })
    pickGlOption(/5211800030/)
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(screen.getByText('สร้างรายการไม่สำเร็จ')).toBeInTheDocument())
    expect(screen.getByLabelText('Cost Center')).toBeInTheDocument()
  })
})
