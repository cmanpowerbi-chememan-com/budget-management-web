import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as approvalApi from '../api/approval'
import { ApiError } from '../api/client'
import type { ApprovalStatusState } from '../api/types'
import { ApprovalActionBar } from './ApprovalActionBar'

vi.mock('../api/approval')

function state(overrides: Partial<ApprovalStatusState> = {}): ApprovalStatusState {
  return {
    department: 'Accounting',
    fiscal_year: 2027,
    status: 'DRAFT',
    submitter_empcode: null,
    submitter_email: null,
    submitted_at: null,
    approver1_empcode: null,
    approver1_actioned_at: null,
    approver2_actioned_at: null,
    approver3_actioned_at: null,
    reject_reason: null,
    rejected_by_empcode: null,
    updated_at: null,
    current_position: null,
    current_approver_empcode: null,
    current_approver_name: null,
    can_act: false,
    notification_warning: null,
    ...overrides,
  }
}

const BASE_PROPS = {
  department: 'Accounting',
  fiscalYear: 2027,
  isFillerOfDept: true,
  adminViewEnabled: false,
  isAdmin: false,
  rowCount: 5,
  costCenterCount: 2,
  onChanged: vi.fn(),
}

describe('ApprovalActionBar', () => {
  beforeEach(() => {
    vi.mocked(BASE_PROPS.onChanged).mockClear()
  })
  afterEach(() => {
    vi.resetAllMocks()
    vi.restoreAllMocks()
  })

  it('renders nothing when no department is selected', () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state())
    const { container } = render(<ApprovalActionBar {...BASE_PROPS} department={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('loads and shows the status chip', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT' }))
    render(<ApprovalActionBar {...BASE_PROPS} />)
    await waitFor(() => expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('แบบร่าง'))
  })

  it('shows a loud Thai error when the status fetch fails', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockRejectedValue(new ApiError(502, 'เซิร์ฟเวอร์ขัดข้อง'))
    render(<ApprovalActionBar {...BASE_PROPS} />)
    await waitFor(() => expect(screen.getByText('เซิร์ฟเวอร์ขัดข้อง')).toBeInTheDocument())
  })

  it('shows Submit for a Filler when status is DRAFT, and submits after confirm', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT' }))
    vi.mocked(approvalApi.submitDepartment).mockResolvedValue(state({ status: 'PENDING_APPROVER1', current_position: 1 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApprovalActionBar {...BASE_PROPS} />)
    const submitBtn = await screen.findByTestId('approval-submit-btn')
    fireEvent.click(submitBtn)

    await waitFor(() => expect(approvalApi.submitDepartment).toHaveBeenCalledWith('Accounting', 2027))
    await waitFor(() => expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('ขั้น 1'))
    expect(BASE_PROPS.onChanged).toHaveBeenCalled()
  })

  it('does not submit when the confirm dialog is cancelled', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT' }))
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    render(<ApprovalActionBar {...BASE_PROPS} />)
    const submitBtn = await screen.findByTestId('approval-submit-btn')
    fireEvent.click(submitBtn)

    expect(approvalApi.submitDepartment).not.toHaveBeenCalled()
  })

  it('hides Submit for a non-Filler, non-admin viewer', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT' }))
    render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} />)
    await screen.findByTestId('approval-status-chip')
    expect(screen.queryByTestId('approval-submit-btn')).not.toBeInTheDocument()
  })

  it('shows Approve/Reject when the caller is the current approver (can_act)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: true }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} />)
    await screen.findByTestId('approval-approve-btn')
    expect(screen.getByTestId('approval-reject-btn')).toBeInTheDocument()
  })

  it('approves after confirm and updates the chip', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER2', current_position: 2, can_act: true }),
    )
    vi.mocked(approvalApi.approveDepartment).mockResolvedValue(state({ status: 'APPROVED', current_position: null }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} />)
    const approveBtn = await screen.findByTestId('approval-approve-btn')
    fireEvent.click(approveBtn)

    await waitFor(() => expect(approvalApi.approveDepartment).toHaveBeenCalledWith('Accounting', 2027))
    await waitFor(() => expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('อนุมัติแล้ว'))
  })

  it('rejects with a required reason via the inline panel', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: true }),
    )
    vi.mocked(approvalApi.rejectDepartment).mockResolvedValue(
      state({ status: 'REJECTED', current_position: null, reject_reason: 'ตัวเลขผิด' }),
    )

    render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} />)
    fireEvent.click(await screen.findByTestId('approval-reject-btn'))

    const confirmBtn = screen.getByTestId('approval-reject-confirm-btn')
    expect(confirmBtn).toBeDisabled() // empty reason blocks confirm

    fireEvent.change(screen.getByTestId('approval-reject-reason-input'), { target: { value: 'ตัวเลขผิด' } })
    expect(confirmBtn).not.toBeDisabled()
    fireEvent.click(confirmBtn)

    await waitFor(() => expect(approvalApi.rejectDepartment).toHaveBeenCalledWith('Accounting', 2027, 'ตัวเลขผิด'))
    await waitFor(() => expect(screen.queryByTestId('approval-reject-panel')).not.toBeInTheDocument())
  })

  it('shows the reject reason once the department is REJECTED', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'REJECTED', reject_reason: 'ยอดไม่ตรง' }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} />)
    await waitFor(() => expect(screen.getByTestId('approval-reject-reason')).toHaveTextContent('ยอดไม่ตรง'))
  })

  it('on a 409 conflict, shows a Thai message and refetches the status', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus)
      .mockResolvedValueOnce(state({ status: 'DRAFT' }))
      .mockResolvedValueOnce(state({ status: 'PENDING_APPROVER1', current_position: 1 }))
    vi.mocked(approvalApi.submitDepartment).mockRejectedValue(new ApiError(409, 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น', 'concurrent'))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApprovalActionBar {...BASE_PROPS} />)
    fireEvent.click(await screen.findByTestId('approval-submit-btn'))

    await waitFor(() => expect(screen.getByTestId('approval-action-message')).toHaveTextContent('ผู้อื่น'))
    await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(2))
  })

  it('hides Approve/Reject in admin mode even when can_act is true (ADR-0014)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: true }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} adminViewEnabled />)
    await screen.findByTestId('approval-status-chip')
    expect(screen.queryByTestId('approval-approve-btn')).not.toBeInTheDocument()
  })

  it('shows Submit in admin mode regardless of status (server decides the branch)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'APPROVED' }))
    render(<ApprovalActionBar {...BASE_PROPS} adminViewEnabled isFillerOfDept={false} />)
    await waitFor(() => expect(screen.getByTestId('approval-submit-btn')).toBeInTheDocument())
  })

  it('hides อนุมัติ for a non-admin who is not the current approver', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: false }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} />)
    await screen.findByTestId('approval-status-chip')
    expect(screen.queryByTestId('approval-approve-btn')).not.toBeInTheDocument()
  })

  it('admin on PENDING_APPROVER1 with can_act=false sees the same อนุมัติ button, and the override confirm names the skipped approver (ADR-0027)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({
        status: 'PENDING_APPROVER1', current_position: 1, can_act: false,
        current_approver_empcode: '200', current_approver_name: 'สมชาย ใจดี',
      }),
    )
    vi.mocked(approvalApi.overrideStep).mockResolvedValue(
      state({ status: 'PENDING_APPROVER2', current_position: 2 }),
    )
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApprovalActionBar {...BASE_PROPS} isAdmin adminViewEnabled isFillerOfDept={false} />)
    fireEvent.click(await screen.findByTestId('approval-approve-btn'))

    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('สมชาย ใจดี'))
    await waitFor(() => expect(approvalApi.overrideStep).toHaveBeenCalledWith('Accounting', 2027))
    expect(approvalApi.approveDepartment).not.toHaveBeenCalled()
    expect(BASE_PROPS.onChanged).toHaveBeenCalled()
    await waitFor(() => expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('ขั้น 2'))
  })

  it('hides อนุมัติ for an admin on PENDING_APPROVER2 (positions 2/3 are never overridable, D4)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER2', current_position: 2, can_act: false }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isAdmin adminViewEnabled isFillerOfDept={false} />)
    await screen.findByTestId('approval-status-chip')
    expect(screen.queryByTestId('approval-approve-btn')).not.toBeInTheDocument()
  })

  it("on a 409 from override-step, shows the server's Thai detail as-is", async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: false }),
    )
    vi.mocked(approvalApi.overrideStep).mockRejectedValue(
      new ApiError(409, 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น', 'ไม่สามารถอนุมัติแทนได้ — ขั้นตอนนี้เป็นการพิจารณาของฝ่ายงบประมาณ'),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApprovalActionBar {...BASE_PROPS} isAdmin adminViewEnabled isFillerOfDept={false} />)
    fireEvent.click(await screen.findByTestId('approval-approve-btn'))

    await waitFor(() =>
      expect(screen.getByTestId('approval-action-message')).toHaveTextContent(
        'ไม่สามารถอนุมัติแทนได้ — ขั้นตอนนี้เป็นการพิจารณาของฝ่ายงบประมาณ',
      ),
    )
  })
})
