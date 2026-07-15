import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import * as subformApi from '../api/subform'
import type { DetailLineState } from '../api/types'
import { DetailSubform } from './DetailSubform'

vi.mock('../api/subform')

function blankLine(overrides: Partial<DetailLineState> = {}): DetailLineState {
  const months = Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`m${String(i + 1).padStart(2, '0')}`, 0]))
  return {
    detail_id: 1,
    cost_center: 'CC1',
    gl_account: '5211900030',
    fiscal_year: 2027,
    trip_id: null,
    gl_group: 'Entertainment',
    line_label: null,
    ...months,
    total_year: 0,
    meta_json: null,
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  } as DetailLineState
}

describe('DetailSubform', () => {
  afterEach(() => vi.resetAllMocks())

  it('shows a loading state then the existing lines', async () => {
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([blankLine()])
    render(
      <DetailSubform
        costCenter="CC1"
        glAccount="5211900030"
        glGroup="Entertainment"
        glName="ค่าเลี้ยงรับรองภายนอก"
        fiscalYear={2027}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    expect(screen.getByText(/กำลังโหลด/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())
  })

  it('shows an empty state with no lines and an "+ เพิ่มรายการ" affordance', async () => {
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])
    render(
      <DetailSubform
        costCenter="CC1"
        glAccount="5211900030"
        glGroup="Entertainment"
        glName={null}
        fiscalYear={2027}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    await waitFor(() => expect(screen.getByText(/ยังไม่มีรายการ/)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /เพิ่มรายการ/ })).toBeInTheDocument()
  })

  it('shows an error state with retry on fetch failure', async () => {
    vi.mocked(subformApi.fetchDetailLines)
      .mockRejectedValueOnce(new ApiError(502, 'เซิร์ฟเวอร์ขัดข้อง'))
      .mockResolvedValueOnce([])
    render(
      <DetailSubform
        costCenter="CC1"
        glAccount="5211900030"
        glGroup="Entertainment"
        glName={null}
        fiscalYear={2027}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    await waitFor(() => expect(screen.getByText('เซิร์ฟเวอร์ขัดข้อง')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'ลองใหม่' }))
    await waitFor(() => expect(screen.getByText(/ยังไม่มีรายการ/)).toBeInTheDocument())
  })

  it('Entertainment external GL offers the 4-option dropdown', async () => {
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([blankLine()])
    render(
      <DetailSubform
        costCenter="CC1"
        glAccount="5211900030"
        glGroup="Entertainment"
        glName={null}
        fiscalYear={2027}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())
    const select = screen.getByLabelText('ประเภทการรับรอง') as HTMLSelectElement
    expect(Array.from(select.options).map((o) => o.value)).toContain('หน่วยงานราชการ')
  })

  it('Lease & Rental non-vehicle GL greys out ประเภทรถ/ทะเบียนรถ', async () => {
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([
      blankLine({ gl_account: '6211200020', gl_group: 'Lease & Rental' }),
    ])
    render(
      <DetailSubform
        costCenter="CC1"
        glAccount="6211200020"
        glGroup="Lease & Rental"
        glName={null}
        fiscalYear={2027}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())
    expect(screen.queryByLabelText('ประเภทรถ')).not.toBeInTheDocument()
    expect(screen.getByLabelText('สถานที่ใช้งาน')).toBeInTheDocument()
  })

  it('adds a blank row, fills it, saves it, and calls onSaved', async () => {
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])
    vi.mocked(subformApi.saveDetailLine).mockResolvedValue(blankLine({ detail_id: 99, meta_json: { รายละเอียด: 'lunch' } }))
    const onSaved = vi.fn()
    render(
      <DetailSubform
        costCenter="CC1"
        glAccount="5211900030"
        glGroup="Entertainment"
        glName={null}
        fiscalYear={2027}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )
    await waitFor(() => expect(screen.getByText(/ยังไม่มีรายการ/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มรายการ/ }))
    fireEvent.change(screen.getByLabelText('รายละเอียด'), { target: { value: 'lunch' } })
    fireEvent.click(screen.getByTestId('save-row-new-0'))

    await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
    const payload = vi.mocked(subformApi.saveDetailLine).mock.calls[0][0]
    expect(payload.detail_id).toBeNull()
    expect(payload.meta_json).toEqual({ รายละเอียด: 'lunch' })
    expect(onSaved).toHaveBeenCalled()
  })

  it('a 409 conflict refetches the lines instead of leaving a stale draft', async () => {
    vi.mocked(subformApi.fetchDetailLines)
      .mockResolvedValueOnce([blankLine()])
      .mockResolvedValueOnce([blankLine({ total_year: 500 })])
    vi.mocked(subformApi.saveDetailLine).mockRejectedValue(new ApiError(409, 'ถูกแก้ไขโดยผู้อื่น'))

    render(
      <DetailSubform
        costCenter="CC1"
        glAccount="5211900030"
        glGroup="Entertainment"
        glName={null}
        fiscalYear={2027}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    )
    await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('save-row-existing-1'))

    await waitFor(() => expect(subformApi.fetchDetailLines).toHaveBeenCalledTimes(2))
  })

  describe('delete', () => {
    beforeEach(() => {
      vi.spyOn(window, 'confirm').mockReturnValue(true)
    })
    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('confirms in Thai, calls deleteDetailLine with the row lock token, removes the row, and calls onSaved', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([blankLine({ updated_at: '2026-02-01T00:00:00' })])
      vi.mocked(subformApi.deleteDetailLine).mockResolvedValue({ ok: true })
      const onSaved = vi.fn()
      render(
        <DetailSubform
          costCenter="CC1"
          glAccount="5211900030"
          glGroup="Entertainment"
          glName={null}
          fiscalYear={2027}
          onClose={vi.fn()}
          onSaved={onSaved}
        />,
      )
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: 'ลบรายการ' }))

      expect(window.confirm).toHaveBeenCalledWith('ลบรายการนี้?')
      await waitFor(() => expect(subformApi.deleteDetailLine).toHaveBeenCalledWith(1, '2026-02-01T00:00:00'))
      await waitFor(() => expect(screen.queryByTestId('detail-row-existing-1')).not.toBeInTheDocument())
      expect(onSaved).toHaveBeenCalled()
    })

    it('does nothing when the user cancels the confirm dialog', async () => {
      vi.mocked(window.confirm).mockReturnValue(false)
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([blankLine()])
      render(
        <DetailSubform
          costCenter="CC1"
          glAccount="5211900030"
          glGroup="Entertainment"
          glName={null}
          fiscalYear={2027}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />,
      )
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: 'ลบรายการ' }))

      expect(subformApi.deleteDetailLine).not.toHaveBeenCalled()
      expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument()
    })

    it('a 409 conflict on delete refetches the lines and shows a Thai message', async () => {
      vi.mocked(subformApi.fetchDetailLines)
        .mockResolvedValueOnce([blankLine()])
        .mockResolvedValueOnce([blankLine({ total_year: 500 })])
      vi.mocked(subformApi.deleteDetailLine).mockRejectedValue(new ApiError(409, 'ถูกแก้ไขโดยผู้อื่น'))
      render(
        <DetailSubform
          costCenter="CC1"
          glAccount="5211900030"
          glGroup="Entertainment"
          glName={null}
          fiscalYear={2027}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />,
      )
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: 'ลบรายการ' }))

      await waitFor(() => expect(subformApi.fetchDetailLines).toHaveBeenCalledTimes(2))
      expect(screen.getByText(/ถูกแก้ไขหรือถูกลบโดยผู้อื่น/)).toBeInTheDocument()
    })

    it('removes an unsaved (never-persisted) row locally without calling the API or confirming', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])
      render(
        <DetailSubform
          costCenter="CC1"
          glAccount="5211900030"
          glGroup="Entertainment"
          glName={null}
          fiscalYear={2027}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />,
      )
      await waitFor(() => expect(screen.getByText(/ยังไม่มีรายการ/)).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มรายการ/ }))
      expect(screen.getByTestId('detail-row-new-0')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'ลบรายการ' }))

      expect(window.confirm).not.toHaveBeenCalled()
      expect(subformApi.deleteDetailLine).not.toHaveBeenCalled()
      expect(screen.queryByTestId('detail-row-new-0')).not.toBeInTheDocument()
    })
  })

  it('calls onClose when the close button is clicked', async () => {
    vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])
    const onClose = vi.fn()
    render(
      <DetailSubform
        costCenter="CC1"
        glAccount="5211900030"
        glGroup="Entertainment"
        glName={null}
        fiscalYear={2027}
        onClose={onClose}
        onSaved={vi.fn()}
      />,
    )
    await waitFor(() => expect(screen.getByText(/ยังไม่มีรายการ/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'ปิด' }))
    expect(onClose).toHaveBeenCalled()
  })
})
