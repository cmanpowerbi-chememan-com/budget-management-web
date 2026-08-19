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

  // FIX #2 — a click on "+ เพิ่มรายการ" DURING the initial load used to be
  // silently lost: load()'s setRows(...) replaces the array, discarding the
  // just-added blank row. The button must be disabled until the data lands.
  it('disables "+ เพิ่มรายการ" while the initial load is in-flight, then a post-load click adds a row that survives', async () => {
    let resolveLoad!: (lines: DetailLineState[]) => void
    vi.mocked(subformApi.fetchDetailLines).mockImplementation(
      () =>
        new Promise<DetailLineState[]>((resolve) => {
          resolveLoad = resolve
        }),
    )
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
    const addBtn = screen.getByRole('button', { name: /เพิ่มรายการ/ })
    expect(addBtn).toBeDisabled()

    resolveLoad([])
    await waitFor(() => expect(addBtn).toBeEnabled())

    fireEvent.click(addBtn)
    expect(screen.getByTestId('detail-row-new-0')).toBeInTheDocument()
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

  describe('Entertainment ประเภทการรับรอง — required dropdown blocks a blank save (bug-entertainment-blank-type-400)', () => {
    it('leaving ประเภทการรับรอง on "— เลือก —" blocks the save with a Thai message and calls the API zero times', async () => {
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
      fireEvent.change(screen.getByLabelText('รายละเอียด'), { target: { value: 'lunch with client' } })

      fireEvent.click(screen.getByTestId('save-all'))

      await waitFor(() => expect(screen.getByText('กรุณาเลือกประเภทการรับรอง')).toBeInTheDocument())
      expect(subformApi.saveDetailLine).not.toHaveBeenCalled()
    })

    it('picking a value unblocks the save and the payload carries it', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([blankLine()])
      vi.mocked(subformApi.saveDetailLine).mockResolvedValue(blankLine({ meta_json: { ประเภทการรับรอง: 'Customer' } }))
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

      fireEvent.change(screen.getByLabelText('ประเภทการรับรอง'), { target: { value: 'Customer' } })
      fireEvent.click(screen.getByTestId('save-all'))

      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
      expect(vi.mocked(subformApi.saveDetailLine).mock.calls[0][0].meta_json?.ประเภทการรับรอง).toBe('Customer')
    })
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
    vi.mocked(subformApi.saveDetailLine).mockResolvedValue(
      blankLine({ detail_id: 99, meta_json: { ประเภทการรับรอง: 'Customer', รายละเอียด: 'lunch' } }),
    )
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
    fireEvent.change(screen.getByLabelText('ประเภทการรับรอง'), { target: { value: 'Customer' } })
    fireEvent.change(screen.getByLabelText('รายละเอียด'), { target: { value: 'lunch' } })
    fireEvent.click(screen.getByTestId('save-all'))

    await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
    const payload = vi.mocked(subformApi.saveDetailLine).mock.calls[0][0]
    expect(payload.detail_id).toBeNull()
    expect(payload.meta_json).toEqual({ ประเภทการรับรอง: 'Customer', รายละเอียด: 'lunch' })
    expect(onSaved).toHaveBeenCalled()
  })

  // bug-subform-no-decimals (2026-08-19): the month input used to do
  // Number(e.target.value.replace(/[^0-9]/g, '')) on every keystroke, which
  // stripped the decimal point AND coerced immediately — "51000.50" became
  // 5100050 mid-typing. Fixed via the shared `MonthAmountInput` (same
  // draft-string-then-commit shape as grid/MonthCell.tsx).
  describe('month amount input — decimal precision (bug-subform-no-decimals)', () => {
    it('typing a decimal keeps the fraction and the SAVED payload carries it exactly', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([blankLine()])
      vi.mocked(subformApi.saveDetailLine).mockResolvedValue(blankLine({ m01: 51000.5, total_year: 51000.5 }))
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

      const input = screen.getByLabelText('m01 existing-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '51000.50' } })
      expect(input.value).toBe('51000.50')
      fireEvent.blur(input)

      fireEvent.change(screen.getByLabelText('ประเภทการรับรอง'), { target: { value: 'Customer' } })
      fireEvent.click(screen.getByTestId('save-all'))

      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
      expect(vi.mocked(subformApi.saveDetailLine).mock.calls[0][0].m01).toBe(51000.5)
    })

    it('a partially typed decimal ("51000.") is not destroyed mid-typing', async () => {
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

      const input = screen.getByLabelText('m01 existing-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '51000.' } })
      expect(input.value).toBe('51000.')
    })

    it('sanitizes multi-dot / letters / minus while typing (1.2.3 -> 1.23)', async () => {
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

      const input = screen.getByLabelText('m01 existing-1') as HTMLInputElement
      fireEvent.change(input, { target: { value: '1.2.3' } })
      expect(input.value).toBe('1.23')
      fireEvent.change(input, { target: { value: '-45a6' } })
      expect(input.value).toBe('456')
    })

    it('the draft re-syncs to the refetched value after a save conflict (same detail_id -> same component instance reused)', async () => {
      vi.mocked(subformApi.fetchDetailLines)
        .mockResolvedValueOnce([blankLine({ m01: 100, total_year: 100 })])
        .mockResolvedValueOnce([blankLine({ m01: 999.25, total_year: 999.25 })])
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

      const input = screen.getByLabelText('m01 existing-1') as HTMLInputElement
      expect(input.value).toBe('100')
      fireEvent.change(input, { target: { value: '250.75' } }) // uncommitted, never blurred
      expect(input.value).toBe('250.75')

      fireEvent.change(screen.getByLabelText('ประเภทการรับรอง'), { target: { value: 'Customer' } })
      fireEvent.click(screen.getByTestId('save-all'))

      await waitFor(() => expect(subformApi.fetchDetailLines).toHaveBeenCalledTimes(2))
      await waitFor(() => expect(screen.getByLabelText('m01 existing-1')).toHaveValue('999.25'))
    })
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
    fireEvent.change(screen.getByLabelText('ประเภทการรับรอง'), { target: { value: 'Customer' } })
    fireEvent.click(screen.getByTestId('save-all'))

    await waitFor(() => expect(subformApi.fetchDetailLines).toHaveBeenCalledTimes(2))
  })

  describe('save-all footer button (mockup #detailModal — one บันทึก per modal)', () => {
    function renderTwoRows(onClose = vi.fn(), onSaved = vi.fn()) {
      render(
        <DetailSubform
          costCenter="CC1"
          glAccount="5211900030"
          glGroup="Entertainment"
          glName={null}
          fiscalYear={2027}
          onClose={onClose}
          onSaved={onSaved}
        />,
      )
      return { onClose, onSaved }
    }

    it('one click saves EVERY row, then closes the modal on full success', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([blankLine({ detail_id: 1 }), blankLine({ detail_id: 2 })])
      vi.mocked(subformApi.saveDetailLine)
        .mockResolvedValueOnce(blankLine({ detail_id: 1 }))
        .mockResolvedValueOnce(blankLine({ detail_id: 2 }))
      const onClose = vi.fn()
      const onSaved = vi.fn()
      renderTwoRows(onClose, onSaved)
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-2')).toBeInTheDocument())
      for (const select of screen.getAllByLabelText('ประเภทการรับรอง')) {
        fireEvent.change(select, { target: { value: 'Customer' } })
      }

      fireEvent.click(screen.getByTestId('save-all'))

      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalledTimes(2))
      expect(onSaved).toHaveBeenCalledTimes(1)
      await waitFor(() => expect(onClose).toHaveBeenCalled())
    })

    it('a failed row never blocks the rest — modal stays open with that row marked', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([blankLine({ detail_id: 1 }), blankLine({ detail_id: 2 })])
      vi.mocked(subformApi.saveDetailLine)
        .mockRejectedValueOnce(new ApiError(500, 'เซิร์ฟเวอร์ขัดข้อง'))
        .mockResolvedValueOnce(blankLine({ detail_id: 2 }))
      const onClose = vi.fn()
      const onSaved = vi.fn()
      renderTwoRows(onClose, onSaved)
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-2')).toBeInTheDocument())
      for (const select of screen.getAllByLabelText('ประเภทการรับรอง')) {
        fireEvent.change(select, { target: { value: 'Customer' } })
      }

      fireEvent.click(screen.getByTestId('save-all'))

      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalledTimes(2))
      await waitFor(() => expect(screen.getByTestId('detail-row-error-existing-1')).toBeInTheDocument())
      expect(screen.getByText('เซิร์ฟเวอร์ขัดข้อง')).toBeInTheDocument()
      expect(onSaved).toHaveBeenCalledTimes(1) // row 2 still saved
      expect(onClose).not.toHaveBeenCalled()
    })

    it('renders JAN-labelled month columns, a Monthly total row, and Rows/Year-total footer', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([blankLine({ m01: 5000, m02: 250, total_year: 5250 })])
      renderTwoRows()
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      expect(screen.getByText('Jan')).toBeInTheDocument()
      expect(screen.getByText('Dec')).toBeInTheDocument()
      expect(screen.getByText('Monthly total')).toBeInTheDocument()
      expect(screen.getByText('5,000.00')).toBeInTheDocument() // m01 column total
      expect(screen.getByText('฿5,250.00')).toBeInTheDocument() // footer year total
      expect(screen.getByText(/Rows:/)).toBeInTheDocument()
    })
  })

  describe('Lease & Rental vehicle plate — อื่นๆ reveals a required free-text plate (2026-07-17)', () => {
    const VEHICLE_GL = '5211200060'

    function vehicleLine(overrides: Partial<DetailLineState> = {}): DetailLineState {
      return blankLine({ gl_account: VEHICLE_GL, gl_group: 'Lease & Rental', ...overrides })
    }

    function renderVehicle() {
      render(
        <DetailSubform
          costCenter="CC1"
          glAccount={VEHICLE_GL}
          glGroup="Lease & Rental"
          glName={null}
          fiscalYear={2027}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />,
      )
    }

    it('a listed plate is sent as-is and shows no free-text input', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([vehicleLine()])
      vi.mocked(subformApi.saveDetailLine).mockResolvedValue(
        vehicleLine({ meta_json: { ทะเบียนรถ: '6ขผ-3918', สถานที่ใช้งาน: 'BK' } }),
      )
      renderVehicle()
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      fireEvent.change(screen.getByLabelText('ทะเบียนรถ'), { target: { value: '6ขผ-3918' } })
      expect(screen.queryByPlaceholderText('พิมพ์ทะเบียนรถ')).not.toBeInTheDocument()
      // สถานที่ใช้งาน is a required field (bug-lease-blank-dropdown-400) — pick
      // one so this test isolates the plate behaviour it's actually about.
      fireEvent.change(screen.getByLabelText('สถานที่ใช้งาน'), { target: { value: 'BK' } })

      fireEvent.click(screen.getByTestId('save-all'))
      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
      expect(vi.mocked(subformApi.saveDetailLine).mock.calls[0][0].meta_json?.ทะเบียนรถ).toBe('6ขผ-3918')
    })

    it('picking อื่นๆ reveals a REQUIRED free-text plate input — saving while blank is blocked, no API call', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([vehicleLine()])
      renderVehicle()
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      fireEvent.change(screen.getByLabelText('ทะเบียนรถ'), { target: { value: 'อื่นๆ' } })
      expect(screen.getByPlaceholderText('พิมพ์ทะเบียนรถ')).toBeInTheDocument()

      fireEvent.click(screen.getByTestId('save-all'))
      await waitFor(() => expect(screen.getByText('กรุณาพิมพ์ทะเบียนรถ')).toBeInTheDocument())
      expect(subformApi.saveDetailLine).not.toHaveBeenCalled()
    })

    it('the typed plate is what gets sent — never the literal อื่นๆ', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([vehicleLine()])
      vi.mocked(subformApi.saveDetailLine).mockResolvedValue(
        vehicleLine({ meta_json: { ทะเบียนรถ: 'กข-1234', สถานที่ใช้งาน: 'BK' } }),
      )
      renderVehicle()
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      fireEvent.change(screen.getByLabelText('ทะเบียนรถ'), { target: { value: 'อื่นๆ' } })
      fireEvent.change(screen.getByPlaceholderText('พิมพ์ทะเบียนรถ'), { target: { value: 'กข-1234' } })
      fireEvent.change(screen.getByLabelText('สถานที่ใช้งาน'), { target: { value: 'BK' } })
      fireEvent.click(screen.getByTestId('save-all'))

      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
      expect(vi.mocked(subformApi.saveDetailLine).mock.calls[0][0].meta_json?.ทะเบียนรถ).toBe('กข-1234')
    })

    it('re-opening a line whose plate is NOT in the 7-list shows อื่นๆ + the plate pre-filled', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([vehicleLine({ meta_json: { ทะเบียนรถ: 'ชล-9999' } })])
      renderVehicle()
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      expect((screen.getByLabelText('ทะเบียนรถ') as HTMLSelectElement).value).toBe('อื่นๆ')
      expect((screen.getByPlaceholderText('พิมพ์ทะเบียนรถ') as HTMLInputElement).value).toBe('ชล-9999')
    })
  })

  describe('Lease & Rental สถานที่ใช้งาน — required dropdown blocks a blank save (bug-lease-blank-dropdown-400)', () => {
    const VEHICLE_GL = '5211200060'
    const BUILDING_GL = '6211200020' // non-vehicle suffix — ประเภทรถ/ทะเบียนรถ render locked

    it('leaving สถานที่ใช้งาน on "— เลือก —" blocks the save with a Thai message and calls the API zero times', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([
        blankLine({ gl_account: VEHICLE_GL, gl_group: 'Lease & Rental' }),
      ])
      render(
        <DetailSubform
          costCenter="CC1"
          glAccount={VEHICLE_GL}
          glGroup="Lease & Rental"
          glName={null}
          fiscalYear={2027}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />,
      )
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())
      fireEvent.change(screen.getByLabelText('กิจกรรม'), { target: { value: 'รับ-ส่งผู้บริหาร' } })

      fireEvent.click(screen.getByTestId('save-all'))

      await waitFor(() => expect(screen.getByText('กรุณาเลือกสถานที่ใช้งาน')).toBeInTheDocument())
      expect(subformApi.saveDetailLine).not.toHaveBeenCalled()
    })

    it('picking a value unblocks the save and the payload carries it', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([
        blankLine({ gl_account: VEHICLE_GL, gl_group: 'Lease & Rental' }),
      ])
      vi.mocked(subformApi.saveDetailLine).mockResolvedValue(
        blankLine({ gl_account: VEHICLE_GL, gl_group: 'Lease & Rental', meta_json: { สถานที่ใช้งาน: 'BK' } }),
      )
      render(
        <DetailSubform
          costCenter="CC1"
          glAccount={VEHICLE_GL}
          glGroup="Lease & Rental"
          glName={null}
          fiscalYear={2027}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />,
      )
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      fireEvent.change(screen.getByLabelText('สถานที่ใช้งาน'), { target: { value: 'BK' } })
      fireEvent.click(screen.getByTestId('save-all'))

      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
      expect(vi.mocked(subformApi.saveDetailLine).mock.calls[0][0].meta_json?.สถานที่ใช้งาน).toBe('BK')
    })

    it('a non-vehicle GL never demands ประเภทรถ/ทะเบียนรถ — locked fields are not part of the required check', async () => {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([
        blankLine({ gl_account: BUILDING_GL, gl_group: 'Lease & Rental' }),
      ])
      vi.mocked(subformApi.saveDetailLine).mockResolvedValue(
        blankLine({ gl_account: BUILDING_GL, gl_group: 'Lease & Rental', meta_json: { สถานที่ใช้งาน: 'TK' } }),
      )
      render(
        <DetailSubform
          costCenter="CC1"
          glAccount={BUILDING_GL}
          glGroup="Lease & Rental"
          glName={null}
          fiscalYear={2027}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />,
      )
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())
      expect(screen.queryByLabelText('ประเภทรถ')).not.toBeInTheDocument() // locked — not even rendered as an input
      expect(screen.queryByLabelText('ทะเบียนรถ')).not.toBeInTheDocument()

      fireEvent.change(screen.getByLabelText('สถานที่ใช้งาน'), { target: { value: 'TK' } })
      fireEvent.click(screen.getByTestId('save-all'))

      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
    })
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

  it('calls onClose when the ยกเลิก button is clicked', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }))
    expect(onClose).toHaveBeenCalled()
  })

  describe('read-only lock (ADR-0013, UI parity port, 2026-08-05)', () => {
    function renderReadOnly(lines: DetailLineState[] = [blankLine()]) {
      vi.mocked(subformApi.fetchDetailLines).mockResolvedValue(lines)
      const onClose = vi.fn()
      const onSaved = vi.fn()
      render(
        <DetailSubform
          costCenter="CC1"
          glAccount="5211900030"
          glGroup="Entertainment"
          glName="ค่าเลี้ยงรับรองภายนอก"
          fiscalYear={2027}
          readOnly
          onClose={onClose}
          onSaved={onSaved}
        />,
      )
      return { onClose, onSaved }
    }

    it('shows the 🔒 title marker and the อ่านอย่างเดียว subtitle', async () => {
      renderReadOnly()
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      expect(screen.getByRole('heading')).toHaveTextContent('🔒')
      expect(screen.getByText(/อ่านอย่างเดียว \(แก้ไม่ได้\)/)).toBeInTheDocument()
    })

    it('every meta/month input is disabled and the trash button is hidden', async () => {
      renderReadOnly()
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      expect(screen.getByLabelText('รายละเอียด')).toBeDisabled()
      expect(screen.getByLabelText('m01 existing-1')).toBeDisabled()
      expect(screen.queryByRole('button', { name: 'ลบรายการ' })).not.toBeInTheDocument()
    })

    it('hides "+ เพิ่มรายการ" and "บันทึก", and the close button reads "ปิด"', async () => {
      renderReadOnly()
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      expect(screen.queryByRole('button', { name: /เพิ่มรายการ/ })).not.toBeInTheDocument()
      expect(screen.queryByTestId('save-all')).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'ปิด' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'ยกเลิก' })).not.toBeInTheDocument()
    })

    it('"ปิด" calls onClose, and no write API is ever called', async () => {
      const { onClose } = renderReadOnly()
      await waitFor(() => expect(screen.getByTestId('detail-row-existing-1')).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: 'ปิด' }))

      expect(onClose).toHaveBeenCalled()
      expect(subformApi.saveDetailLine).not.toHaveBeenCalled()
      expect(subformApi.deleteDetailLine).not.toHaveBeenCalled()
    })
  })
})
