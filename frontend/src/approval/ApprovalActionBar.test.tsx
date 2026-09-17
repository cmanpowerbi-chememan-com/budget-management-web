import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as approvalApi from '../api/approval'
import { ApiError } from '../api/client'
import type { ApprovalStatusState } from '../api/types'
import { ApprovalActionBar } from './ApprovalActionBar'
import { REJECT_REASON_MAX_LEN } from './model'

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
    is_post_deadline: false,
    can_submit: true,
    submit_blocked_reason: null,
    locked: false,
    ...overrides,
  }
}

const BASE_PROPS = {
  department: 'Accounting',
  fiscalYear: 2027,
  dataVersion: 0,
  isFillerOfDept: true,
  adminViewEnabled: false,
  isAdmin: false,
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
    await waitFor(() => expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('Draft'))
  })

  // jakkaritw, 2026-09-17: the chip names the real approver in English
  // rather than a role/step label.
  it('names the current approver in English when the status carries a name', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER1', current_position: 1, current_approver_name: 'Laddawan Kearnoi' }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} />)
    await waitFor(() =>
      expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('Pending on Laddawan Kearnoi'),
    )
  })

  it('falls back to the step-number wording when the status carries no name', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER2', current_position: 2, current_approver_name: null }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} />)
    await waitFor(() => expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('Pending · Step 2'))
  })

  it('shows a loud error when the status fetch fails', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockRejectedValue(new ApiError(502, 'Server error'))
    render(<ApprovalActionBar {...BASE_PROPS} />)
    await waitFor(() => expect(screen.getByText('Server error')).toBeInTheDocument())
  })

  it('shows Submit for a Filler when status is DRAFT, and submits after confirm', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT' }))
    vi.mocked(approvalApi.submitDepartment).mockResolvedValue(state({ status: 'PENDING_APPROVER1', current_position: 1 }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApprovalActionBar {...BASE_PROPS} />)
    const submitBtn = await screen.findByTestId('approval-submit-btn')
    fireEvent.click(submitBtn)

    await waitFor(() => expect(approvalApi.submitDepartment).toHaveBeenCalledWith('Accounting', 2027))
    await waitFor(() => expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('Step 1'))
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
    await waitFor(() => expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('Approved'))
  })

  it('switches the chip to the next approver name immediately from the Approve response, with no extra status fetch', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: true, current_approver_name: 'Laddawan Kearnoi' }),
    )
    vi.mocked(approvalApi.approveDepartment).mockResolvedValue(
      state({ status: 'PENDING_APPROVER2', current_position: 2, current_approver_name: 'Nipaporn Tongking' }),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} />)
    fireEvent.click(await screen.findByTestId('approval-approve-btn'))

    await waitFor(() =>
      expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('Pending on Nipaporn Tongking'),
    )
    // The chip switched from the mocked action RESPONSE, not a refetch --
    // fetchApprovalStatus was only ever called once, on mount.
    expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(1)
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

  // 100-char reject-reason cap (jakkaritw, 2026-09-17, from UAT): the box
  // stops at 100 (browser's own maxLength) and a live counter shows the
  // room left. These 5 tests cover the user stories in prd.md at
  // .scratch/reject-reason-limit/ -- opens at 0/100, hard stop while typing,
  // hard stop on paste (same maxLength mechanism), and reset on cancel.
  describe('reject reason 100-character cap', () => {
    async function openRejectPanel() {
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
        state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: true }),
      )
      render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} />)
      fireEvent.click(await screen.findByTestId('approval-reject-btn'))
      return screen.getByTestId('approval-reject-reason-input') as HTMLTextAreaElement
    }

    it('opens with the counter at 0/100', async () => {
      await openRejectPanel()
      expect(screen.getByTestId('approval-reject-reason-counter')).toHaveTextContent(`0/${REJECT_REASON_MAX_LEN}`)
    })

    it('typing past the limit stops the box at 100 characters and the counter reads 100/100', async () => {
      const textarea = await openRejectPanel()
      const user = userEvent.setup()
      await user.type(textarea, 'a'.repeat(REJECT_REASON_MAX_LEN + 20))
      expect(textarea.value).toHaveLength(REJECT_REASON_MAX_LEN)
      expect(screen.getByTestId('approval-reject-reason-counter')).toHaveTextContent(`${REJECT_REASON_MAX_LEN}/${REJECT_REASON_MAX_LEN}`)
    })

    it('pasting past the limit keeps only the first 100 characters', async () => {
      const textarea = await openRejectPanel()
      const user = userEvent.setup()
      textarea.focus()
      await user.paste('b'.repeat(REJECT_REASON_MAX_LEN + 50))
      expect(textarea.value).toHaveLength(REJECT_REASON_MAX_LEN)
      expect(screen.getByTestId('approval-reject-reason-counter')).toHaveTextContent(`${REJECT_REASON_MAX_LEN}/${REJECT_REASON_MAX_LEN}`)
    })

    it('resets the counter to 0/100 on cancel then reopen', async () => {
      const textarea = await openRejectPanel()
      fireEvent.change(textarea, { target: { value: 'some reason' } })
      expect(screen.getByTestId('approval-reject-reason-counter')).toHaveTextContent('11/100')

      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
      fireEvent.click(screen.getByTestId('approval-reject-btn'))

      expect(screen.getByTestId('approval-reject-reason-input')).toHaveValue('')
      expect(screen.getByTestId('approval-reject-reason-counter')).toHaveTextContent(`0/${REJECT_REASON_MAX_LEN}`)
    })

    it('shows the Thai over-length sentence when the server 422s for a too-long reason', async () => {
      const textarea = await openRejectPanel()
      fireEvent.change(textarea, { target: { value: 'a valid reason' } })
      // Mirrors what apiFetch actually throws for a 422 (client.ts:281-284):
      // the translated Thai sentence lands on `.message`, `.detail` stays
      // undefined (the raw `detail` is an array, not a string).
      vi.mocked(approvalApi.rejectDepartment).mockRejectedValue(
        new ApiError(422, 'ข้อมูลไม่ถูกต้อง: reason — ยาวเกินกำหนด (ไม่เกิน 100 ตัวอักษร)'),
      )

      fireEvent.click(screen.getByTestId('approval-reject-confirm-btn'))

      await waitFor(() =>
        expect(screen.getByTestId('approval-action-message')).toHaveTextContent('ยาวเกินกำหนด (ไม่เกิน 100 ตัวอักษร)'),
      )
    })
  })

  it('shows the reject reason once the department is REJECTED', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'REJECTED', reject_reason: 'ยอดไม่ตรง' }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} />)
    await waitFor(() => expect(screen.getByTestId('approval-reject-reason')).toHaveTextContent('ยอดไม่ตรง'))
  })

  it('on a 409 conflict, shows an error message and refetches the status', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus)
      .mockResolvedValueOnce(state({ status: 'DRAFT' }))
      .mockResolvedValueOnce(state({ status: 'PENDING_APPROVER1', current_position: 1 }))
    vi.mocked(approvalApi.submitDepartment).mockRejectedValue(new ApiError(409, 'Conflict', 'concurrent'))
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApprovalActionBar {...BASE_PROPS} />)
    fireEvent.click(await screen.findByTestId('approval-submit-btn'))

    await waitFor(() => expect(screen.getByTestId('approval-action-message')).toHaveTextContent('Someone else'))
    await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(2))
  })

  it('on a 400 department_empty error, shows the server\'s own detail (bug 3, 2026-08-08 -- defense in depth for a stale can_submit=true, same describeApiError fallback every non-409 submit failure already uses)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT', can_submit: true }))
    vi.mocked(approvalApi.submitDepartment).mockRejectedValue(
      new ApiError(400, 'คำขอไม่ถูกต้อง', 'This department has no budget data yet, so it cannot be submitted.'),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApprovalActionBar {...BASE_PROPS} />)
    fireEvent.click(await screen.findByTestId('approval-submit-btn'))

    await waitFor(() =>
      expect(screen.getByTestId('approval-action-message')).toHaveTextContent('This department has no budget data yet, so it cannot be submitted.'),
    )
  })

  it('hides Approve/Reject in admin mode even when can_act is true (ADR-0014)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: true }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} adminViewEnabled />)
    await screen.findByTestId('approval-status-chip')
    expect(screen.queryByTestId('approval-approve-btn')).not.toBeInTheDocument()
  })

  it('hides Submit for admin on a locked status the server refuses -- shape (a), the SIT defect (2026-08-16 fix #2)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({
        status: 'PENDING_APPROVER1', current_position: 1,
        can_submit: false, submit_blocked_reason: 'admin_cannot_submit_in_cycle',
      }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isAdmin adminViewEnabled isFillerOfDept={false} />)
    await screen.findByTestId('approval-approve-btn') // ADR-0027 step-override still shows
    expect(screen.queryByTestId('approval-submit-btn')).not.toBeInTheDocument()
  })

  it('shows a short explanation next to the chip when the blocked admin hint applies (2026-08-16 fix #2)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({
        status: 'DRAFT', current_position: null,
        can_submit: false, submit_blocked_reason: 'admin_cannot_submit_in_cycle',
      }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isAdmin adminViewEnabled isFillerOfDept={false} />)
    await waitFor(() =>
      expect(screen.getByTestId('approval-submit-blocked-hint')).toHaveTextContent('normal approval cycle'),
    )
    expect(screen.queryByTestId('approval-submit-btn')).not.toBeInTheDocument()
  })

  it('shows Submit for admin on a locked status the server allows (post-deadline override door, shape (d))', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER1', current_position: 1, can_submit: true, submit_blocked_reason: null }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isAdmin adminViewEnabled isFillerOfDept={false} />)
    await waitFor(() => expect(screen.getByTestId('approval-submit-btn')).toBeInTheDocument())
    expect(screen.queryByTestId('approval-submit-blocked-hint')).not.toBeInTheDocument()
  })

  it('shows Submit for admin on DRAFT when the server allows it (never-submitted admin door, no regression)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT', can_submit: true }))
    render(<ApprovalActionBar {...BASE_PROPS} adminViewEnabled isFillerOfDept={false} />)
    await waitFor(() => expect(screen.getByTestId('approval-submit-btn')).toBeInTheDocument())
  })

  it('hides Submit for an admin viewer with the hat OFF even when the server would allow it', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT', can_submit: true }))
    render(<ApprovalActionBar {...BASE_PROPS} isAdmin adminViewEnabled={false} isFillerOfDept={false} />)
    await screen.findByTestId('approval-status-chip')
    expect(screen.queryByTestId('approval-submit-btn')).not.toBeInTheDocument()
  })

  it('hides Approve for a non-admin who is not the current approver', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: false }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} />)
    await screen.findByTestId('approval-status-chip')
    expect(screen.queryByTestId('approval-approve-btn')).not.toBeInTheDocument()
  })

  it('admin on PENDING_APPROVER1 with can_act=false sees the same Approve button, and the override confirm names the skipped approver (ADR-0027)', async () => {
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

    expect(confirmSpy).toHaveBeenCalledWith(
      '⚠️ You are approving on behalf of สมชาย ใจดี for department "Accounting", FY 2027',
    )
    await waitFor(() => expect(approvalApi.overrideStep).toHaveBeenCalledWith('Accounting', 2027))
    expect(approvalApi.approveDepartment).not.toHaveBeenCalled()
    expect(BASE_PROPS.onChanged).toHaveBeenCalled()
    await waitFor(() => expect(screen.getByTestId('approval-status-chip')).toHaveTextContent('Step 2'))
  })

  it('override confirm dialog falls back to a step-number wording when the server sends no approver name', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({
        status: 'PENDING_APPROVER1', current_position: 1, can_act: false,
        current_approver_empcode: '200', current_approver_name: null,
      }),
    )
    vi.mocked(approvalApi.overrideStep).mockResolvedValue(state({ status: 'PENDING_APPROVER2', current_position: 2 }))
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<ApprovalActionBar {...BASE_PROPS} isAdmin adminViewEnabled isFillerOfDept={false} />)
    fireEvent.click(await screen.findByTestId('approval-approve-btn'))

    expect(confirmSpy).toHaveBeenCalledWith(
      '⚠️ You are approving on behalf of Step 1 approver for department "Accounting", FY 2027',
    )
  })

  it('hides Approve for an admin on PENDING_APPROVER2 (positions 2/3 are never overridable, D4)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'PENDING_APPROVER2', current_position: 2, can_act: false }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isAdmin adminViewEnabled isFillerOfDept={false} />)
    await screen.findByTestId('approval-status-chip')
    expect(screen.queryByTestId('approval-approve-btn')).not.toBeInTheDocument()
  })

  // Filler-blocked-hint fix (2026-08-16, jakkaritw: "ใส่ข้อความให้ผู้กรอกด้วย"):
  // the hint used to be gated to admins only (`adminViewEnabled && !isFillerOfDept`)
  // -- a Filler who lost the button silently got no explanation at all.
  it('shows an explanation to a blocked Filler, not just to a blocked admin (jakkaritw 2026-08-16)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'DRAFT', can_submit: false, submit_blocked_reason: 'department_empty' }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept adminViewEnabled={false} />)
    await waitFor(() =>
      expect(screen.getByTestId('approval-submit-blocked-hint')).toHaveTextContent('This department has no budget data yet'),
    )
    expect(screen.queryByTestId('approval-submit-btn')).not.toBeInTheDocument()
  })

  it.each(['year_not_open', 'past_deadline'] as const)(
    'shows the filler-reachable %s reason as a hint next to the chip',
    async (reason) => {
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
        state({ status: 'DRAFT', can_submit: false, submit_blocked_reason: reason }),
      )
      render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept adminViewEnabled={false} />)
      await waitFor(() => expect(screen.getByTestId('approval-submit-blocked-hint')).toBeInTheDocument())
    },
  )

  it('does not duplicate the pending-lock message with the generic blocked hint (invalid_approval_state on PENDING_*, both would otherwise fire)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({
        status: 'PENDING_APPROVER1', current_position: 1,
        can_submit: false, submit_blocked_reason: 'invalid_approval_state',
      }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept adminViewEnabled={false} />)
    await screen.findByText('Submitted — locked for editing until it is rejected')
    expect(screen.queryByTestId('approval-submit-blocked-hint')).not.toBeInTheDocument()
  })

  // Issue #13 (2026-09-17): `isEditLocked` now covers APPROVED too (was
  // `isPendingLocked`, PENDING_* only) — the longest-lived locked state now
  // gets the same explicit note as a PENDING_* one, with wording that names
  // it as "Approved" rather than "Submitted".
  it('shows the APPROVED-worded locked note for a Filler on an APPROVED department, and suppresses the generic hint (dedup, same as PENDING_*)', async () => {
    vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
      state({ status: 'APPROVED', can_submit: false, submit_blocked_reason: 'invalid_approval_state' }),
    )
    render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept adminViewEnabled={false} />)
    await screen.findByText('Approved — locked for editing until it is rejected')
    expect(screen.queryByTestId('approval-submit-blocked-hint')).not.toBeInTheDocument()
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

  // Bug fix (2026-09-16): a Filler's first successful save on an empty
  // department flipped the server's can_submit/department_empty verdict,
  // but this component's status fetch used to key ONLY on
  // [department, fiscalYear] -- neither changes on a save, so Submit stayed
  // hidden until a manual reload. `dataVersion` is the parent's signal that
  // a write just succeeded.
  describe('dataVersion refetch (bug fix: Submit stuck hidden after the first save on an empty department)', () => {
    it('refetches the status when dataVersion changes, and shows Submit once the server answer flips to can_submit true', async () => {
      vi.mocked(approvalApi.fetchApprovalStatus)
        .mockResolvedValueOnce(state({ status: 'DRAFT', can_submit: false, submit_blocked_reason: 'department_empty' }))
        .mockResolvedValueOnce(state({ status: 'DRAFT', can_submit: true, submit_blocked_reason: null }))

      const { rerender } = render(<ApprovalActionBar {...BASE_PROPS} dataVersion={0} />)
      await screen.findByTestId('approval-submit-blocked-hint')
      expect(screen.queryByTestId('approval-submit-btn')).not.toBeInTheDocument()

      rerender(<ApprovalActionBar {...BASE_PROPS} dataVersion={1} />)

      await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(2))
      await waitFor(() => expect(screen.getByTestId('approval-submit-btn')).toBeInTheDocument())
    })

    // Gate finding (R1, 2026-09-16): once can_submit is already true, the
    // server's answer cannot change further this session (department_empty
    // is monotonic -- saving only ever adds rows), so re-asking on every
    // save was measured at ~a dozen DB round-trips per call, wasted.
    it('does not refetch when can_submit is already true -- the answer cannot change further (R1)', async () => {
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT', can_submit: true }))

      const { rerender } = render(<ApprovalActionBar {...BASE_PROPS} dataVersion={0} />)
      await screen.findByTestId('approval-submit-btn')
      expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(1)

      rerender(<ApprovalActionBar {...BASE_PROPS} dataVersion={1} />)

      await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(1))
    })

    it('does not refetch a second time on mount (dataVersion starts unchanged) -- exactly one GET per mount', async () => {
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT' }))
      render(<ApprovalActionBar {...BASE_PROPS} dataVersion={0} />)
      await screen.findByTestId('approval-status-chip')
      expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(1)
    })

    // can_submit: false (an approver's own view, not the filler) so R1's skip
    // does not apply here -- this pins the ORIGINAL guarantee (a genuine
    // in-place refetch must not clear actionMessage) on a fixture that still
    // reaches a real second fetchApprovalStatus call post-R1.
    it('a dataVersion refetch does not clear an action message the user is reading', async () => {
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
        state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: true, can_submit: false }),
      )
      vi.mocked(approvalApi.approveDepartment).mockRejectedValue(new ApiError(502, 'Approve failed', 'เซิร์ฟเวอร์ขัดข้อง'))
      vi.spyOn(window, 'confirm').mockReturnValue(true)

      const { rerender } = render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} dataVersion={0} />)
      const approveBtn = await screen.findByTestId('approval-approve-btn')
      fireEvent.click(approveBtn)
      await waitFor(() => expect(screen.getByTestId('approval-action-message')).toHaveTextContent('เซิร์ฟเวอร์ขัดข้อง'))

      rerender(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} dataVersion={1} />)

      // The message must survive a dataVersion-triggered refetch -- only a
      // department/fiscalYear change (the OTHER effect) is allowed to clear it.
      await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(2))
      expect(screen.getByTestId('approval-action-message')).toHaveTextContent('เซิร์ฟเวอร์ขัดข้อง')
    })

    // R2 (gate finding, 2026-09-16): a dataVersion-triggered refetch is a
    // background check, not a user-initiated load -- a transient failure
    // (502/offline) must leave the bar showing whatever it already had, not
    // blow it away into the full load-error panel.
    it('a dataVersion refetch that fails leaves the previous status on screen, not the load-error panel (R2)', async () => {
      vi.mocked(approvalApi.fetchApprovalStatus)
        .mockResolvedValueOnce(state({ status: 'DRAFT', can_submit: false, submit_blocked_reason: 'department_empty' }))
        .mockRejectedValueOnce(new ApiError(502, 'Server error'))

      const { rerender } = render(<ApprovalActionBar {...BASE_PROPS} dataVersion={0} />)
      await screen.findByTestId('approval-submit-blocked-hint')

      rerender(<ApprovalActionBar {...BASE_PROPS} dataVersion={1} />)

      await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(2))
      // Still the PREVIOUS status (blocked hint + chip) -- not the full-bar
      // load-error panel a plain load() failure would otherwise show.
      expect(screen.getByTestId('approval-submit-blocked-hint')).toBeInTheDocument()
      expect(screen.getByTestId('approval-status-chip')).toBeInTheDocument()
      expect(screen.queryByText('Server error')).not.toBeInTheDocument()
    })

    // can_submit: false (default would be true via the state() factory) so
    // R1's skip does not apply -- a genuine refetch must still not reset an
    // in-progress reject panel.
    it('a dataVersion refetch does not reset an in-progress reject panel', async () => {
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(
        state({ status: 'PENDING_APPROVER1', current_position: 1, can_act: true, can_submit: false }),
      )
      const { rerender } = render(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} dataVersion={0} />)
      fireEvent.click(await screen.findByTestId('approval-reject-btn'))
      const reasonInput = screen.getByTestId('approval-reject-reason-input')
      fireEvent.change(reasonInput, { target: { value: 'กำลังพิมพ์เหตุผล' } })

      rerender(<ApprovalActionBar {...BASE_PROPS} isFillerOfDept={false} dataVersion={1} />)

      await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledTimes(2))
      expect(screen.getByTestId('approval-reject-reason-input')).toHaveValue('กำลังพิมพ์เหตุผล')
    })

    it('changing department still performs the full reset (clears an action message), unlike a dataVersion bump', async () => {
      vi.mocked(approvalApi.fetchApprovalStatus).mockResolvedValue(state({ status: 'DRAFT', can_submit: true }))
      vi.mocked(approvalApi.submitDepartment).mockRejectedValue(new ApiError(502, 'Submit failed', 'เซิร์ฟเวอร์ขัดข้อง'))
      vi.spyOn(window, 'confirm').mockReturnValue(true)

      const { rerender } = render(<ApprovalActionBar {...BASE_PROPS} department="Accounting" dataVersion={0} />)
      const submitBtn = await screen.findByTestId('approval-submit-btn')
      fireEvent.click(submitBtn)
      await waitFor(() => expect(screen.getByTestId('approval-action-message')).toHaveTextContent('เซิร์ฟเวอร์ขัดข้อง'))

      rerender(<ApprovalActionBar {...BASE_PROPS} department="Finance" dataVersion={0} />)

      await waitFor(() => expect(approvalApi.fetchApprovalStatus).toHaveBeenCalledWith('Finance', 2027))
      expect(screen.queryByTestId('approval-action-message')).not.toBeInTheDocument()
    })

    // R2 counterpart: the department/fiscalYear effect always calls plain
    // load() (no keepStatusOnError) -- a failure there must still show the
    // full load-error panel exactly as before, unaffected by R2.
    it('a department-change load failure still shows the load-error panel (existing behavior, unaffected by R2)', async () => {
      vi.mocked(approvalApi.fetchApprovalStatus)
        .mockResolvedValueOnce(state({ status: 'DRAFT', can_submit: true }))
        .mockRejectedValueOnce(new ApiError(502, 'Server error'))

      const { rerender } = render(<ApprovalActionBar {...BASE_PROPS} department="Accounting" dataVersion={0} />)
      await screen.findByTestId('approval-submit-btn')

      rerender(<ApprovalActionBar {...BASE_PROPS} department="Finance" dataVersion={0} />)

      await waitFor(() => expect(screen.getByText('Server error')).toBeInTheDocument())
      expect(screen.queryByTestId('approval-submit-btn')).not.toBeInTheDocument()
    })
  })
})
