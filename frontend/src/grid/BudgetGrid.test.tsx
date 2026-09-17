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

// Issue #13, decision E: `admitRows` (BudgetGrid.loadGrid) now keeps only
// rows whose `department` matches the selected ฝ่าย — defaults to
// 'Solution Delivery' (the DEPARTMENTS fixture below auto-selects it for
// CC1, the single-Cost-Center scope most tests use); a test scoped to a
// different/no selected department overrides this explicitly.
function makeRow(cc: string, gl: string, overrides: Partial<BudgetRow> = {}): BudgetRow {
  return makeRowFromOverrides({ cost_center: cc, gl_account: gl, editable: true, department: 'Solution Delivery', ...overrides })
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

/** Drives the DeptPicker UI to switch the selected ฝ่าย — issue #13 scoped
 * "+ เพิ่ม Transaction" to the ฝ่าย on screen, so a test exercising 2+ ฝ่าย in
 * one render must actually switch between them (a deep-linked
 * `initialFilter.dept` only ever applies once, at mount). */
function switchDepartment(target: string) {
  fireEvent.click(document.querySelector('.dept-picker-trigger') as Element)
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${target}`) }))
}

describe('BudgetGrid', () => {
  beforeEach(() => {
    // A10 รออนุมัติ badge — called unconditionally on every mount/year
    // change, so every test needs a default (most tests are not testing
    // the badge itself and just need this to resolve quietly).
    vi.mocked(approvalApi.fetchPendingForMe).mockResolvedValue({ departments: [] })
    // "+ เพิ่ม Transaction" lock-awareness (2026-08-08 bug fix) — called
    // unconditionally on every mount/year change, same as fetchPendingForMe
    // above; most tests are not testing this feature and just need it to
    // resolve quietly with "nothing locked".
    vi.mocked(approvalApi.fetchLockedDepartments).mockResolvedValue({ departments: [], year_not_open: false })
    // Trip Manager loads these reference masters whenever it opens — the two
    // trip tests here only need them to resolve quietly.
    vi.mocked(referenceApi.fetchTravelers).mockResolvedValue([])
    vi.mocked(referenceApi.fetchCountries).mockResolvedValue([])
    // SAP freshness chip (ADR-0030) — called unconditionally on every
    // mount/year change, same as fetchPendingForMe above; a healthy default
    // so tests not exercising the chip itself see the plain legend text.
    vi.mocked(budgetApi.fetchSapCoverage).mockResolvedValue({
      fiscal_year: 2026, watermark_date: '2026-09-11', days_behind: 1, is_stale: false,
    })
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
      m01: 900, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
      total_year: 900, remark: null, template: 'USER', gl_name: null, gl_group: null, c_level: null, division: null, department: null,
      updated_at: '2026-01-02T00:00:00Z',
    })

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    const input = await screen.findByTestId('pending-input-CC1-5211800030-m01')
    fireEvent.change(input, { target: { value: '900' } })
    fireEvent.blur(input)

    await waitFor(() =>
      expect(budgetApi.saveRow).toHaveBeenCalledWith(
        expect.objectContaining({
          cost_center: 'CC1',
          gl_account: '5211800030',
          fiscal_year: 2027,
          m01: 900,
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
    fireEvent.change(input, { target: { value: '900' } })
    fireEvent.blur(input)

    await waitFor(() => expect(screen.getByText(/หมดเวลาการเข้าใช้งาน/)).toBeInTheDocument())
    // Never refetches on this error kind (unlike 409) — the optimistic
    // value is simply left in place, not reconciled against the server.
    expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('pending-input-CC1-5211800030-m01')).toHaveValue('900')
  })

  it('a save rejected as department-locked (403) shows the Thai reason and reverts the cell', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    const freshRow = makeRow('CC1', '5211800030', {
      pending: { ...makeRow('x', 'y').pending, m01: 100, total_year: 100, updated_at: '2026-01-01T00:00:00Z' },
      editable: false,
    })
    vi.mocked(budgetApi.fetchBudgetGrid)
      .mockResolvedValueOnce([
        makeRow('CC1', '5211800030', {
          pending: { ...makeRow('x', 'y').pending, m01: 100, total_year: 100, updated_at: '2026-01-01T00:00:00Z' },
        }),
      ])
      // Refetch after the rejected save — the department is now locked, so
      // the server's own row.editable flips false too (same source of
      // truth the grid always reads).
      .mockResolvedValueOnce([freshRow])
    vi.mocked(budgetApi.saveRow).mockRejectedValue(
      new ApiError(
        403,
        'บันทึกไม่สำเร็จ — ฝ่ายนี้ส่งขออนุมัติแล้ว จึงแก้ไขไม่ได้ กรุณาโหลดหน้าใหม่',
        'ฝ่ายบัญชี/2027 is PENDING_APPROVER1 — mid-approval or approved, editing is locked',
      ),
    )

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    const input = await screen.findByTestId('pending-input-CC1-5211800030-m01')
    fireEvent.change(input, { target: { value: '777' } })
    fireEvent.blur(input)

    await waitFor(() => expect(screen.getByText(/ฝ่ายนี้ส่งขออนุมัติแล้ว/)).toBeInTheDocument())
    // Reverts the cell AND flips it read-only — same refetch-and-trust-the-
    // server contract the 409 path already uses.
    await waitFor(() => expect(screen.getByTestId('pending-cell-CC1-5211800030-m01')).toHaveTextContent('100'))
    expect(screen.queryByTestId('pending-input-CC1-5211800030-m01')).not.toBeInTheDocument()
  })

  // S2 gate follow-up (issue #13): department_unknown must go through the
  // SAME refusal handling as department_locked — mirrors the test above,
  // only the Thai message and raw ApiError.detail differ.
  it('a save rejected as department_unknown (403) shows the Thai reason and reverts the cell', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    const freshRow = makeRow('CC1', '5211800030', {
      pending: { ...makeRow('x', 'y').pending, m01: 100, total_year: 100, updated_at: '2026-01-01T00:00:00Z' },
      editable: false,
    })
    vi.mocked(budgetApi.fetchBudgetGrid)
      .mockResolvedValueOnce([
        makeRow('CC1', '5211800030', {
          pending: { ...makeRow('x', 'y').pending, m01: 100, total_year: 100, updated_at: '2026-01-01T00:00:00Z' },
        }),
      ])
      .mockResolvedValueOnce([freshRow])
    vi.mocked(budgetApi.saveRow).mockRejectedValue(
      new ApiError(
        403,
        'cost center นี้ยังไม่มีฝ่ายในไฟล์ master กรุณาติดต่อ admin',
        'CC1 has no department mapping in dbo.cc_filler_map — cannot verify approval-lock status',
      ),
    )

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    const input = await screen.findByTestId('pending-input-CC1-5211800030-m01')
    fireEvent.change(input, { target: { value: '777' } })
    fireEvent.blur(input)

    await waitFor(() => expect(screen.getByText('cost center นี้ยังไม่มีฝ่ายในไฟล์ master กรุณาติดต่อ admin')).toBeInTheDocument())
    expect(screen.queryByText(/cannot verify approval-lock status/)).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('pending-cell-CC1-5211800030-m01')).toHaveTextContent('100'))
    expect(screen.queryByTestId('pending-input-CC1-5211800030-m01')).not.toBeInTheDocument()
  })

  it('a successful Submit flips the grid to read-only immediately, without a page reload', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid)
      .mockResolvedValueOnce([
        makeRow('CC1', '5211800030', {
          pending: { ...makeRow('x', 'y').pending, m01: 100, total_year: 100, updated_at: '2026-01-01T00:00:00Z' },
        }),
      ])
      // Refetch triggered by ApprovalActionBar's onChanged after a
      // successful submit — the server now reports the row locked.
      .mockResolvedValueOnce([
        makeRow('CC1', '5211800030', {
          pending: { ...makeRow('x', 'y').pending, m01: 100, total_year: 100, updated_at: '2026-01-01T00:00:00Z' },
          editable: false,
        }),
      ])
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue({
      department: 'Solution Delivery', fiscal_year: 2027, status: 'DRAFT',
      submitter_empcode: null, submitter_email: null, submitted_at: null,
      approver1_empcode: null, approver1_actioned_at: null, approver2_actioned_at: null, approver3_actioned_at: null,
      reject_reason: null, rejected_by_empcode: null, updated_at: null,
      current_position: null, current_approver_empcode: null, can_act: false, notification_warning: null,
      can_submit: true, submit_blocked_reason: null,
    })
    vi.mocked(approvalApi.submitDepartment).mockResolvedValue({
      department: 'Solution Delivery', fiscal_year: 2027, status: 'PENDING_APPROVER1',
      submitter_empcode: null, submitter_email: null, submitted_at: null,
      approver1_empcode: null, approver1_actioned_at: null, approver2_actioned_at: null, approver3_actioned_at: null,
      reject_reason: null, rejected_by_empcode: null, updated_at: null,
      current_position: null, current_approver_empcode: null, can_act: false, notification_warning: null,
      can_submit: false, submit_blocked_reason: 'invalid_approval_state',
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    await screen.findByTestId('pending-input-CC1-5211800030-m01')
    const submitBtn = await screen.findByTestId('approval-submit-btn')
    fireEvent.click(submitBtn)

    await waitFor(() => expect(approvalApi.submitDepartment).toHaveBeenCalled())
    // Same-page flip — no reload, just the grid re-rendering read-only once
    // the refetched rows come back with editable:false.
    await waitFor(() => expect(screen.queryByTestId('pending-input-CC1-5211800030-m01')).not.toBeInTheDocument())
    expect(screen.getByTestId('pending-cell-CC1-5211800030-m01')).toHaveTextContent('100')

    vi.restoreAllMocks()
  })

  it('a successful month-cell save on an empty department refreshes the Submit button without a page reload (bug fixed 2026-09-16)', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    // The department has no pending_budget rows yet -- the grid still shows
    // the GL master's template row (all-zero Pending), which is exactly how
    // a Filler reaches "type into a month cell" on an otherwise-empty ฝ่าย.
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '5211800030')])
    vi.mocked(budgetApi.saveRow).mockResolvedValue({
      cost_center: 'CC1', gl_account: '5211800030', fiscal_year: 2027,
      m01: 900, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
      total_year: 900, remark: null, template: 'USER', gl_name: null, gl_group: null, c_level: null, division: null, department: null,
      updated_at: '2026-01-02T00:00:00Z',
    })
    vi.mocked(approvalApi.fetchApprovalStatus)
      // 1st call: initial mount -- the department is genuinely empty.
      .mockResolvedValueOnce({
        department: 'Solution Delivery', fiscal_year: 2027, status: 'DRAFT',
        submitter_empcode: null, submitter_email: null, submitted_at: null,
        approver1_empcode: null, approver1_actioned_at: null, approver2_actioned_at: null, approver3_actioned_at: null,
        reject_reason: null, rejected_by_empcode: null, updated_at: null,
        current_position: null, current_approver_empcode: null, can_act: false, notification_warning: null,
        can_submit: false, submit_blocked_reason: 'department_empty',
      })
      // 2nd call: the refetch the month-cell save must trigger -- the
      // department now has a row, so the server allows Submit.
      .mockResolvedValueOnce({
        department: 'Solution Delivery', fiscal_year: 2027, status: 'DRAFT',
        submitter_empcode: null, submitter_email: null, submitted_at: null,
        approver1_empcode: null, approver1_actioned_at: null, approver2_actioned_at: null, approver3_actioned_at: null,
        reject_reason: null, rejected_by_empcode: null, updated_at: null,
        current_position: null, current_approver_empcode: null, can_act: false, notification_warning: null,
        can_submit: true, submit_blocked_reason: null,
      })

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    await screen.findByTestId('approval-submit-blocked-hint')
    expect(screen.queryByTestId('approval-submit-btn')).not.toBeInTheDocument()

    const input = await screen.findByTestId('pending-input-CC1-5211800030-m01')
    fireEvent.change(input, { target: { value: '900' } })
    fireEvent.blur(input)

    await waitFor(() => expect(budgetApi.saveRow).toHaveBeenCalled())
    await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.getByTestId('approval-submit-btn')).toBeInTheDocument())
  })

  it('a FAILED month-cell save (409) does not refresh the approval status', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '5211800030')])
    vi.mocked(budgetApi.saveRow).mockRejectedValue(
      new ApiError(409, 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น กรุณาโหลดข้อมูลใหม่แล้วลองอีกครั้ง', 'changed by someone else'),
    )
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue({
      department: 'Solution Delivery', fiscal_year: 2027, status: 'DRAFT',
      submitter_empcode: null, submitter_email: null, submitted_at: null,
      approver1_empcode: null, approver1_actioned_at: null, approver2_actioned_at: null, approver3_actioned_at: null,
      reject_reason: null, rejected_by_empcode: null, updated_at: null,
      current_position: null, current_approver_empcode: null, can_act: false, notification_warning: null,
      can_submit: false, submit_blocked_reason: 'department_empty',
    })

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    await screen.findByTestId('approval-submit-blocked-hint')
    const input = await screen.findByTestId('pending-input-CC1-5211800030-m01')
    fireEvent.change(input, { target: { value: '900' } })
    fireEvent.blur(input)

    await waitFor(() => expect(screen.getByText(/ถูกแก้ไขโดยผู้อื่น/)).toBeInTheDocument())
    // The failed save still refetches the GRID (409 contract, unrelated to
    // this fix) but must NOT touch the approval status -- only one GET
    // /approval/status ever happens (the initial mount).
    expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('approval-submit-blocked-hint')).toBeInTheDocument()
  })

  it('a successful "+ เพิ่ม Transaction" with a NORMAL (non-special) GL on an empty department refreshes the Submit button without a page reload (gap closed 2026-09-16)', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
    vi.mocked(budgetApi.saveRow).mockResolvedValue({
      cost_center: 'CC1', gl_account: '5211800030', fiscal_year: 2027,
      m01: 0, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
      total_year: 0, remark: null, template: 'USER', gl_name: 'Office COST', gl_group: 'Office expenses', c_level: null, division: null, department: null,
      updated_at: '2026-01-01T00:00:00Z',
    })
    vi.mocked(approvalApi.fetchApprovalStatus)
      // 1st call: initial mount -- the department is genuinely empty.
      .mockResolvedValueOnce({
        department: 'Solution Delivery', fiscal_year: 2027, status: 'DRAFT',
        submitter_empcode: null, submitter_email: null, submitted_at: null,
        approver1_empcode: null, approver1_actioned_at: null, approver2_actioned_at: null, approver3_actioned_at: null,
        reject_reason: null, rejected_by_empcode: null, updated_at: null,
        current_position: null, current_approver_empcode: null, can_act: false, notification_warning: null,
        can_submit: false, submit_blocked_reason: 'department_empty',
      })
      // 2nd call: the refetch the new-transaction save must trigger -- the
      // department now has a row, so the server allows Submit.
      .mockResolvedValueOnce({
        department: 'Solution Delivery', fiscal_year: 2027, status: 'DRAFT',
        submitter_empcode: null, submitter_email: null, submitted_at: null,
        approver1_empcode: null, approver1_actioned_at: null, approver2_actioned_at: null, approver3_actioned_at: null,
        reject_reason: null, rejected_by_empcode: null, updated_at: null,
        current_position: null, current_approver_empcode: null, can_act: false, notification_warning: null,
        can_submit: true, submit_blocked_reason: null,
      })

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    await waitFor(() => expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument())
    await screen.findByTestId('approval-submit-blocked-hint')
    expect(screen.queryByTestId('approval-submit-btn')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    fireEvent.focus(screen.getByLabelText('Cost Center'))
    fireEvent.click(screen.getByRole('option', { name: 'CC1' }))
    fireEvent.focus(screen.getByLabelText('GL Code'))
    fireEvent.click(screen.getByRole('option', { name: /5211800030/ }))
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(budgetApi.saveRow).toHaveBeenCalled())
    await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.getByTestId('approval-submit-btn')).toBeInTheDocument())
  })

  it('a FAILED "+ เพิ่ม Transaction" save (409) does not refresh the approval status', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
    vi.mocked(budgetApi.saveRow).mockRejectedValue(
      new ApiError(409, 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น กรุณาโหลดข้อมูลใหม่แล้วลองอีกครั้ง', 'duplicate row'),
    )
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue({
      department: 'Solution Delivery', fiscal_year: 2027, status: 'DRAFT',
      submitter_empcode: null, submitter_email: null, submitted_at: null,
      approver1_empcode: null, approver1_actioned_at: null, approver2_actioned_at: null, approver3_actioned_at: null,
      reject_reason: null, rejected_by_empcode: null, updated_at: null,
      current_position: null, current_approver_empcode: null, can_act: false, notification_warning: null,
      can_submit: false, submit_blocked_reason: 'department_empty',
    })

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    await waitFor(() => expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument())
    await screen.findByTestId('approval-submit-blocked-hint')

    fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
    fireEvent.focus(screen.getByLabelText('Cost Center'))
    fireEvent.click(screen.getByRole('option', { name: 'CC1' }))
    fireEvent.focus(screen.getByLabelText('GL Code'))
    fireEvent.click(screen.getByRole('option', { name: /5211800030/ }))
    fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

    await waitFor(() => expect(budgetApi.saveRow).toHaveBeenCalled())
    // A failed create must not touch approval status at all -- only the
    // initial mount's GET /approval/status ever happens.
    expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('approval-submit-blocked-hint')).toBeInTheDocument()
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

    // Issue #13, decision H (2026-09-17): this delete path had no
    // department-locked branch at all before — only persistRow's did.
    it('on a department-locked refusal, shows the Thai message only and reloads the grid (no raw English detail)', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([
        makeRow('CC1', '5211800030', {
          pending: { ...makeRow('x', 'y').pending, updated_at: '2026-01-01T00:00:00Z' },
        }),
      ])
      vi.mocked(budgetApi.deleteRow).mockRejectedValue(
        new ApiError(
          403,
          'บันทึกไม่สำเร็จ — ฝ่ายนี้ส่งขออนุมัติแล้ว จึงแก้ไขไม่ได้ กรุณาโหลดหน้าใหม่',
          'Solution Delivery/2027 is PENDING_APPROVER1 — mid-approval or approved, editing is locked',
        ),
      )
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue({
        department: 'Solution Delivery', fiscal_year: 2027, status: 'DRAFT', submitter_empcode: null,
        submitter_email: null, submitted_at: null, approver1_empcode: null, approver1_actioned_at: null,
        approver2_actioned_at: null, approver3_actioned_at: null, reject_reason: null, rejected_by_empcode: null,
        updated_at: null, current_position: null, current_approver_empcode: null, current_approver_name: null,
        can_act: false, notification_warning: null, is_post_deadline: false, can_submit: false,
        submit_blocked_reason: null, locked: false,
      })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

      const deleteBtn = await screen.findByTestId('delete-row-CC1-5211800030')
      fireEvent.click(deleteBtn)

      await waitFor(() => expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(2))
      expect(screen.getByText('บันทึกไม่สำเร็จ — ฝ่ายนี้ส่งขออนุมัติแล้ว จึงแก้ไขไม่ได้ กรุณาโหลดหน้าใหม่')).toBeInTheDocument()
      expect(screen.queryByText(/mid-approval or approved/)).not.toBeInTheDocument()
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
      total_year: 0, remark: null, template: 'USER', gl_name: 'Office COST', gl_group: 'Office expenses', c_level: null, division: null,
      department: 'Solution Delivery', updated_at: '2026-01-01T00:00:00Z', editable: true, lock_reason: 'none',
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

  // "+ เพิ่ม Transaction" lock-awareness (2026-08-08 bug fix, ADR-0013 UI
  // parity): a Filler whose department is already mid-approval/APPROVED
  // used to be able to open the Add form, pick a Cost Center + GL, and only
  // THEN get a late 403 `department_locked`. jakkaritw's decision: keep the
  // button VISIBLE but non-actionable with the reason on screen — never a
  // blanket disable, since a Filler can hold Cost Centers in more than one
  // ฝ่าย (45% do).
  describe('"+ เพิ่ม Transaction" lock-awareness (BudgetGrid wiring)', () => {
    it('the caller\'s only department is locked — the Add button is visible but disabled, reason on screen', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
      vi.mocked(approvalApi.fetchLockedDepartments).mockResolvedValue({ departments: ['Solution Delivery'], year_not_open: false })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      const trigger = await screen.findByRole('button', { name: /เพิ่ม transaction/i })
      await waitFor(() => expect(trigger).toBeDisabled())
      // The reason names the LOCKED ฝ่าย on screen — one text node combining
      // both, so this uniquely targets the disabled-reason span (not the
      // dept-picker trigger, which also just says "Solution Delivery" alone).
      expect(screen.getByText(/Solution Delivery.*อยู่ระหว่างอนุมัติหรืออนุมัติแล้ว/)).toBeInTheDocument()
    })

    // 2026-08-08 3-state extension: a YEAR-wide lock (from the SAME
    // GET /approval/locked-departments fetch, its `year_not_open` field) —
    // every department is closed, not just the ones already mid-approval.
    it('the fiscal_year is NOT_OPEN — the Add button is visible but disabled, with the year-wide Thai reason on screen', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
      vi.mocked(approvalApi.fetchLockedDepartments).mockResolvedValue({ departments: [], year_not_open: true })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      const trigger = await screen.findByRole('button', { name: /เพิ่ม transaction/i })
      await waitFor(() => expect(trigger).toBeDisabled())
      expect(screen.getByText(/ไม่เปิดให้กรอกในเว็บ/)).toBeInTheDocument()
    })

    it('the department is open (DRAFT, nothing locked) — unchanged: Add button works and the new row renders editable (derived, not hardcoded)', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
      vi.mocked(approvalApi.fetchLockedDepartments).mockResolvedValue({ departments: [], year_not_open: false })
      vi.mocked(budgetApi.saveRow).mockResolvedValue({
        cost_center: 'CC1', gl_account: '5211800030', fiscal_year: 2027,
        m01: 0, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
        total_year: 0, remark: null, template: 'USER', gl_name: null, gl_group: null, c_level: null, division: null,
        department: 'Solution Delivery', updated_at: '2026-01-01T00:00:00Z', editable: true, lock_reason: 'none',
      })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      await waitFor(() => expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument())
      const trigger = screen.getByRole('button', { name: /เพิ่ม transaction/i })
      expect(trigger).not.toBeDisabled()
      fireEvent.click(trigger)
      fireEvent.focus(screen.getByLabelText('Cost Center'))
      fireEvent.click(screen.getByRole('option', { name: 'CC1' }))
      fireEvent.focus(screen.getByLabelText('GL Code'))
      fireEvent.click(screen.getByRole('option', { name: /5211800030/ }))
      fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

      // A real editable <input>, not a read-only display — proves the new
      // row's `editable` was actually derived, not just hardcoded true.
      expect(await screen.findByTestId('pending-input-CC1-5211800030-m01')).toBeInTheDocument()
    })

    // Issue #13, G1 (2026-09-17): this test used to pin the PHANTOM-ROW
    // bug — with BOTH Cost Centers offered by one shared Add form, adding
    // to the OPEN one while the LOCKED one was on screen (or vice versa)
    // rendered a live editable row under the wrong/locked ฝ่าย heading.
    // Rewritten to pin the FIX: the Add form is scoped to the ฝ่าย on
    // screen — disabled while looking at the locked one, and only offers
    // (and only succeeds for) the OPEN ฝ่าย's own Cost Center once the
    // picker switches there.
    //
    // Hoisted out of this test (2026-09-17, HIGH-1/MED-1 gate fixes) so the
    // focus/visibility-revalidation tests below can reuse the same 2-ฝ่าย
    // Fill scope instead of redeclaring it.
    const twoDeptScope: ScopeState = { ...SCOPE, fillCostCenters: ['CC1', 'CC2'], seeCostCenters: ['CC1', 'CC2'] }
    const twoDepartments = [
      ...DEPARTMENTS,
      { cost_center: 'CC2', department: 'Warehouse', division: 'Digital Technology Division', c_level: 'CTO' },
    ]

    it('picker on the locked ฝ่าย disables Add; switching to the open ฝ่าย re-enables it and only offers that ฝ่าย\'s own Cost Center', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(twoDepartments)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
      vi.mocked(approvalApi.fetchLockedDepartments).mockResolvedValue({ departments: ['Solution Delivery'], year_not_open: false })
      vi.mocked(budgetApi.saveRow).mockResolvedValue({
        cost_center: 'CC2', gl_account: '5211800030', fiscal_year: 2027,
        m01: 0, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
        total_year: 0, remark: null, template: 'USER', gl_name: null, gl_group: null, c_level: null, division: null,
        department: 'Warehouse', updated_at: '2026-01-01T00:00:00Z', editable: true, lock_reason: 'none',
      })

      render(<BudgetGrid scope={twoDeptScope} initialFilter={{ dept: null, year: null }} />)

      // Auto-selects "Solution Delivery" (alphabetically first within the
      // shared division) — locked per the mock above.
      const trigger = await screen.findByRole('button', { name: /เพิ่ม transaction/i })
      await waitFor(() => expect(trigger).toBeDisabled())

      switchDepartment('Warehouse')
      await waitFor(() => expect(trigger).not.toBeDisabled())

      fireEvent.click(trigger)
      fireEvent.focus(screen.getByLabelText('Cost Center'))
      // CC1 (the locked ฝ่าย's own Cost Center) is not even offered anymore.
      expect(screen.queryByRole('option', { name: 'CC1' })).not.toBeInTheDocument()
      fireEvent.click(screen.getByRole('option', { name: 'CC2' }))
      fireEvent.focus(screen.getByLabelText('GL Code'))
      fireEvent.click(screen.getByRole('option', { name: /5211800030/ }))
      fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

      // The new row renders under Warehouse (the ฝ่าย on screen) — never a
      // phantom row appended regardless of which ฝ่าย it actually belongs to.
      expect(await screen.findByTestId('pending-input-CC2-5211800030-m01')).toBeInTheDocument()
    })

    // Issue #13, decision E: the row-admission function's defensive branch —
    // unreachable via the form itself (validateNewTransaction already blocks
    // a Cost Center outside the selected ฝ่าย), but a live CC->ฝ่าย remap
    // landing between the form opening and the save completing could still
    // make the server's response disagree with what was on screen.
    it('an added row whose response department differs from the one on screen is NOT appended', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
      vi.mocked(budgetApi.saveRow).mockResolvedValue({
        cost_center: 'CC1', gl_account: '5211800030', fiscal_year: 2027,
        m01: 0, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
        total_year: 0, remark: null, template: 'USER', gl_name: null, gl_group: null, c_level: null, division: null,
        department: 'Some Other Department', updated_at: '2026-01-01T00:00:00Z', editable: true, lock_reason: 'none',
      })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      await waitFor(() => expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument())
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      fireEvent.focus(screen.getByLabelText('Cost Center'))
      fireEvent.click(screen.getByRole('option', { name: 'CC1' }))
      fireEvent.focus(screen.getByLabelText('GL Code'))
      fireEvent.click(screen.getByRole('option', { name: /5211800030/ }))
      fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

      await waitFor(() => expect(budgetApi.saveRow).toHaveBeenCalled())
      expect(screen.queryByTestId('pending-input-CC1-5211800030-m01')).not.toBeInTheDocument()
    })

    // Issue #13, decision G: the lock-status fetch itself failing must never
    // silently fall open — the button disables with its own reason, but the
    // grid itself still loads (rows carry their own server-truth editable).
    it('a failed GET /approval/locked-departments disables Add (never falls open) while the grid still loads', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([makeRow('CC1', '5211800030')])
      vi.mocked(approvalApi.fetchLockedDepartments).mockRejectedValue(new Error('network down'))

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      const trigger = await screen.findByRole('button', { name: /เพิ่ม transaction/i })
      await waitFor(() => expect(trigger).toBeDisabled())
      expect(screen.getByText(/ไม่สามารถตรวจสอบสถานะฝ่าย/)).toBeInTheDocument()
      // The grid itself is unaffected — it still renders.
      expect(await screen.findByTestId('txn-CC1-5211800030')).toBeInTheDocument()
    })

    // Gate LOW-1 (2026-09-17): `departmentUnknown` used to be a bare
    // `department === null`, true on EVERY mount (department starts `null`
    // until `GET /scope/departments` resolves) — so the "ยังไม่ทราบฝ่าย" reason
    // flashed on first paint even for a Filler with exactly one ฝ่าย. It must
    // only mean "we resolved, and there is genuinely no ฝ่าย" (a load
    // failure, covered by the test above).
    it('does not show the "ยังไม่ทราบฝ่าย" reason on first paint, before departments have resolved', async () => {
      let resolveDepartments!: (value: typeof DEPARTMENTS) => void
      const pending = new Promise<typeof DEPARTMENTS>((resolve) => {
        resolveDepartments = resolve
      })
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockReturnValue(pending)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      // First paint — the departments promise has not resolved yet.
      expect(screen.getByRole('button', { name: /เพิ่ม transaction/i })).toBeInTheDocument()
      expect(screen.queryByText(/ยังไม่ทราบฝ่าย/)).not.toBeInTheDocument()

      resolveDepartments(DEPARTMENTS)
      await waitFor(() => expect(budgetApi.fetchBudgetGrid).toHaveBeenCalled())
    })

    // Issue #13, decision I (2026-09-17): a tab left open before a submit
    // (by another tab/device/co-Filler) must lock itself within one focus
    // change, not never.
    // Shared by both revalidation-trigger variants below (focus + visibility)
    // — 2 ฝ่าย so `department` resolves to a non-null value AFTER mount
    // (never the initial-render `null`), and `fetchBudgetGrid` responds
    // differently depending on whether a department filter was actually
    // sent, so a stale mount-time closure (HIGH-1) is observable: it would
    // call the endpoint with NO filter and admit the other ฝ่าย's row too.
    function mockTwoDeptGridForRevalidation() {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(twoDepartments)
      vi.mocked(budgetApi.fetchBudgetGrid).mockImplementation(({ department }) =>
        Promise.resolve(
          department === undefined
            ? [makeRow('CC1', '5211800030'), makeRow('CC2', '5211800030', { department: 'Warehouse' })]
            : [makeRow('CC1', '5211800030')],
        ),
      )
      vi.mocked(approvalApi.fetchLockedDepartments).mockResolvedValue({ departments: [], year_not_open: false })
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue({
        department: 'Solution Delivery', fiscal_year: 2027, status: 'PENDING_APPROVER1', submitter_empcode: null,
        submitter_email: null, submitted_at: null, approver1_empcode: null, approver1_actioned_at: null,
        approver2_actioned_at: null, approver3_actioned_at: null, reject_reason: null, rejected_by_empcode: null,
        updated_at: null, current_position: 1, current_approver_empcode: null, current_approver_name: null,
        can_act: false, notification_warning: null, is_post_deadline: false, can_submit: false,
        submit_blocked_reason: null, locked: true,
      })
    }

    it('a focus event that reveals the ฝ่าย just became locked reloads the grid using the CURRENT ฝ่าย, not the one from mount', async () => {
      mockTwoDeptGridForRevalidation()

      render(<BudgetGrid scope={twoDeptScope} initialFilter={{ dept: null, year: null }} />)

      // Auto-selects "Solution Delivery" (alphabetically first) — resolved
      // AFTER mount, once `GET /scope/departments` returns.
      expect(await screen.findByTestId('txn-CC1-5211800030')).toBeInTheDocument()
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1)

      fireEvent(window, new Event('focus'))

      await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledWith('Solution Delivery', 2027))
      await waitFor(() => expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(2))
      expect(budgetApi.fetchBudgetGrid).toHaveBeenLastCalledWith(expect.objectContaining({ department: 'Solution Delivery' }))
      // HIGH-1: a stale mount-time closure would have refetched with NO
      // department filter and admitted Warehouse's row too.
      expect(screen.queryByTestId('txn-CC2-5211800030')).not.toBeInTheDocument()
    })

    it('a visibilitychange event (tab becomes visible) that reveals the ฝ่าย just became locked reloads the grid using the CURRENT ฝ่าย', async () => {
      mockTwoDeptGridForRevalidation()

      render(<BudgetGrid scope={twoDeptScope} initialFilter={{ dept: null, year: null }} />)

      expect(await screen.findByTestId('txn-CC1-5211800030')).toBeInTheDocument()
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1)

      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
      fireEvent(document, new Event('visibilitychange'))

      await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledWith('Solution Delivery', 2027))
      await waitFor(() => expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(2))
      expect(budgetApi.fetchBudgetGrid).toHaveBeenLastCalledWith(expect.objectContaining({ department: 'Solution Delivery' }))
      expect(screen.queryByTestId('txn-CC2-5211800030')).not.toBeInTheDocument()
    })

    it('a focus event with no status change does NOT reload the grid', async () => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
      vi.mocked(approvalApi.fetchLockedDepartments).mockResolvedValue({ departments: [], year_not_open: false })
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue({
        department: 'Solution Delivery', fiscal_year: 2027, status: 'DRAFT', submitter_empcode: null,
        submitter_email: null, submitted_at: null, approver1_empcode: null, approver1_actioned_at: null,
        approver2_actioned_at: null, approver3_actioned_at: null, reject_reason: null, rejected_by_empcode: null,
        updated_at: null, current_position: null, current_approver_empcode: null, current_approver_name: null,
        can_act: false, notification_warning: null, is_post_deadline: false, can_submit: true,
        submit_blocked_reason: null, locked: false,
      })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: null }} />)

      await waitFor(() => expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument())
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1)

      fireEvent(window, new Event('focus'))

      await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledWith('Solution Delivery', 2027))
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1) // status agrees with lockedDepartments -> no reload
    })

    // Gate MED-1 (2026-09-17): admin-wide never locks (ADR-0012), but
    // `GET /approval/status` is caller-agnostic — without an early return, an
    // admin viewing any mid-approval/APPROVED ฝ่าย got a spurious mismatch
    // (nothing is ever in `lockedDepartments`, since that fetch short-
    // circuits empty for admin-wide) and a full reload on every single
    // focus/visibility event.
    it('an admin-wide view never revalidates lock status on focus (admin never locks)', async () => {
      const pureAdminScope: ScopeState = {
        ...SCOPE, isAdmin: true, role: 'admin', fillCostCenters: [], seeCostCenters: [],
      }
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue({
        department: 'Solution Delivery', fiscal_year: 2027, status: 'APPROVED', submitter_empcode: null,
        submitter_email: null, submitted_at: null, approver1_empcode: null, approver1_actioned_at: null,
        approver2_actioned_at: null, approver3_actioned_at: null, reject_reason: null, rejected_by_empcode: null,
        updated_at: null, current_position: null, current_approver_empcode: null, current_approver_name: null,
        can_act: false, notification_warning: null, is_post_deadline: false, can_submit: false,
        submit_blocked_reason: null, locked: true,
      })

      render(<BudgetGrid scope={pureAdminScope} initialFilter={{ dept: null, year: null }} />)

      await waitFor(() => expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument())
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1)
      // ApprovalActionBar (a sibling, unrelated to focus-revalidation) fetches
      // its own status once on mount -- settle on that baseline first so the
      // assertions below isolate what the FOCUS event itself triggers.
      await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(1))

      fireEvent(window, new Event('focus'))
      await Promise.resolve()

      // Admin-wide: the focus-revalidation path must add NO further call.
      expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(1)
      expect(budgetApi.fetchBudgetGrid).toHaveBeenCalledTimes(1)
    })

    // Gate follow-up item 2 (issue #13): `openSpecialForm`'s `readOnly` arg on
    // the Add-form path (`handleAddTransaction` -> `openSpecialForm(..,
    // selectedDepartmentLocked)`) had zero coverage. The button that reaches
    // it disables the instant the ฝ่าย is known-locked (see the button test
    // above) — but `AddTransactionForm`'s `open` state is local to that
    // component and does NOT reset when the ฝ่าย locks while the form is
    // already open (no `key` prop forces a remount here). Decision I's
    // focus-revalidation is exactly the route that can flip
    // `selectedDepartmentLocked` under an already-open form: read the code,
    // and this IS reachable, so it gets the honest assertion (read-only
    // subform), not a "button disabled" assertion.
    it('a special-GL pick from the Add form, submitted after the ฝ่าย locks WHILE the form was already open, opens its subform read-only', async () => {
      const SPECIAL_GL_REF = [
        { gl_code: '5211900030', gl_group: 'Entertainment', gl_name: 'Ent COST', is_special: true },
      ]
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(SPECIAL_GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])
      vi.mocked(approvalApi.fetchLockedDepartments)
        .mockResolvedValueOnce({ departments: [], year_not_open: false }) // mount: unlocked, Add button enabled
        .mockResolvedValueOnce({ departments: ['Solution Delivery'], year_not_open: false }) // after the lock is discovered
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue({
        department: 'Solution Delivery', fiscal_year: 2027, status: 'PENDING_APPROVER1', submitter_empcode: null,
        submitter_email: null, submitted_at: null, approver1_empcode: null, approver1_actioned_at: null,
        approver2_actioned_at: null, approver3_actioned_at: null, reject_reason: null, rejected_by_empcode: null,
        updated_at: null, current_position: 1, current_approver_empcode: null, current_approver_name: null,
        can_act: false, notification_warning: null, is_post_deadline: false, can_submit: false,
        submit_blocked_reason: null, locked: true,
      })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

      await waitFor(() => expect(screen.getByText(/ไม่มีรายการ/)).toBeInTheDocument())
      // Opens the form and picks the special GL WHILE the ฝ่าย is still
      // unlocked (the trigger button is enabled at this point).
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      fireEvent.focus(screen.getByLabelText('Cost Center'))
      fireEvent.click(screen.getByRole('option', { name: 'CC1' }))
      fireEvent.focus(screen.getByLabelText('GL Code'))
      fireEvent.click(screen.getByRole('option', { name: /5211900030/ }))

      // The ฝ่าย locks while the form is still open (decision I's focus revalidation).
      fireEvent(window, new Event('focus'))
      await waitFor(() => expect(approvalApi.fetchLockedDepartments).toHaveBeenCalledTimes(2))

      fireEvent.click(screen.getByRole('button', { name: 'บันทึก' }))

      expect(await screen.findByTestId('detail-subform')).toBeInTheDocument()
      expect(screen.getByText(/อ่านอย่างเดียว \(แก้ไม่ได้\)/)).toBeInTheDocument()
      expect(screen.queryByTestId('save-all')).not.toBeInTheDocument()
      expect(budgetApi.saveRow).not.toHaveBeenCalled()
    })
  })

  // Department-restricted GL groups (jakkaritw 2026-08-29) — the rule itself is
  // unit-tested in model.test.ts and AddTransactionForm.test.tsx; what only
  // exists here is the wiring, i.e. that BudgetGrid actually hands the picker
  // its `departments` (from GET /scope/departments) and the caller's isAdmin.
  describe('department-restricted GL wiring (departments + isAdmin -> AddTransactionForm)', () => {
    const SEMINAR_GL_REF = [
      ...GL_REF,
      { gl_code: '5210100150', gl_group: 'Training & Seminar', gl_name: 'ค่าอบรมและสัมมนา - ค่าธรรมเนียม', is_special: true, edit_by: 'user' as const },
    ]
    const TWO_DEPARTMENTS = [
      { cost_center: '10AC012000', department: 'Accounting', division: 'Finance Division', c_level: 'CFO' },
      { cost_center: '10HR012000', department: 'Talent & Culture', division: 'Corporate Affairs', c_level: 'CEO' },
    ]

    function mockGrid() {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(SEMINAR_GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(TWO_DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
      vi.mocked(approvalApi.fetchLockedDepartments).mockResolvedValue({ departments: [], year_not_open: false })
    }

    it('a filler gets the seminar GL only on the Talent & Culture cost center', async () => {
      const scope: ScopeState = {
        ...SCOPE, fillCostCenters: ['10AC012000', '10HR012000'], seeCostCenters: ['10AC012000', '10HR012000'],
      }
      mockGrid()

      render(<BudgetGrid scope={scope} initialFilter={{ dept: null, year: null }} />)

      // Auto-selects "Talent & Culture" (its division, 'Corporate Affairs',
      // sorts before 'Finance Division') — its own Cost Center gets the GL.
      fireEvent.click(await screen.findByRole('button', { name: /เพิ่ม transaction/i }))
      fireEvent.focus(screen.getByLabelText('Cost Center'))
      fireEvent.click(screen.getByRole('option', { name: '10HR012000' }))
      fireEvent.focus(screen.getByLabelText('GL Code'))
      expect(screen.getByRole('option', { name: /5210100150/ })).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }))

      // Issue #13, decision 1: switching to Accounting scopes the Add form
      // to ITS Cost Center — the seminar GL is withheld there instead.
      switchDepartment('Accounting')
      fireEvent.click(screen.getByRole('button', { name: /เพิ่ม transaction/i }))
      fireEvent.focus(screen.getByLabelText('Cost Center'))
      fireEvent.click(screen.getByRole('option', { name: '10AC012000' }))
      fireEvent.focus(screen.getByLabelText('GL Code'))
      expect(screen.queryByRole('option', { name: /5210100150/ })).not.toBeInTheDocument()
      expect(screen.getByRole('option', { name: /5211800030/ })).toBeInTheDocument()
    })

    // Issue #13, decision 1/G (2026-09-17): a `GET /scope/departments`
    // failure means the ฝ่าย on screen cannot be known either (both come
    // from the same fetch) — the Add button now disables ENTIRELY with its
    // own distinct reason, superseding the old inline "why is this GL
    // missing" message (unreachable now: the form can no longer even open).
    it('a failed /scope/departments disables Add with the distinct "ยังไม่ทราบฝ่าย" reason', async () => {
      const scope: ScopeState = { ...SCOPE, fillCostCenters: ['10HR012000'], seeCostCenters: ['10HR012000'] }
      mockGrid()
      vi.mocked(budgetApi.fetchDepartments).mockRejectedValue(new ApiError(502, 'เซิร์ฟเวอร์ขัดข้อง'))

      render(<BudgetGrid scope={scope} initialFilter={{ dept: null, year: null }} />)

      const trigger = await screen.findByRole('button', { name: /เพิ่ม transaction/i })
      await waitFor(() => expect(trigger).toBeDisabled())
      expect(screen.getByText(/ยังไม่ทราบฝ่าย/)).toBeInTheDocument()
    })

    it('an admin gets the seminar GL on a cost center outside Talent & Culture', async () => {
      const adminScope: ScopeState = {
        ...SCOPE, isAdmin: true, role: 'admin', fillCostCenters: ['10AC012000'], seeCostCenters: ['10AC012000'],
      }
      mockGrid()
      // This admin's OWN personal-view department list (admin_view_enabled
      // defaults off — the "โหมด Admin" hat is a deliberate, visible act) —
      // only their own Cost Center's ฝ่าย, same as any Filler would see.
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue([TWO_DEPARTMENTS[0]])

      render(<BudgetGrid scope={adminScope} initialFilter={{ dept: null, year: null }} />)

      fireEvent.click(await screen.findByRole('button', { name: /เพิ่ม transaction/i }))
      fireEvent.focus(screen.getByLabelText('Cost Center'))
      fireEvent.click(screen.getByRole('option', { name: '10AC012000' }))
      fireEvent.focus(screen.getByLabelText('GL Code'))
      expect(screen.getByRole('option', { name: /5210100150/ })).toBeInTheDocument()
    })
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

  it('spells out the 100-rounding rule under the legend (fillers must not be surprised by the silent round on commit)', async () => {
    vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
    vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
    vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])

    render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

    const note = await screen.findByTestId('pending-rounding-note')
    expect(note.textContent?.replace(/\s+/g, ' ')).toBe(
      'หมายเหตุ: กรอกได้ตั้งแต่ 100 ขึ้นไป โดยระบบจะปรับตัวเลข 2 หลักสุดท้ายเป็น 00 โดยอัตโนมัติ',
    )
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
        m01: 900, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
        total_year: 900, remark: null, template: 'USER', gl_name: null, gl_group: null, c_level: null, division: null, department: null,
        updated_at: '2026-01-02T00:00:00Z',
      })
      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)
      await enterFullscreen()

      const input = screen.getByTestId('pending-input-CC1-5211800030-m01')
      fireEvent.change(input, { target: { value: '900' } })
      fireEvent.blur(input)

      await waitFor(() =>
        expect(budgetApi.saveRow).toHaveBeenCalledWith(
          expect.objectContaining({ cost_center: 'CC1', gl_account: '5211800030', fiscal_year: 2027, m01: 900 }),
        ),
      )
    })
  })

  describe('SAP freshness chip (ADR-0030)', () => {
    beforeEach(() => {
      vi.mocked(budgetApi.fetchGlAccounts).mockResolvedValue(GL_REF)
      vi.mocked(budgetApi.fetchDepartments).mockResolvedValue(DEPARTMENTS)
      vi.mocked(budgetApi.fetchBudgetGrid).mockResolvedValue([])
    })

    it('healthy: shows the keyed-through date with no warning styling', async () => {
      vi.mocked(budgetApi.fetchSapCoverage).mockResolvedValue({
        fiscal_year: 2026, watermark_date: '2026-09-11', days_behind: 1, is_stale: false,
      })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

      const suffix = await screen.findByTestId('sap-freshness')
      expect(suffix).toHaveTextContent('ข้อมูลบันทึกถึงวันที่ 11 Sep 26')
      expect(suffix).not.toHaveTextContent('⚠')
      expect(suffix.className).not.toContain('sap-freshness-warn')
    })

    it('stale: warns on the chip when the server marks the feed stale', async () => {
      vi.mocked(budgetApi.fetchSapCoverage).mockResolvedValue({
        fiscal_year: 2026, watermark_date: '2026-09-11', days_behind: 3, is_stale: true,
      })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

      const suffix = await screen.findByTestId('sap-freshness')
      expect(suffix).toHaveTextContent('⚠ ข้อมูลบันทึกถึงวันที่ 11 Sep 26')
      expect(suffix.className).toContain('sap-freshness-warn')
    })

    it('unknown: warns with no date at all when nothing is loaded yet', async () => {
      // watermark_date: null -> the backend ALWAYS pairs this with is_stale:
      // true (app.sap.resolve_sap_coverage never reports an undeterminable
      // watermark as healthy) -- this fixture matches that contract.
      vi.mocked(budgetApi.fetchSapCoverage).mockResolvedValue({
        fiscal_year: 2026, watermark_date: null, days_behind: null, is_stale: true,
      })

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

      const suffix = await screen.findByTestId('sap-freshness')
      expect(suffix).toHaveTextContent('⚠ ไม่ทราบวันที่ข้อมูล')
      expect(suffix.className).toContain('sap-freshness-warn')
    })

    it('still loading: no suffix yet before the first fetch resolves (not a failure, just not answered yet)', async () => {
      let resolveFetch: (value: Awaited<ReturnType<typeof budgetApi.fetchSapCoverage>>) => void = () => {}
      vi.mocked(budgetApi.fetchSapCoverage).mockImplementation(
        () => new Promise((resolve) => { resolveFetch = resolve }),
      )

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

      await waitFor(() => expect(screen.getByTestId('status-legend')).toHaveTextContent('SAP · ใช้จริง'))
      expect(screen.queryByTestId('sap-freshness')).not.toBeInTheDocument()

      resolveFetch({ fiscal_year: 2026, watermark_date: '2026-09-11', days_behind: 1, is_stale: false })

      const suffix = await screen.findByTestId('sap-freshness')
      expect(suffix).toHaveTextContent('ข้อมูลบันทึกถึงวันที่ 11 Sep 26')
    })

    it('H1: a failed freshness fetch must WARN, never silently vanish (ADR-0030 §3.2 release-blocking chip)', async () => {
      vi.mocked(budgetApi.fetchSapCoverage).mockRejectedValue(new ApiError(502, 'เซิร์ฟเวอร์ขัดข้อง กรุณาลองใหม่อีกครั้ง'))

      render(<BudgetGrid scope={SCOPE} initialFilter={{ dept: null, year: 2027 }} />)

      const suffix = await screen.findByTestId('sap-freshness')
      expect(suffix).toHaveTextContent('⚠ ไม่ทราบวันที่ข้อมูล')
      expect(suffix.className).toContain('sap-freshness-warn')
    })
  })
})
