import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import * as subformApi from '../api/subform'
import type { DetailLineState, TripListItem } from '../api/types'
import { TripManager } from './TripManager'

vi.mock('../api/subform')

function blankMonths(): Record<string, number> {
  return Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`m${String(i + 1).padStart(2, '0')}`, 0]))
}

function tripItem(overrides: Partial<TripListItem> = {}): TripListItem {
  return {
    trip_id: 10,
    cost_center: 'CC1',
    fiscal_year: 2027,
    traveler_empcode: 'E1',
    traveler_name: 'สมชาย ใจดี',
    position: 'Supervisor',
    destination: 'Japan',
    country_group: 2,
    days: 5,
    travel_months: ['02', '03'],
    purpose: null,
    side: 'COST',
    updated_at: '2026-01-01T00:00:00',
    per_diem_months: { ...blankMonths(), m02: 500, m03: 500 },
    per_diem_error: null,
    ...overrides,
  }
}

function detailLine(overrides: Partial<DetailLineState> = {}): DetailLineState {
  return {
    detail_id: 1,
    cost_center: 'CC1',
    gl_account: '5210400020',
    fiscal_year: 2027,
    trip_id: 10,
    gl_group: 'Travelling Expense',
    line_label: null,
    ...blankMonths(),
    total_year: 0,
    meta_json: null,
    updated_at: '2026-01-01T00:00:00',
    ...overrides,
  } as DetailLineState
}

function mockNoManualLines() {
  vi.mocked(subformApi.fetchDetailLines).mockResolvedValue([])
}

describe('TripManager', () => {
  afterEach(() => vi.resetAllMocks())

  it('shows a loading state then the existing trips', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(screen.getByText(/กำลังโหลด/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
  })

  it('shows an empty state with an "+ เพิ่มทริป" affordance', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /เพิ่มทริป/ })).toBeInTheDocument()
  })

  it('shows an error state with retry on fetch failure', async () => {
    vi.mocked(subformApi.fetchTrips)
      .mockRejectedValueOnce(new ApiError(502, 'เซิร์ฟเวอร์ขัดข้อง'))
      .mockResolvedValueOnce([])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('เซิร์ฟเวอร์ขัดข้อง')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'ลองใหม่' }))
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
  })

  it('shows the server per-diem total for a freshly-loaded (non-dirty) trip', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
    expect(screen.getByText(/จากเซิร์ฟเวอร์/)).toBeInTheDocument()
    expect(screen.getByText(/1,000/)).toBeInTheDocument()
  })

  it('shows "รอคำนวณหลังบันทึก" (never a client-computed number) once the trip is edited', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('days existing-10'), { target: { value: '9' } })
    expect(screen.getByText(/ระบบจะคำนวณให้หลังกดบันทึก/)).toBeInTheDocument()
  })

  it('surfaces a per_diem_error from the read path without blocking the rest of the card', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([
      tripItem({ per_diem_months: null, per_diem_error: 'no master_currency_rate for fiscal_year=2027' }),
    ])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ไม่สามารถคำนวณเบี้ยเลี้ยงได้/)).toBeInTheDocument())
  })

  it('adds a new trip, fills it, and saves it via createTrip; onSaved is called', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    vi.mocked(subformApi.createTrip).mockResolvedValue({
      trip_id: 99,
      cost_center: 'CC1',
      fiscal_year: 2027,
      traveler_empcode: 'E9',
      traveler_name: 'ใหม่ ทดสอบ',
      position: 'Supervisor',
      destination: null,
      country_group: 1,
      days: 3,
      travel_months: ['05'],
      purpose: null,
      side: 'SGA',
      updated_at: '2026-01-02T00:00:00',
      per_diem_months: { ...blankMonths(), m05: 900 },
    })
    const onSaved = vi.fn()
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={onSaved} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fireEvent.change(screen.getByLabelText('traveler_empcode new-0'), { target: { value: 'E9' } })
    fireEvent.change(screen.getByLabelText('days new-0'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'm05' }))
    fireEvent.click(screen.getByTestId('save-trip-new-0'))

    await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalled())
    const payload = vi.mocked(subformApi.createTrip).mock.calls[0][0]
    expect(payload.traveler_empcode).toBe('E9')
    expect(payload.travel_months).toEqual(['05'])
    expect(onSaved).toHaveBeenCalled()
    await waitFor(() => expect(screen.getByText(/900/)).toBeInTheDocument())
  })

  it('rejects saving a trip with no traveler/days/months (client-side validation)', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fireEvent.click(screen.getByTestId('save-trip-new-0'))
    await waitFor(() => expect(screen.getByText('กรุณาระบุผู้เดินทาง')).toBeInTheDocument())
    expect(subformApi.createTrip).not.toHaveBeenCalled()
  })

  it('flipping side on an existing trip calls updateTrip via PUT (side flip re-homes lines server-side)', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
    mockNoManualLines()
    vi.mocked(subformApi.updateTrip).mockResolvedValue({
      ...tripItem(),
      side: 'SGA',
      per_diem_months: { ...blankMonths(), m02: 500, m03: 500 },
    } as never)
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('side existing-10'), { target: { value: 'SGA' } })
    fireEvent.click(screen.getByTestId('save-trip-existing-10'))

    await waitFor(() => expect(subformApi.updateTrip).toHaveBeenCalled())
    const payload = vi.mocked(subformApi.updateTrip).mock.calls[0][0]
    expect(payload.side).toBe('SGA')
    expect(payload.trip_id).toBe(10)
  })

  it('shows a 500-class error as a clear "ไม่สามารถคำนวณเบี้ยเลี้ยงได้" message, never a silent fallback', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    vi.mocked(subformApi.createTrip).mockRejectedValue(
      new ApiError(500, 'เซิร์ฟเวอร์ขัดข้อง', 'no master_currency_rate for fiscal_year=2027'),
    )
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fireEvent.change(screen.getByLabelText('traveler_empcode new-0'), { target: { value: 'E9' } })
    fireEvent.change(screen.getByLabelText('days new-0'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'm05' }))
    fireEvent.click(screen.getByTestId('save-trip-new-0'))

    await waitFor(() => expect(screen.getByText(/ไม่สามารถคำนวณเบี้ยเลี้ยงได้/)).toBeInTheDocument())
    expect(screen.getByText(/no master_currency_rate/)).toBeInTheDocument()
  })

  it('a manual expense type only allows input on the trip travel_months, and saves via saveDetailLine with trip_id', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
    mockNoManualLines()
    vi.mocked(subformApi.saveDetailLine).mockResolvedValue(detailLine({ m02: 1000, total_year: 1000 }))
    const onSaved = vi.fn()
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={onSaved} />)
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

    // m02 is in travel_months (active) -> editable input exists
    const input = screen.getByLabelText('transport m02 existing-10')
    fireEvent.change(input, { target: { value: '1000' } })
    // m01 is NOT in travel_months -> no input for it
    expect(screen.queryByLabelText('transport m01 existing-10')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('save-manual-transport-existing-10'))

    await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
    const payload = vi.mocked(subformApi.saveDetailLine).mock.calls[0][0]
    expect(payload.trip_id).toBe(10)
    expect(payload.gl_account).toBe('5210400020') // transport, COST (this trip's side)
    expect(payload.m02).toBe(1000)
    expect(onSaved).toHaveBeenCalled()
  })

  describe('delete trip', () => {
    beforeEach(() => {
      vi.spyOn(window, 'confirm').mockReturnValue(true)
    })
    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('confirms in Thai, calls deleteTrip with the trip lock token, removes the card, and calls onSaved', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem({ updated_at: '2026-03-01T00:00:00' })])
      mockNoManualLines()
      vi.mocked(subformApi.deleteTrip).mockResolvedValue({ ok: true })
      const onSaved = vi.fn()
      render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={onSaved} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: 'ลบทริป' }))

      expect(window.confirm).toHaveBeenCalledWith(
        'ลบทริปนี้ทั้งหมด? รายการเบี้ยเลี้ยง/ค่าเดินทางทั้งหมดของทริปจะถูกลบ',
      )
      await waitFor(() => expect(subformApi.deleteTrip).toHaveBeenCalledWith(10, '2026-03-01T00:00:00'))
      await waitFor(() => expect(screen.queryByTestId('trip-card-existing-10')).not.toBeInTheDocument())
      expect(onSaved).toHaveBeenCalled()
    })

    it('does nothing when the user cancels the confirm dialog', async () => {
      vi.mocked(window.confirm).mockReturnValue(false)
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: 'ลบทริป' }))

      expect(subformApi.deleteTrip).not.toHaveBeenCalled()
      expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument()
    })

    it('a 409 conflict on delete refetches the trips and shows a Thai message', async () => {
      vi.mocked(subformApi.fetchTrips)
        .mockResolvedValueOnce([tripItem()])
        .mockResolvedValueOnce([tripItem({ days: 9 })])
      mockNoManualLines()
      vi.mocked(subformApi.deleteTrip).mockRejectedValue(new ApiError(409, 'ถูกแก้ไขโดยผู้อื่น'))
      render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: 'ลบทริป' }))

      await waitFor(() => expect(subformApi.fetchTrips).toHaveBeenCalledTimes(2))
      expect(screen.getByText(/ถูกแก้ไขหรือถูกลบโดยผู้อื่น/)).toBeInTheDocument()
    })

    it('removes an unsaved (never-persisted) trip card locally without calling the API or confirming', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      expect(screen.getByTestId('trip-card-new-0')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'ลบทริป' }))

      expect(window.confirm).not.toHaveBeenCalled()
      expect(subformApi.deleteTrip).not.toHaveBeenCalled()
      expect(screen.queryByTestId('trip-card-new-0')).not.toBeInTheDocument()
    })
  })

  it('calls onClose when the close button is clicked', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    const onClose = vi.fn()
    render(<TripManager costCenter="CC1" fiscalYear={2027} onClose={onClose} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'ปิด' }))
    expect(onClose).toHaveBeenCalled()
  })
})
