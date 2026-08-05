import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetRow } from '../api/types'
import type { ScopeState } from '../auth/useScope'
import { ApiError } from '../api/client'
import * as approvalApi from '../api/approval'
import * as budgetApi from '../api/budget'
import * as referenceApi from '../api/reference'
import * as subformApi from '../api/subform'
import { BudgetGrid, SCOPE_ACCESS_CONTACT_EMAIL, SCOPE_ACCESS_SOURCE_FILE } from './BudgetGrid'
import { blankLayer, makeRow as makeRowFromOverrides } from './testUtils'

vi.mock('../api/budget')
vi.mock('../api/subform')
vi.mock('../api/approval')
vi.mock('../api/reference')

function makeRow(cc: string, gl: string, overrides: Partial<BudgetRow> = {}): BudgetRow {
  return makeRowFromOverrides({ cost_center: cc, gl_account: gl, editable: true, ...overrides })
}

const SCOPE: ScopeState = {
  role: 'filler',
  isAdmin: false,
  fillCostCenters: ['CC1'],
  seeCostCenters: ['CC1'],
  email: 'user@chememan.com',
  loading: false,
  error: null,
}

const GL_REF = [
  { gl_code: '5211800030', gl_group: 'Office expenses', gl_name: 'Office COST', is_special: false },
]

const DEPARTMENTS = [
  { cost_center: 'CC1', department: 'Solution Delivery', division: 'Digital Technology Division', c_level: 'CTO' },
]

describe('BudgetGrid', () => {
  beforeEach(() => {
    // A10 รออนุมัติ badge — called unconditionally on every mount/year
    // change, so every test needs a default (most tests are not testing
    // the badge itself and just need this to resolve quietly).
    vi.mocked(approvalApi.fetchPendingForMe).mockResolvedValue({ departments: [] })
    // Trip Manager loads these reference masters whenever it opens — the two
    // trip tests here only need them to resolve quietly.
    vi.mocked(referenceApi.fetchTravelers).mockResolvedValue([])
    vi.mocked(referenceApi.fetchCountries).mockResolvedValue([])
  })

  afterEach(() => {
    vi.resetAllMocks()
    window.sessionStorage.clear() // admin-mode-toggle tests persist here (A10)
  })

  it('loads and renders all 3 layers for a fetched row', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([
      makeRow('CC1', '5211800030', { sap: blankLayer({ m01: 100 }), pending: { ...makeRow('x', 'y').pending, m01: 50, total_year: 50 } }),
    ])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    await waitFor(() => expect(screen.getByTestId('sap-value-CC1-5211800030-m01')).toHaveTextContent('100'))
    expect(screen.getByTestId('pending-cell-CC1-5211800030-m01')).toBeInTheDocument()
  })

  it('shows a loud Thai error state when the grid fetch fails (never a silent empty grid)', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockRejectedValue(new ApiError(502, 'เซิร์ฟเวอร์ขัดข้อง กรุณาลองใหม่อีกครั้ง'))

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('เซิร์ฟเวอร์ขัดข้อง'))
  })

  it('edits a Pending cell and saves with the correct payload including the lock token', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([
      makeRow('CC1', '5211800030', {
        pending: { ...makeRow('x', 'y').pending, m01: 100, total_year: 100, updated_at: '2026-01-01T00:00:00Z' },
      }),
    ])
    vi.mocked(budgetApi.saveRow).mockResolvedValue({
      cost_center: 'CC1', gl_account: '5211800030', fiscal_year: 2027,
      m01: 999, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
      total_year: 999, remark: null, template: 'USER', gl_name: null, gl_group: null, c_level: null, division: null, department: null,
      updated_at: '2026-01-02T00:00:00Z',
    })

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    const input = await screen.findByTestId('pending-input-CC1-5211800030-m01')
    fireEvent.change(input, { target: { value: '999' } })
    fireEvent.blur(input)

    await waitFor(() =>
      expect(budgetApi.saveRow).toHaveBeenCalledWith(
        expect.objectContaining({
          cost_center: 'CC1',
          gl_account: '5211800030',
          fiscal_year: 2027,
          m01: 999,
          expected_updated_at: '2026-01-01T00:00:00Z',
        }),
      ),
    )
  })

  it('on a 409 conflict, refetches the grid and shows a clear Thai message without overwriting silently', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    const freshRow = makeRow('CC1', '5211800030', {
      pending: { ...makeRow('x', 'y').pending, m01: 777, total_year: 777, updated_at: '2026-03-03T00:00:00Z' },
    })
    vi.mocked(budgetApi.fetchBudgetGrid)
      // 1st call: initial mount — gated on ฝ่าย resolution (deptResolved),
      // so this is the ONLY mount-time fetch even though DEPARTMENTS has
      // exactly 1 ฝ่าย (see the mount-fetch-count tests below).
      .mockResolvedValueOnce([
        makeRow('CC1', '5211800030', {
          pending: { ...makeRow('x', 'y').pending, m01: 100, total_year: 100, updated_at: '2026-01-01T00:00:00Z' },
        }),
      ])
      // 2nd call: the conflict-triggered refetch after the rejected save.
      .mockResolvedValueOnce([freshRow])
    vi.mocked(budgetApi.saveRow).mockRejectedValue(
      new ApiError(409, 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น กรุณาโหลดข้อมูลใหม่แล้วลองอีกครั้ง', 'changed by someone else'),
    )

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    const input = await screen.findByTestId('pending-input-CC1-5211800030-m01')
    fireEvent.change(input, { target: { value: '999' } })
    fireEvent.blur(input)

    await waitFor(() => expect(screen.getByText(/ถูกแก้ไขโดยผู้อื่น/)).toBeInTheDocument())
    await waitFor(() => expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(2))
    await waitFor(() =>
      expect(screen.getByTestId('pending-input-CC1-5211800030-m01')).toHaveValue('777'),
    )
  })

  it('on a non-conflict save failure (e.g. session-expiry), the typed value stays in the cell — only a 409 reverts it', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([
      makeRow('CC1', '5211800030', {
        pending: { ...makeRow('x', 'y').pending, m01: 100, total_year: 100, updated_at: '2026-01-01T00:00:00Z' },
      }),
    ])
    vi.mocked(budgetApi.saveRow).mockRejectedValue(
      new ApiError(0, 'หมดเวลาการเข้าใช้งาน (ระบบให้ล็อกอินได้ครั้งละ 14 ชั่วโมง) กรุณา login ใหม่อีกครั้ง'),
    )

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    const input = await screen.findByTestId('pending-input-CC1-5211800030-m01')
    fireEvent.change(input, { target: { value: '999' } })
    fireEvent.blur(input)

    await waitFor(() => expect(screen.getByText(/หมดเวลาการเข้าใช้งาน/)).toBeInTheDocument())
    // Never refetches on this error kind (unlike 409) — the optimistic
    // value is simply left in place, not reconciled against the server.
    expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('pending-input-CC1-5211800030-m01')).toHaveValue('999')
  })

  describe('grid trailing "ลบ" column — deleting a manually-added row', () => {
    beforeEach(() => {
      vi.spyOn(window, 'confirm').mockReturnValue(true)
    })
    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('confirms in Thai, calls deleteRow with the row lock token, and removes the row from the grid', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([
        makeRow('CC1', '5211800030', {
          pending: { ...makeRow('x', 'y').pending, updated_at: '2026-01-01T00:00:00Z' },
        }),
      ])
      vi.mocked(budgetApi.deleteRow).mockResolvedValue({ ok: true })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

      const deleteBtn = await screen.findByTestId('delete-row-CC1-5211800030')
      fireEvent.click(deleteBtn)

      expect(window.confirm).toHaveBeenCalled()
      await waitFor(() =>
        expect(budgetApi.deleteRow).toHaveBeenCalledWith({
          costCenter: 'CC1', glAccount: '5211800030', fiscalYear: 2027, expectedUpdatedAt: '2026-01-01T00:00:00Z',
        }),
      )
      await waitFor(() => expect(screen.queryByTestId('txn-CC1-5211800030')).not.toBeInTheDocument())
    })

    it('does nothing when the user cancels the confirm dialog (no API call, row stays)', async () => {
      vi.mocked(window.confirm).mockReturnValue(false)
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([
        makeRow('CC1', '5211800030', {
          pending: { ...makeRow('x', 'y').pending, updated_at: '2026-01-01T00:00:00Z' },
        }),
      ])

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

      const deleteBtn = await screen.findByTestId('delete-row-CC1-5211800030')
      fireEvent.click(deleteBtn)

      expect(budgetApi.deleteRow).not.toHaveBeenCalled()
      expect(screen.getByTestId('txn-CC1-5211800030')).toBeInTheDocument()
    })

    it('on a 409 conflict, refetches the grid instead of silently removing the row', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid)
        .mockResolvedValueOnce([
          makeRow('CC1', '5211800030', {
            pending: { ...makeRow('x', 'y').pending, updated_at: '2026-01-01T00:00:00Z' },
          }),
        ])
        .mockResolvedValueOnce([
          makeRow('CC1', '5211800030', {
            pending: { ...makeRow('x', 'y').pending, m01: 500, total_year: 500, updated_at: '2026-02-02T00:00:00Z' },
          }),
        ])
      vi.mocked(budgetApi.deleteRow).mockRejectedValue(
        new ApiError(409, 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น', 'changed by someone else'),
      )

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

      const deleteBtn = await screen.findByTestId('delete-row-CC1-5211800030')
      fireEvent.click(deleteBtn)

      await waitFor(() => expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(2))
      await waitFor(() => expect(screen.getByTestId('txn-CC1-5211800030')).toBeInTheDocument())
    })
  })

  describe('mount-time grid fetch (gated on ฝ่าย resolution — single fetch, no flicker)', () => {
    it('fetches the grid exactly once on mount for a single-ฝ่าย caller, already resolved to that ฝ่าย (no department=null flash)', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS) // 1 ฝ่าย: 'Solution Delivery'
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      await waitFor(() => expect(screen.getByRole('button', { name: 'Solution Delivery' })).toBeInTheDocument())
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1)
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledWith(expect.objectContaining({ department: 'Solution Delivery' }))
    })

    it('fetches the grid exactly once on mount for a >1-ฝ่าย caller, with the FIRST ฝ่าย force-selected (2026-07-21)', async () => {
      const MULTI_DEPARTMENTS = [
        { cost_center: 'CC1', department: 'Solution Delivery', division: 'Digital Technology Division', c_level: 'CTO' },
        { cost_center: 'CC3', department: 'Budgeting and Management Accounting', division: 'Budgeting and Cost Accounting Division', c_level: 'CFO' },
      ]
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(MULTI_DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      // Divisions sort alphabetically: 'Budgeting and Cost Accounting Division'
      // < 'Digital Technology Division' → first ฝ่าย wins as the forced default.
      await waitFor(() => expect(screen.getByRole('button', { name: 'Budgeting and Management Accounting' })).toBeInTheDocument())
      await waitFor(() => expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1))
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledWith(expect.objectContaining({ department: 'Budgeting and Management Accounting' }))
    })

    it('still loads the grid (department=null) when fetchDepartments fails — never stuck in loading forever', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockRejectedValue(new Error('network down'))
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      await waitFor(() => expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1))
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledWith(expect.objectContaining({ department: undefined }))
      await waitFor(() => expect(screen.queryByText('กำลังโหลดข้อมูลงบประมาณ…')).not.toBeInTheDocument())
    })
  })

  it('applies the deep-link department/year as the initial filter', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue({
      department: 'Solution Delivery', fiscal_year: 2029, status: 'DRAFT',
      submitter_empcode: null, submitter_email: null, submitted_at: null,
      approver1_empcode: null, approver1_actioned_at: null, approver2_actioned_at: null, approver3_actioned_at: null,
      reject_reason: null, rejected_by_empcode: null, updated_at: null,
      current_position: null, current_approver_empcode: null, can_act: false, notification_warning: null,
    })

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: 'Solution Delivery', year: 2029 }} />)

    await waitFor(() =>
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledWith(
        expect.objectContaining({ year: 2029, department: 'Solution Delivery' }),
      ),
    )
  })

  it('adds a new transaction end-to-end through the form', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
    vi.mocked(budgetApi.saveRow).mockResolvedValue({
      cost_center: 'CC1', gl_account: '5211800030', fiscal_year: 2027,
      m01: 0, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
      total_year: 0, remark: null, template: 'USER', gl_name: 'Office COST', gl_group: 'Office expenses', c_level: null, division: null, department: null,
      updated_at: '2026-01-01T00:00:00Z',
    })

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    await waitFor(() => expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    // Cost Center and GL Code are both searchable comboboxes — focus opens
    // the list, click picks.
    fireEvent.focus(screen.getByLabelText('Cost Center'))
    fireEvent.click(screen.getByRole('option', { name: 'CC1' }))
    fireEvent.focus(screen.getByLabelText('GL Code'))
    fireEvent.click(screen.getByRole('option', { name: /5211800030/ }))
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(screen.getByTestId('pending-cell-CC1-5211800030-m01')).toBeInTheDocument())
  })

  // Spec B path ข (jakkaritw, 2026-08-05): picking a special-GL code in
  // "+ เพิ่ม Transaction" must NOT go through /budget/rows — the backend
  // unconditionally refuses to create a special-GL header row that way
  // (`_save_one_pending_row`: SpecialGlDirectEditError). It routes straight
  // into that GL's own subform instead, exactly like clicking an existing
  // special-GL row's own open button; the subform's own save lazily creates
  // the pending_budget row on its first write.
  it('"+ เพิ่ม Transaction" on a special-GL code opens its subform directly, without calling /budget/rows', async () => {
    const SPECIAL_GL_REF = [
      { gl_code: '6211900030', gl_group: 'Entertainment', gl_name: 'Ent SGA', is_special: true },
    ]
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(SPECIAL_GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    await waitFor(() => expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    fireEvent.focus(screen.getByLabelText('Cost Center'))
    fireEvent.click(screen.getByRole('option', { name: 'CC1' }))
    fireEvent.focus(screen.getByLabelText('GL Code'))
    fireEvent.click(screen.getByRole('option', { name: /6211900030/ }))
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    expect(await screen.findByTestId('detail-subform')).toBeInTheDocument()
    expect(budgetApi.saveRow).not.toHaveBeenCalled()
  })

  it('"+ เพิ่ม Transaction" on a Travelling Expense GL opens Trip Manager directly, locked to that GL\'s side', async () => {
    const TRAVEL_GL_REF = [
      { gl_code: '6210400010', gl_group: 'Travelling Expense', gl_name: 'Per Diem SGA', is_special: true },
    ]
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(TRAVEL_GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    await waitFor(() => expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    fireEvent.focus(screen.getByLabelText('Cost Center'))
    fireEvent.click(screen.getByRole('option', { name: 'CC1' }))
    fireEvent.focus(screen.getByLabelText('GL Code'))
    fireEvent.click(screen.getByRole('option', { name: /6210400010/ }))
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    expect(await screen.findByTestId('trip-manager')).toBeInTheDocument()
    expect(screen.queryByTestId('detail-subform')).not.toBeInTheDocument()
    expect(budgetApi.saveRow).not.toHaveBeenCalled()
  })

  it('opens the A9 DetailSubform for a non-travel special-GL row and refetches the grid after a save', async () => {
    const SPECIAL_GL_REF = [
      { gl_code: '5211900030', gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true },
    ]
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(SPECIAL_GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '5211900030')])
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    const openBtn = await screen.findByTestId('open-subform-CC1-5211900030')
    fireEvent.click(openBtn)

    expect(await screen.findByTestId('detail-subform')).toBeInTheDocument()
    await waitFor(() => expect(subformApi.fetchDetailLines).toHaveBeenCalledWith('CC1', '5211900030', expect.any(Number)))
  })

  it('opens Trip Manager (not DetailSubform) for a Travelling Expense special-GL row', async () => {
    const TRAVEL_GL_REF = [
      { gl_code: '5210400010', gl_group: 'Travelling Expense', gl_name: 'Per Diem', is_special: true },
    ]
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(TRAVEL_GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '5210400010')])
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    const openBtn = await screen.findByTestId('open-subform-CC1-5210400010')
    fireEvent.click(openBtn)

    expect(await screen.findByTestId('trip-manager')).toBeInTheDocument()
    expect(screen.queryByTestId('detail-subform')).not.toBeInTheDocument()
  })

  // ADR-0013 read-only lock (UI parity port, 2026-08-05) — the single line
  // `const readOnly = !row.editable` in handleOpenSpecial is the whole
  // feature's wiring point and had zero coverage at this level; inverting it
  // to `row.editable` left every other test green (gate finding item 3).
  describe('ADR-0013 read-only lock wiring (handleOpenSpecial -> readOnly prop)', () => {
    it('opening DetailSubform from a LOCKED (editable:false) special row renders its read-only affordances', async () => {
      const SPECIAL_GL_REF = [
        { gl_code: '5211900030', gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true },
      ]
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(SPECIAL_GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '5211900030', { editable: false })])
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      fireEvent.click(await screen.findByTestId('open-subform-CC1-5211900030'))

      expect(await screen.findByTestId('detail-subform')).toBeInTheDocument()
      expect(screen.getByText(/อ่านอย่างเดียว \(แก้ไม่ได้\)/)).toBeInTheDocument()
      expect(screen.queryByTestId('save-all')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'ปิด' })).toBeInTheDocument()
    })

    it('opening DetailSubform from an EDITABLE special row renders NO read-only affordances', async () => {
      const SPECIAL_GL_REF = [
        { gl_code: '5211900030', gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true },
      ]
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(SPECIAL_GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '5211900030', { editable: true })])
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      fireEvent.click(await screen.findByTestId('open-subform-CC1-5211900030'))

      expect(await screen.findByTestId('detail-subform')).toBeInTheDocument()
      expect(screen.queryByText(/อ่านอย่างเดียว \(แก้ไม่ได้\)/)).not.toBeInTheDocument()
      expect(screen.getByTestId('save-all')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'ยกเลิก' })).toBeInTheDocument()
    })

    it('opening Trip Manager from a LOCKED (editable:false) travel row renders its read-only affordances', async () => {
      const TRAVEL_GL_REF = [
        { gl_code: '5210400010', gl_group: 'Travelling Expense', gl_name: 'Per Diem', is_special: true },
      ]
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(TRAVEL_GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '5210400010', { editable: false })])
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      fireEvent.click(await screen.findByTestId('open-subform-CC1-5210400010'))

      expect(await screen.findByTestId('trip-manager')).toBeInTheDocument()
      expect(screen.getByText(/🔒 อ่านอย่างเดียว \(แก้ไม่ได้\)/)).toBeInTheDocument()
      expect(screen.queryByTestId('save-all')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'ปิด' })).toBeInTheDocument()
    })

    it('opening Trip Manager from an EDITABLE travel row renders NO read-only affordances', async () => {
      const TRAVEL_GL_REF = [
        { gl_code: '5210400010', gl_group: 'Travelling Expense', gl_name: 'Per Diem', is_special: true },
      ]
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(TRAVEL_GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '5210400010', { editable: true })])
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      fireEvent.click(await screen.findByTestId('open-subform-CC1-5210400010'))

      expect(await screen.findByTestId('trip-manager')).toBeInTheDocument()
      expect(screen.queryByText(/🔒 อ่านอย่างเดียว \(แก้ไม่ได้\)/)).not.toBeInTheDocument()
      expect(screen.getByTestId('save-all')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'ยกเลิก' })).toBeInTheDocument()
    })
  })

  // 2026-08-04, jakkaritw — FINAL: the Trip Manager's ฝั่งบัญชี select locks
  // to the side of the GL row the form was opened FROM (never ฝ่าย booking
  // history anymore), for every user incl. admins. These 3 tests replace
  // the old ฝ่าย-history-inheritance test above.
  it('opening from a 6xxx (SG&A) travel row locks the new trip to SG&A, select disabled', async () => {
    const TRAVEL_GL_REF = [
      { gl_code: '6210400010', gl_group: 'Travelling Expense', gl_name: 'Per Diem SGA', is_special: true },
    ]
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(TRAVEL_GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '6210400010')])
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    fireEvent.click(await screen.findByTestId('open-subform-CC1-6210400010'))
    expect(await screen.findByTestId('trip-manager')).toBeInTheDocument()

    const addBtn = await screen.findByRole('button', { name: /เพิ่มทริป/ })
    await waitFor(() => expect(addBtn).toBeEnabled()) // disabled while the trip list loads
    fireEvent.click(addBtn)
    const select = screen.getByLabelText('side new-0')
    expect(select).toHaveValue('SGA') // derived directly from the clicked row's own GL
    expect(select).toBeDisabled()
  })

  it('opening from a 5xxx (COST) travel row locks the new trip to COST, select disabled', async () => {
    const TRAVEL_GL_REF = [
      { gl_code: '5210400010', gl_group: 'Travelling Expense', gl_name: 'Per Diem COST', is_special: true },
    ]
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(TRAVEL_GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '5210400010')])
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    fireEvent.click(await screen.findByTestId('open-subform-CC1-5210400010'))
    expect(await screen.findByTestId('trip-manager')).toBeInTheDocument()

    const addBtn = await screen.findByRole('button', { name: /เพิ่มทริป/ })
    await waitFor(() => expect(addBtn).toBeEnabled())
    fireEvent.click(addBtn)
    const select = screen.getByLabelText('side new-0')
    expect(select).toHaveValue('COST')
    expect(select).toBeDisabled()
  })

  // Regression for the removed `!isAdmin` exemption (TripManager.tsx used to
  // read `!isAdmin && sideHistory.sides.length === 1`) — an admin scope must
  // get the SAME lock. TripManager no longer even accepts an `isAdmin` prop,
  // so this is the only level left that can prove the exemption is gone.
  it('locks the Trip Manager side select for an admin too — no exemption', async () => {
    const DUAL_ROLE_ADMIN: ScopeState = {
      role: 'admin', isAdmin: true, fillCostCenters: ['CC1'], seeCostCenters: ['CC1'], email: 'admin@chememan.com', loading: false, error: null,
    }
    const TRAVEL_GL_REF = [
      { gl_code: '6210400010', gl_group: 'Travelling Expense', gl_name: 'Per Diem SGA', is_special: true },
    ]
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(TRAVEL_GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '6210400010')])
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

    render(<BudgetGrid scope={DUAL_ROLE_ADMIN} initialFilter={{ dept: null, year: null }} />)

    fireEvent.click(await screen.findByTestId('open-subform-CC1-6210400010'))
    expect(await screen.findByTestId('trip-manager')).toBeInTheDocument()

    const addBtn = await screen.findByRole('button', { name: /เพิ่มทริป/ })
    await waitFor(() => expect(addBtn).toBeEnabled())
    fireEvent.click(addBtn)
    const select = screen.getByLabelText('side new-0')
    expect(select).toHaveValue('SGA')
    expect(select).toBeDisabled() // admin gets the same lock — no exemption
  })

  it('shows an actionable no-scope message (caller email + contact + master file) and never calls the budget/departments endpoints (A10 scope-role UX)', async () => {
    const NONE_SCOPE: ScopeState = {
      role: 'none', isAdmin: false, fillCostCenters: [], seeCostCenters: [],
      email: 'suchanyay@chememan.com', loading: false, error: null,
    }

    render(<BudgetGrid scope={NONE_SCOPE} initialFilter={{ dept: null, year: null }} />)

    const empty = await screen.findByTestId('no-scope-empty-state')
    expect(empty).toHaveTextContent('ไม่มีสิทธิ์เข้าถึงระบบงบประมาณ')
    expect(empty).toHaveTextContent('suchanyay@chememan.com')
    expect(empty).toHaveTextContent(SCOPE_ACCESS_CONTACT_EMAIL)
    expect(empty).toHaveTextContent(SCOPE_ACCESS_SOURCE_FILE)
    expect(empty).not.toHaveTextContent('Dashboard')
    expect(budgetApi.fetchDepartments).not.toHaveBeenCalled()
    expect(budgetApi.fetchBudgetGrid).not.toHaveBeenCalled()
  })

  it('omits the caller-email line entirely when scope.email is null (never prints "null" or a blank gap)', async () => {
    const NONE_SCOPE_NO_EMAIL: ScopeState = {
      role: 'none', isAdmin: false, fillCostCenters: [], seeCostCenters: [],
      email: null, loading: false, error: null,
    }

    render(<BudgetGrid scope={NONE_SCOPE_NO_EMAIL} initialFilter={{ dept: null, year: null }} />)

    const empty = await screen.findByTestId('no-scope-empty-state')
    expect(empty).toHaveTextContent('ไม่มีสิทธิ์เข้าถึงระบบงบประมาณ')
    expect(empty).toHaveTextContent(SCOPE_ACCESS_CONTACT_EMAIL)
    expect(empty).not.toHaveTextContent('null')
    expect(empty).not.toHaveTextContent('บัญชีของคุณ')
  })

  it('never shows the no-scope empty state for a filler scope (full page renders instead)', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    await waitFor(() => expect(budgetApi.fetchDepartments).toHaveBeenCalled())
    expect(screen.queryByTestId('no-scope-empty-state')).not.toBeInTheDocument()
  })

  it('never shows the no-scope empty state for a see_only scope (full page renders instead)', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={{ ...SCOPE, role: 'see_only', fillCostCenters: [] }} initialFilter={{ dept: null, year: null }} />)

    await waitFor(() => expect(budgetApi.fetchDepartments).toHaveBeenCalled())
    expect(screen.queryByTestId('no-scope-empty-state')).not.toBeInTheDocument()
  })

  it('shows the รออนุมัติ badge on the ฝ่าย picker when the caller is the current approver for it', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
    vi.mocked(approvalApi.fetchPendingForMe).mockResolvedValue({ departments: ['Solution Delivery'] })

    render(<BudgetGrid scope={{ ...SCOPE, role: 'see_only', fillCostCenters: [] }} initialFilter={{ dept: 'Solution Delivery', year: null }} />)

    await waitFor(() => expect(screen.getByTestId('dept-picker-pending-badge')).toBeInTheDocument())
  })

  it('a dual-role admin gets an admin-mode toggle that switches admin_view_enabled', async () => {
    const DUAL_ROLE_ADMIN: ScopeState = { role: 'admin', isAdmin: true, fillCostCenters: ['CC1'], seeCostCenters: ['CC1'], email: 'admin@chememan.com', loading: false, error: null }
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={DUAL_ROLE_ADMIN} initialFilter={{ dept: null, year: null }} />)

    const toggle = await screen.findByTestId('admin-mode-checkbox')
    await waitFor(() => expect(budgetApi.fetchDepartments).toHaveBeenLastCalledWith(false))

    fireEvent.click(toggle)

    await waitFor(() => expect(budgetApi.fetchDepartments).toHaveBeenLastCalledWith(true))
    await waitFor(() => expect(budgetApi.fetchBudgetGrid).toHaveBeenLastCalledWith(expect.objectContaining({ adminViewEnabled: true })))
  })

  it('re-auto-selects the first ฝ่าย after the admin-mode toggle switches (2026-07-24 rule)', async () => {
    const DUAL_ROLE_ADMIN: ScopeState = { role: 'admin', isAdmin: true, fillCostCenters: ['CC1'], seeCostCenters: ['CC1'], email: 'admin@chememan.com', loading: false, error: null }
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={DUAL_ROLE_ADMIN} initialFilter={{ dept: 'Solution Delivery', year: null }} />)

    const toggle = await screen.findByTestId('admin-mode-checkbox')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Solution Delivery' })).toBeInTheDocument())

    fireEvent.click(toggle)

    // The 2026-07-21 "never land unselected" rule now applies after a
    // hat-switch too: no settled placeholder — the dept re-resolves.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Solution Delivery' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: '— เลือกฝ่าย —' })).not.toBeInTheDocument()
  })

  it('after a hat-switch, auto-selects the FIRST ฝ่าย of the NEW scope (hierarchy order), not the previous pick', async () => {
    const DUAL_ROLE_ADMIN: ScopeState = { role: 'admin', isAdmin: true, fillCostCenters: ['CC1'], seeCostCenters: ['CC1'], email: 'admin@chememan.com', loading: false, error: null }
    const TWO_DEPTS = [
      { cost_center: 'CC2', department: 'Beta Dept', division: 'Div', c_level: 'X' },
      { cost_center: 'CC1', department: 'Alpha Dept', division: 'Div', c_level: 'X' },
    ]
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments)
      .mockResolvedValueOnce(DEPARTMENTS) // initial mount: single ฝ่าย
      .mockResolvedValue(TWO_DEPTS) // after toggle: the new, wider scope
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={DUAL_ROLE_ADMIN} initialFilter={{ dept: null, year: null }} />)

    const toggle = await screen.findByTestId('admin-mode-checkbox')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Solution Delivery' })).toBeInTheDocument())

    fireEvent.click(toggle)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Alpha Dept' })).toBeInTheDocument())
  })

  it('shows the status legend with SAP/Approved at year-1 and Pending at the selected year (they disambiguate the prior-year baseline)', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    const legend = await screen.findByTestId('status-legend')
    const items = legend.querySelectorAll('.legend-item')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('SAP · ใช้จริง (2026)')
    expect(items[1]).toHaveTextContent('Approved · งบอนุมัติ (2026)')
    expect(items[2]).toHaveTextContent('Pending · งบรออนุมัติ (2027)')
  })

  it('a non-admin, non-dual-role user never sees the admin-mode toggle', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    await waitFor(() => expect(budgetApi.fetchDepartments).toHaveBeenCalled())
    expect(screen.queryByTestId('admin-mode-checkbox')).not.toBeInTheDocument()
  })

  it('shows only the gear + "Admin" marker for an admin scope, with the full provenance (incl. the FX year one behind the planning year) in its tooltip', async () => {
    const ADMIN_SCOPE: ScopeState = { role: 'admin', isAdmin: true, fillCostCenters: [], seeCostCenters: [], email: 'admin@chememan.com', loading: false, error: null }
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={ADMIN_SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    const zone = await screen.findByTestId('admin-zone')
    // Visible text is deliberately just "Admin" (2026-08-04) — the strip is a
    // marker now, not a paragraph, so the grid gets the vertical space back.
    expect(zone).toHaveTextContent('Admin')
    expect(zone).not.toHaveTextContent('งบอนุมัติ (Approved) · Admin')
    expect(zone.querySelector('.admin-zone-title')).toHaveTextContent(/^Admin$/)
    expect(zone.querySelector('svg.admin-zone-ic')).toBeInTheDocument()
    // Everything the strip used to spell out survives in the tooltip, incl.
    // the FX year, which still tracks the selected planning year minus one.
    const tooltip = zone.getAttribute('title') ?? ''
    expect(tooltip).toContain('FY2026') // planning year 2027 - 1
    expect(tooltip).toContain('read-only')
    expect(tooltip).toContain('Budgeting and Management')
    expect(tooltip).toContain('Master Currency')
    // Read-only strip: no controls of any kind, and no stacked second row.
    expect(zone.querySelector('button')).not.toBeInTheDocument()
    expect(zone.querySelector('a')).not.toBeInTheDocument()
    expect(zone.querySelector('.admin-zone-actions')).not.toBeInTheDocument()
  })

  it('never shows the admin-only info strip for a non-admin scope', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    await waitFor(() => expect(budgetApi.fetchDepartments).toHaveBeenCalled())
    expect(screen.queryByTestId('admin-zone')).not.toBeInTheDocument()
  })

  describe('fullscreen mode (⤢ whole-grid overlay — jakkaritw-approved 2026-07-31)', () => {
    beforeEach(() => {
      // One COST row so exactly ONE side-table (and one toggle button) renders.
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([
        makeRow('CC1', '5211800030', {
          pending: { ...makeRow('x', 'y').pending, m01: 100, total_year: 100, updated_at: '2026-01-01T00:00:00Z' },
        }),
      ])
    })

    afterEach(() => {
      document.body.style.overflow = '' // safety net if a test fails mid-fullscreen
    })

    async function enterFullscreen() {
      fireEvent.click(await screen.findByTestId('enter-fullscreen-btn'))
      await waitFor(() => expect(screen.getByTestId('budget-grid')).toHaveClass('is-fullscreen'))
    }

    it('starts in normal mode: no is-fullscreen class on the root, body overflow untouched', async () => {
      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)
      await screen.findByTestId('enter-fullscreen-btn')
      expect(screen.getByTestId('budget-grid')).not.toHaveClass('is-fullscreen')
      expect(document.body.style.overflow).toBe('')
    })

    it('clicking ⤢ adds is-fullscreen to the root and locks body scroll', async () => {
      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)
      await enterFullscreen()
      expect(document.body.style.overflow).toBe('hidden')
    })

    it('clicking ⤡ exits: class removed and body overflow restored to its previous value', async () => {
      document.body.style.overflow = 'auto' // sentinel "previous value"
      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)
      await enterFullscreen()
      fireEvent.click(screen.getByTestId('exit-fullscreen-btn'))
      await waitFor(() => expect(screen.getByTestId('budget-grid')).not.toHaveClass('is-fullscreen'))
      expect(document.body.style.overflow).toBe('auto')
    })

    it('Escape on the page exits fullscreen', async () => {
      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)
      await enterFullscreen()
      fireEvent.keyDown(document.body, { key: 'Escape' })
      await waitFor(() => expect(screen.getByTestId('budget-grid')).not.toHaveClass('is-fullscreen'))
    })

    it('Escape fired from inside an input (a month cell) does NOT exit — the key belongs to the field', async () => {
      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)
      await enterFullscreen()
      fireEvent.keyDown(screen.getByTestId('pending-input-CC1-5211800030-m01'), { key: 'Escape' })
      expect(screen.getByTestId('budget-grid')).toHaveClass('is-fullscreen')
    })

    it('Escape while a modal (.modal-backdrop) is open does NOT exit — the key belongs to the modal', async () => {
      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)
      await enterFullscreen()
      const backdrop = document.createElement('div')
      backdrop.className = 'modal-backdrop'
      document.body.appendChild(backdrop)
      try {
        fireEvent.keyDown(document.body, { key: 'Escape' })
        expect(screen.getByTestId('budget-grid')).toHaveClass('is-fullscreen')
      } finally {
        backdrop.remove()
      }
    })

    it('unmounting while fullscreen still restores body overflow (no stuck hidden page)', async () => {
      const { unmount } = render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)
      await enterFullscreen()
      expect(document.body.style.overflow).toBe('hidden')
      unmount()
      expect(document.body.style.overflow).toBe('')
    })

    it('a month-cell edit still commits through the normal save path while fullscreen', async () => {
      vi.mocked(budgetApi.saveRow).mockResolvedValue({
        cost_center: 'CC1', gl_account: '5211800030', fiscal_year: 2027,
        m01: 999, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
        total_year: 999, remark: null, template: 'USER', gl_name: null, gl_group: null, c_level: null, division: null, department: null,
        updated_at: '2026-01-02T00:00:00Z',
      })
      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)
      await enterFullscreen()

      const input = screen.getByTestId('pending-input-CC1-5211800030-m01')
      fireEvent.change(input, { target: { value: '999' } })
      fireEvent.blur(input)

      await waitFor(() =>
        expect(budgetApi.saveRow).toHaveBeenCalledWith(
          expect.objectContaining({ cost_center: 'CC1', gl_account: '5211800030', fiscal_year: 2027, m01: 999 }),
        ),
      )
    })
  })
})
