import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as attachmentsApi from '../api/attachments'
import { ApiError } from '../api/client'
import { AttachmentsModal } from './AttachmentsModal'

vi.mock('../api/attachments')

const ITEM = {
  item_id: 'item-1', name: 'budget.pdf', size: 2048,
  created_by: 'Somchai', created_at: '2027-01-01T00:00:00Z', web_url: 'https://x/budget.pdf',
}

describe('AttachmentsModal', () => {
  afterEach(() => {
    vi.resetAllMocks()
  })

  it('loads and lists attachments', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([ITEM])
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('budget.pdf')).toBeInTheDocument())
    expect(attachmentsApi.fetchAttachments).toHaveBeenCalledWith('Accounting', 2027)
  })

  it('shows an empty-state message when the folder has no files', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([])
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีไฟล์/)).toBeInTheDocument())
  })

  it('shows a loud Thai error when the folder is missing (never a silent empty list)', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockRejectedValue(
      new ApiError(502, 'เซิร์ฟเวอร์ขัดข้อง กรุณาลองใหม่อีกครั้ง', "the folder 'เอกสาร ฝ่าย/Orphan/2027' does not exist yet"),
    )
    render(<AttachmentsModal department="Orphan" fiscalYear={2027} canUpload onClose={vi.fn()} />)

    await waitFor(() => expect(screen.getByText(/does not exist yet/)).toBeInTheDocument())
  })

  it('hides the upload control when the caller cannot upload', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([])
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีไฟล์/)).toBeInTheDocument())
    expect(screen.queryByTestId('attachments-upload-input')).not.toBeInTheDocument()
  })

  it('uploads a picked file and refreshes the list', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValueOnce([]).mockResolvedValueOnce([ITEM])
    vi.mocked(attachmentsApi.uploadAttachment).mockResolvedValue(ITEM)
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีไฟล์/)).toBeInTheDocument())

    const file = new File(['abc'], 'report.pdf', { type: 'application/pdf' })
    const input = screen.getByTestId('attachments-upload-input')
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => expect(attachmentsApi.uploadAttachment).toHaveBeenCalledWith('Accounting', 2027, file))
    await waitFor(() => expect(screen.getByText('budget.pdf')).toBeInTheDocument())
  })

  it('shows a Thai error when upload fails (e.g. disallowed file type)', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([])
    vi.mocked(attachmentsApi.uploadAttachment).mockRejectedValue(
      new ApiError(400, 'คำขอไม่ถูกต้อง', "file type '.exe' is not allowed"),
    )
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีไฟล์/)).toBeInTheDocument())

    const file = new File(['abc'], 'malware.exe', { type: 'application/octet-stream' })
    fireEvent.change(screen.getByTestId('attachments-upload-input'), { target: { files: [file] } })

    await waitFor(() => expect(screen.getByTestId('attachments-action-error')).toHaveTextContent('.exe'))
  })

  it('shows the backend Thai message alone for a 413 (file too large), no "(HTTP 413)" prefix', async () => {
    const tooLarge = 'ไฟล์ใหญ่เกินกำหนด (15 MB) — อัปโหลดได้ไม่เกิน 10 MB'
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([])
    vi.mocked(attachmentsApi.uploadAttachment).mockRejectedValue(new ApiError(413, tooLarge, tooLarge))
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีไฟล์/)).toBeInTheDocument())

    const file = new File(['a'.repeat(20)], 'big.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByTestId('attachments-upload-input'), { target: { files: [file] } })

    await waitFor(() => expect(screen.getByTestId('attachments-action-error')).toHaveTextContent(tooLarge))
    expect(screen.getByTestId('attachments-action-error').textContent).toBe(tooLarge)
    expect(screen.getByTestId('attachments-action-error').textContent).not.toContain('HTTP 413')
  })

  it('downloads a file by opening the resolved Graph URL', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([ITEM])
    vi.mocked(attachmentsApi.fetchDownloadUrl).mockResolvedValue('https://download.example/x')
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)

    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('budget.pdf')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /เปิด\/ดาวน์โหลด/ }))

    await waitFor(() => expect(attachmentsApi.fetchDownloadUrl).toHaveBeenCalledWith('Accounting', 2027, 'item-1'))
    await waitFor(() => expect(openSpy).toHaveBeenCalledWith('https://download.example/x', '_blank', 'noopener,noreferrer'))
  })

  it('calls onClose when the close button is clicked', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([])
    const onClose = vi.fn()
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={onClose} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีไฟล์/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'ปิด' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('deletes a file after the user confirms, then reloads the list', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValueOnce([ITEM]).mockResolvedValueOnce([])
    vi.mocked(attachmentsApi.deleteAttachment).mockResolvedValue('budget.pdf')
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('budget.pdf')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('attachments-delete-item-1'))

    await waitFor(() => expect(screen.getByText(/ยังไม่มีไฟล์/)).toBeInTheDocument())
    expect(confirmSpy).toHaveBeenCalledWith('ลบไฟล์ "budget.pdf" ออกจากโฟลเดอร์นี้?')
    expect(attachmentsApi.deleteAttachment).toHaveBeenCalledWith('Accounting', 2027, 'item-1')
    confirmSpy.mockRestore()
  })

  it('does not delete anything when the user cancels the confirm', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([ITEM])
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('budget.pdf')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('attachments-delete-item-1'))

    expect(attachmentsApi.deleteAttachment).not.toHaveBeenCalled()
    expect(screen.getByText('budget.pdf')).toBeInTheDocument()
    confirmSpy.mockRestore()
  })

  it('hides the delete button from a caller who cannot upload (See-only reviewer)', async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([ITEM])
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload={false} onClose={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('budget.pdf')).toBeInTheDocument())
    expect(screen.queryByTestId('attachments-delete-item-1')).not.toBeInTheDocument()
    expect(screen.getByText('เปิด/ดาวน์โหลด')).toBeInTheDocument()
  })

  it("shows the server's Thai reason when a delete fails", async () => {
    vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([ITEM])
    vi.mocked(attachmentsApi.deleteAttachment).mockRejectedValue(
      new ApiError(404, 'ไม่พบข้อมูล', 'ไม่พบไฟล์นี้ในเอกสารของฝ่าย Accounting ปี 2027'),
    )
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('budget.pdf')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('attachments-delete-item-1'))

    await waitFor(() =>
      expect(screen.getByTestId('attachments-action-error').textContent).toContain(
        'ไม่พบไฟล์นี้ในเอกสารของฝ่าย Accounting ปี 2027',
      ),
    )
    confirmSpy.mockRestore()
  })

  // BUG FIX (jakkaritw, prd report 2026-09-24): pressing the mouse inside the
  // modal and releasing over the dim backdrop used to fire a native `click`
  // on the backdrop itself — the browser's common-ancestor rule for a
  // cross-element press/release — which the old `e.target === e.currentTarget`
  // check couldn't tell apart from a real backdrop click, silently closing
  // the modal. Fixed by `useBackdropDismiss` (src/platform/backdropDismiss.ts),
  // which only dismisses when the PRESS and the RELEASE both land on the
  // backdrop itself.
  describe('backdrop drag-release guard (bug fix 2026-09-24)', () => {
    function backdrop(): HTMLElement {
      const el = document.querySelector('.modal-backdrop')
      if (!el) throw new Error('modal-backdrop not found')
      return el as HTMLElement
    }

    it('a press that starts inside the modal and a click that lands on the backdrop (drag-release) does not close it', async () => {
      vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([])
      const onClose = vi.fn()
      render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={onClose} />)
      await waitFor(() => expect(screen.getByText(/ยังไม่มีไฟล์/)).toBeInTheDocument())

      fireEvent.mouseDown(screen.getByTestId('attachments-modal'))
      fireEvent.mouseUp(backdrop())
      fireEvent.click(backdrop())

      expect(onClose).not.toHaveBeenCalled()
      expect(screen.getByTestId('attachments-modal')).toBeInTheDocument()
    })

    it('a press and click that both land on the backdrop close it (clean backdrop click still works)', async () => {
      vi.mocked(attachmentsApi.fetchAttachments).mockResolvedValue([])
      const onClose = vi.fn()
      render(<AttachmentsModal department="Accounting" fiscalYear={2027} canUpload onClose={onClose} />)
      await waitFor(() => expect(screen.getByText(/ยังไม่มีไฟล์/)).toBeInTheDocument())

      fireEvent.mouseDown(backdrop())
      fireEvent.mouseUp(backdrop())
      fireEvent.click(backdrop())

      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })
})
