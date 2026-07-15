import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    const glSelect = screen.getByLabelText('GL Code')
    expect(glSelect).toHaveTextContent('5211800030')
    expect(glSelect).not.toHaveTextContent('5211900030')
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
    fireEvent.change(screen.getByLabelText('GL Code'), { target: { value: '5211800030' } })
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))
    expect(screen.getByText('รายการนี้มีอยู่ในตารางแล้ว')).toBeInTheDocument()
    expect(onAdd).not.toHaveBeenCalled()
  })

  it('calls onAdd with the chosen (CC, GL) when valid, and closes the form on success', async () => {
    const onAdd = vi.fn().mockResolvedValue({ ok: true })
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    fireEvent.change(screen.getByLabelText('Cost Center'), { target: { value: 'CC1' } })
    fireEvent.change(screen.getByLabelText('GL Code'), { target: { value: '5211800030' } })
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(onAdd).toHaveBeenCalledWith('CC1', '5211800030'))
    await waitFor(() => expect(screen.queryByLabelText('Cost Center')).not.toBeInTheDocument())
  })

  it('shows the server error and keeps the form open when onAdd resolves not-ok', async () => {
    const onAdd = vi.fn().mockResolvedValue({ ok: false, errorTh: 'สร้างรายการไม่สำเร็จ' })
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    fireEvent.change(screen.getByLabelText('Cost Center'), { target: { value: 'CC1' } })
    fireEvent.change(screen.getByLabelText('GL Code'), { target: { value: '5211800030' } })
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(screen.getByText('สร้างรายการไม่สำเร็จ')).toBeInTheDocument())
    expect(screen.getByLabelText('Cost Center')).toBeInTheDocument()
  })
})
