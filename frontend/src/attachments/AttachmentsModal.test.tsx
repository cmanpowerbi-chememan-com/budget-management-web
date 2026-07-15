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
})
