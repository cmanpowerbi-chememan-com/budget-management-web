import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetRow } from '../api/types'
import type { ScopeState } from '../auth/useScope'
import { ApiError } from '../api/client'
import * as approvalApi from '../api/approval'
import * as budgetApi from '../api/budget'
import * as referenceApi from '../api/reference'
import * as subformApi from '../api/subform'
import { BudgetGrid } from './BudgetGrid'
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

    it('fetches the grid exactly once on mount for a >1-ฝ่าย caller, with no ฝ่าย auto-selected', async () => {
      const MULTI_DEPARTMENTS = [
        { cost_center: 'CC1', department: 'Solution Delivery', division: 'Digital Technology Division', c_level: 'CTO' },
        { cost_center: 'CC3', department: 'Budgeting and Management Accounting', division: 'Budgeting and Cost Accounting Division', c_level: 'CFO' },
      ]
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(MULTI_DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      await waitFor(() => expect(screen.getByRole('button', { name: '— เลือกฝ่าย —' })).toBeInTheDocument())
      await waitFor(() => expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1))
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledWith(expect.objectContaining({ department: undefined }))
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
    fireEvent.change(screen.getByLabelText('Cost Center'), { target: { value: 'CC1' } })
    fireEvent.change(screen.getByLabelText('GL Code'), { target: { value: '5211800030' } })
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(screen.getByTestId('pending-cell-CC1-5211800030-m01')).toBeInTheDocument())
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

  it('derives the trip side at ฝ่าย grain: a CC with no own travel history inherits its sibling CC\'s side (locked for non-admin)', async () => {
    const TRAVEL_GL_REF = [
      { gl_code: '6210400010', gl_group: 'Travelling Expense', gl_name: 'Per Diem SGA', is_special: true },
    ]
    const TWO_CC_DEPT = [
      { cost_center: 'CC1', department: 'Solution Delivery', division: 'Digital Technology Division', c_level: 'CTO' },
      { cost_center: 'CC2', department: 'Solution Delivery', division: 'Digital Technology Division', c_level: 'CTO' },
    ]
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(TRAVEL_GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(TWO_CC_DEPT)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([
      makeRow('CC1', '6210400010'), // the trip CC — zero history of its own
      makeRow('CC2', '6210400010', { sap: blankLayer({ m01: 100, total_year: 100 }) }), // sibling CC: SGA history
    ])
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    fireEvent.click(await screen.findByTestId('open-subform-CC1-6210400010'))
    expect(await screen.findByTestId('trip-manager')).toBeInTheDocument()

    const addBtn = await screen.findByRole('button', { name: /เพิ่มทริป/ })
    await waitFor(() => expect(addBtn).toBeEnabled()) // disabled while the trip list loads
    fireEvent.click(addBtn)
    const select = screen.getByLabelText('side new-0')
    expect(select).toHaveValue('SGA') // inherited from CC2, not a blind default
    expect(select).toBeDisabled() // single side across the ฝ่าย + non-admin
  })

  it('shows the no-scope empty state and never calls the budget/departments endpoints (A10 scope-role UX)', async () => {
    const NONE_SCOPE: ScopeState = { role: 'none', isAdmin: false, fillCostCenters: [], seeCostCenters: [], loading: false, error: null }

    render(<BudgetGrid scope={NONE_SCOPE} initialFilter={{ dept: null, year: null }} />)

    expect(await screen.findByTestId('no-scope-empty-state')).toHaveTextContent('ดูข้อมูลได้ที่ Dashboard')
    expect(budgetApi.fetchDepartments).not.toHaveBeenCalled()
    expect(budgetApi.fetchBudgetGrid).not.toHaveBeenCalled()
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
    const DUAL_ROLE_ADMIN: ScopeState = { role: 'admin', isAdmin: true, fillCostCenters: ['CC1'], seeCostCenters: ['CC1'], loading: false, error: null }
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

  it('resets the selected ฝ่าย to null when the admin-mode toggle switches (ADR-0014)', async () => {
    const DUAL_ROLE_ADMIN: ScopeState = { role: 'admin', isAdmin: true, fillCostCenters: ['CC1'], seeCostCenters: ['CC1'], loading: false, error: null }
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={DUAL_ROLE_ADMIN} initialFilter={{ dept: 'Solution Delivery', year: null }} />)

    const toggle = await screen.findByTestId('admin-mode-checkbox')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Solution Delivery' })).toBeInTheDocument())

    fireEvent.click(toggle)

    await waitFor(() => expect(screen.getByRole('button', { name: '— เลือกฝ่าย —' })).toBeInTheDocument())
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

  it('shows the read-only "Approved · Admin" info strip for an admin scope, with the FX year one behind the selected planning year', async () => {
    const ADMIN_SCOPE: ScopeState = { role: 'admin', isAdmin: true, fillCostCenters: [], seeCostCenters: [], loading: false, error: null }
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={ADMIN_SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    const zone = await screen.findByTestId('admin-zone')
    expect(zone).toHaveTextContent('งบอนุมัติ (Approved) · Admin')
    expect(zone).toHaveTextContent('FY2026') // planning year 2027 - 1
    expect(zone).toHaveTextContent('read-only')
    expect(zone).toHaveTextContent('Budgeting and Management')
    expect(zone.querySelector('button')).not.toBeInTheDocument()
    const fxLink = zone.querySelector('a')
    expect(fxLink).toHaveAttribute('target', '_blank')
    expect(fxLink).toHaveAttribute('href', 'https://witty-meadow-01107f500.7.azurestaticapps.net/master-currency.html')
  })

  it('never shows the admin-only info strip for a non-admin scope', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

    await waitFor(() => expect(budgetApi.fetchDepartments).toHaveBeenCalled())
    expect(screen.queryByTestId('admin-zone')).not.toBeInTheDocument()
  })
})
