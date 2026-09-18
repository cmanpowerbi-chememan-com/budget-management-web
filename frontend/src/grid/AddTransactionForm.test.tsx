import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { BudgetRow, DepartmentRow, GlAccount } from '../api/types'
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

/** The Cost Center picker is the SAME searchable-combobox pattern as GL Code
 * (see the module doc comment) — focus opens the list, click picks. */
function openCcList() {
  fireEvent.focus(screen.getByLabelText('Cost Center'))
}

function pickCcOption(name: string | RegExp) {
  openCcList()
  fireEvent.click(screen.getByRole('option', { name }))
}

describe('AddTransactionForm', () => {
  it('opens the Cost Center combobox listing every option in the Fill scope', () => {
    render(
      <AddTransactionForm
        fillCostCenters={['CC1', 'CC2']}
        glRef={GL_REF}
        existingRows={[]}
        onAdd={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    openCcList()
    expect(screen.getByRole('option', { name: 'CC1' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'CC2' })).toBeInTheDocument()
  })

  it('typing filters Cost Center options by substring; no match shows an empty hint', () => {
    render(
      <AddTransactionForm
        fillCostCenters={['CC1', 'CC2', '10IT011300']}
        glRef={GL_REF}
        existingRows={[]}
        onAdd={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    const ccInput = screen.getByLabelText('Cost Center')

    openCcList()
    fireEvent.change(ccInput, { target: { value: 'it01' } })
    expect(screen.getByRole('option', { name: '10IT011300' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'CC1' })).not.toBeInTheDocument()

    fireEvent.change(ccInput, { target: { value: 'zzz' } })
    // Only one combobox list is open at a time — safe to query the lone listbox.
    expect(within(screen.getByRole('listbox')).queryByRole('option')).not.toBeInTheDocument()
    expect(screen.getByText('ไม่พบ Cost Center ที่ค้นหา')).toBeInTheDocument()
  })

  it('Enter picks the first filtered Cost Center match; free text alone never selects a CC', () => {
    render(<AddTransactionForm fillCostCenters={['CC1', 'CC2']} glRef={GL_REF} existingRows={[]} onAdd={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    const ccInput = screen.getByLabelText('Cost Center') as HTMLInputElement

    openCcList()
    fireEvent.change(ccInput, { target: { value: 'CC2' } })
    fireEvent.keyDown(ccInput, { key: 'Enter' })

    expect(ccInput.value).toBe('CC2')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument() // list closed after pick
  })

  it('includes special-GL accounts in the GL picker (Spec B path ข, jakkaritw 2026-08-05 — no longer excluded)', () => {
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    openGlList()
    expect(screen.getByRole('option', { name: /5211800030/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /5211900030/ })).toBeInTheDocument()
  })

  it('a picked special-GL code is no longer rejected — onAdd is called (it will route into its own subform on save)', async () => {
    const onAdd = vi.fn().mockResolvedValue({ ok: true })
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    pickCcOption('CC1')
    pickGlOption(/5211900030/)
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(onAdd).toHaveBeenCalledWith('CC1', '5211900030'))
    expect(screen.queryByText(/เป็นกลุ่มพิเศษ/)).not.toBeInTheDocument()
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
    pickCcOption('CC1')
    pickGlOption(/5211800030/)
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))
    expect(screen.getByText('รายการนี้มีอยู่ในตารางแล้ว')).toBeInTheDocument()
    expect(onAdd).not.toHaveBeenCalled()
  })

  it('calls onAdd with the chosen (CC, GL) when valid, and closes the form on success', async () => {
    const onAdd = vi.fn().mockResolvedValue({ ok: true })
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    pickCcOption('CC1')
    pickGlOption(/5211800030/)
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(onAdd).toHaveBeenCalledWith('CC1', '5211800030'))
    await waitFor(() => expect(screen.queryByLabelText('Cost Center')).not.toBeInTheDocument())
  })

  it('shows the server error and keeps the form open when onAdd resolves not-ok', async () => {
    const onAdd = vi.fn().mockResolvedValue({ ok: false, errorTh: 'สร้างรายการไม่สำเร็จ' })
    render(<AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    pickCcOption('CC1')
    pickGlOption(/5211800030/)
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(screen.getByText('สร้างรายการไม่สำเร็จ')).toBeInTheDocument())
    expect(screen.getByLabelText('Cost Center')).toBeInTheDocument()
  })

  // "+ เพิ่ม Transaction" lock-awareness (2026-08-08 bug fix, REDESIGNED
  // 2026-09-17 issue #13 decision 1: the form is now scoped to ONE ฝ่าย at a
  // time — a single `departmentLocked` boolean replaces the old
  // per-Cost-Center `lockedCostCenters` map). jakkaritw's decision: keep the
  // control VISIBLE but non-actionable, reason on screen — never hide it
  // silently, same tone as the locked subform button.
  describe('department-lock awareness (ADR-0013 UI parity)', () => {
    it('ฝ่ายเปิด (departmentLocked=false) — unchanged: the button works and add still succeeds', async () => {
      const onAdd = vi.fn().mockResolvedValue({ ok: true })
      render(
        <AddTransactionForm
          fillCostCenters={['CC1']}
          glRef={GL_REF}
          existingRows={[]}
          onAdd={onAdd}
          selectedDepartment="Accounting"
        />,
      )
      const trigger = screen.getByRole('button', { name: /เพิ่ม transaction/i })
      expect(trigger).not.toBeDisabled()
      fireEvent.click(trigger)
      pickCcOption('CC1')
      pickGlOption(/5211800030/)
      fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

      await waitFor(() => expect(onAdd).toHaveBeenCalledWith('CC1', '5211800030'))
    })

    it('the ฝ่าย on screen is locked — the "+ เพิ่ม Transaction" button is visible but disabled, naming the ฝ่าย in the Thai reason', () => {
      render(
        <AddTransactionForm
          fillCostCenters={['CC1']}
          glRef={GL_REF}
          existingRows={[]}
          onAdd={vi.fn()}
          selectedDepartment="Accounting"
          departmentLocked
        />,
      )
      const trigger = screen.getByRole('button', { name: /เพิ่ม transaction/i })
      expect(trigger).toBeInTheDocument() // visible, not hidden
      expect(trigger).toBeDisabled() // not actionable
      expect(screen.getByText(/Accounting/)).toBeInTheDocument()
      expect(screen.getByText(/อยู่ระหว่างอนุมัติหรืออนุมัติแล้ว/)).toBeInTheDocument()
    })

    it('a picked Cost Center outside the selected ฝ่าย is rejected (defense-in-depth), onAdd never called', () => {
      const onAdd = vi.fn()
      const departments: DepartmentRow[] = [
        { cost_center: 'CC1', department: 'Accounting', division: null, c_level: null },
        { cost_center: 'CC2', department: 'IT', division: null, c_level: null },
      ]
      render(
        <AddTransactionForm
          fillCostCenters={['CC1', 'CC2']}
          glRef={GL_REF}
          existingRows={[]}
          onAdd={onAdd}
          selectedDepartment="Accounting"
          departments={departments}
        />,
      )
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      pickCcOption('CC2')
      pickGlOption(/5211800030/)
      fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

      expect(screen.getByText(/ไม่ได้อยู่ในฝ่าย/)).toBeInTheDocument()
      expect(onAdd).not.toHaveBeenCalled()
    })

    it('no ฝ่าย selected (departmentUnknown) — the button is disabled with a distinct "ยังไม่ทราบฝ่าย" reason', () => {
      render(
        <AddTransactionForm
          fillCostCenters={[]}
          glRef={GL_REF}
          existingRows={[]}
          onAdd={vi.fn()}
          departmentUnknown
        />,
      )
      const trigger = screen.getByRole('button', { name: /เพิ่ม transaction/i })
      expect(trigger).toBeDisabled()
      expect(screen.getByText(/ยังไม่ทราบฝ่าย/)).toBeInTheDocument()
    })

    it('the lock-status fetch failed (lockStatusUnavailable) — the button is disabled with its own reason, never falls open', () => {
      render(
        <AddTransactionForm
          fillCostCenters={['CC1']}
          glRef={GL_REF}
          existingRows={[]}
          onAdd={vi.fn()}
          selectedDepartment="Accounting"
          lockStatusUnavailable
        />,
      )
      const trigger = screen.getByRole('button', { name: /เพิ่ม transaction/i })
      expect(trigger).toBeDisabled()
      expect(screen.getByText(/ไม่สามารถตรวจสอบสถานะฝ่าย/)).toBeInTheDocument()
    })
  })

  // 2026-08-08 3-state extension: a YEAR-wide lock (every department, not
  // just the one on screen) — distinct from the per-department
  // departmentLocked above.
  describe('year-not-open awareness (2026-08-08 3-state extension)', () => {
    it('yearNotOpen — the button is visible but disabled, with the year-wide Thai reason on screen, even though no Cost Center is individually locked', () => {
      render(
        <AddTransactionForm
          fillCostCenters={['CC1']}
          glRef={GL_REF}
          existingRows={[]}
          onAdd={vi.fn()}
          yearNotOpen
        />,
      )
      const trigger = screen.getByRole('button', { name: /เพิ่ม transaction/i })
      expect(trigger).toBeInTheDocument() // visible, not hidden
      expect(trigger).toBeDisabled() // not actionable
      expect(screen.getByText(/ไม่เปิดให้กรอกในเว็บ/)).toBeInTheDocument()
    })

    it('yearNotOpen takes precedence over the per-department reason when both happen to be true', () => {
      render(
        <AddTransactionForm
          fillCostCenters={['CC1']}
          glRef={GL_REF}
          existingRows={[]}
          onAdd={vi.fn()}
          selectedDepartment="Accounting"
          departmentLocked
          yearNotOpen
        />,
      )
      expect(screen.getByRole('button', { name: /เพิ่ม transaction/i })).toBeDisabled()
      expect(screen.getByText(/ไม่เปิดให้กรอกในเว็บ/)).toBeInTheDocument()
      expect(screen.queryByText(/อยู่ระหว่างอนุมัติหรืออนุมัติแล้ว/)).not.toBeInTheDocument()
    })

    it('yearNotOpen is optional — omitting it entirely behaves like "the year is open" (unchanged)', async () => {
      const onAdd = vi.fn().mockResolvedValue({ ok: true })
      render(
        <AddTransactionForm fillCostCenters={['CC1']} glRef={GL_REF} existingRows={[]} onAdd={onAdd} />,
      )
      const trigger = screen.getByRole('button', { name: /เพิ่ม transaction/i })
      expect(trigger).not.toBeDisabled()
      fireEvent.click(trigger)
      pickCcOption('CC1')
      pickGlOption(/5211800030/)
      fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

      await waitFor(() => expect(onAdd).toHaveBeenCalledWith('CC1', '5211800030'))
    })
  })

  // GL 6210100150 is budgeted only by 10OS010000 and 10HR012000 (jakkaritw
  // 2026-09-17/18 — supersedes the department-keyed rule shipped 2026-08-29).
  // The rule lives in the PICKER: existing rows and every total stay
  // untouched, so a cost center that already carries seminar money keeps it.
  describe('cost-center-restricted GLs (GL 6210100150)', () => {
    const SEMINAR_GL_REF: GlAccount[] = [
      ...GL_REF,
      { gl_code: '6210100150', gl_group: 'Training & Seminar', gl_name: 'ค่าอบรมและสัมมนา - ค่าธรรมเนียม', is_special: true, edit_by: 'user' },
    ]
    const FILL_CCS = ['10OS010000', '10HR012000', '10HR011000', '10AC012000']

    function renderForm(props: Partial<ComponentProps<typeof AddTransactionForm>> = {}) {
      return render(
        <AddTransactionForm
          fillCostCenters={FILL_CCS}
          glRef={SEMINAR_GL_REF}
          existingRows={[]}
          onAdd={vi.fn().mockResolvedValue({ ok: true })}
          {...props}
        />,
      )
    }

    it('a filler on 10OS010000 sees the GL — the cost center that gained it', () => {
      renderForm()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      pickCcOption('10OS010000')
      openGlList()
      expect(screen.getByRole('option', { name: /6210100150/ })).toBeInTheDocument()
    })

    it('a filler on 10HR012000 still sees the GL — unchanged from before', () => {
      renderForm()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      pickCcOption('10HR012000')
      openGlList()
      expect(screen.getByRole('option', { name: /6210100150/ })).toBeInTheDocument()
    })

    it('a filler on 10HR011000 no longer sees the GL, but every other GL is still there', () => {
      renderForm()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      pickCcOption('10HR011000')
      openGlList()
      expect(screen.queryByRole('option', { name: /6210100150/ })).not.toBeInTheDocument()
      expect(screen.getByRole('option', { name: /5211800030/ })).toBeInTheDocument()
    })

    it('a filler on any other cost center does not see the GL', () => {
      renderForm()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      pickCcOption('10AC012000')
      openGlList()
      expect(screen.queryByRole('option', { name: /6210100150/ })).not.toBeInTheDocument()
    })

    it('searching cannot type the hidden GL back into view', () => {
      renderForm()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      pickCcOption('10HR011000')
      openGlList()
      fireEvent.change(screen.getByLabelText('GL Code'), { target: { value: 'seminar' } })
      expect(within(screen.getByRole('listbox')).queryByRole('option')).not.toBeInTheDocument()
      expect(screen.getByText('ไม่พบ GL Code ที่ค้นหา')).toBeInTheDocument()
    })

    it('an admin sees the GL on 10HR011000', () => {
      renderForm({ isAdmin: true })
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      pickCcOption('10HR011000')
      openGlList()
      expect(screen.getByRole('option', { name: /6210100150/ })).toBeInTheDocument()
    })

    it('no cost center picked yet — the GL is hidden, so it can never appear and then vanish', () => {
      renderForm()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      openGlList()
      expect(screen.queryByRole('option', { name: /6210100150/ })).not.toBeInTheDocument()
      expect(screen.getByRole('option', { name: /5211800030/ })).toBeInTheDocument()
    })

    it('switching the cost center from 10HR012000 to 10HR011000 clears an already-picked GL', () => {
      const onAdd = vi.fn().mockResolvedValue({ ok: true })
      renderForm({ onAdd })
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      pickCcOption('10HR012000')
      pickGlOption(/6210100150/)
      expect((screen.getByLabelText('GL Code') as HTMLInputElement).value).toContain('6210100150')

      pickCcOption('10HR011000')
      expect((screen.getByLabelText('GL Code') as HTMLInputElement).value).toBe('')

      fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))
      expect(screen.getByText('กรุณาเลือก GL Code')).toBeInTheDocument()
      expect(onAdd).not.toHaveBeenCalled()
    })

    it('switching between the two eligible cost centers keeps the picked GL', () => {
      renderForm()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      pickCcOption('10OS010000')
      pickGlOption(/6210100150/)
      pickCcOption('10HR012000')
      expect((screen.getByLabelText('GL Code') as HTMLInputElement).value).toContain('6210100150')
    })

    it('switching between two cost centers keeps a picked non-restricted GL', () => {
      renderForm()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      pickCcOption('10HR012000')
      pickGlOption(/5211800030/)
      pickCcOption('10AC012000')
      expect((screen.getByLabelText('GL Code') as HTMLInputElement).value).toContain('5211800030')
    })
  })
})
