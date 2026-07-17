import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import * as referenceApi from '../api/reference'
import * as subformApi from '../api/subform'
import type { DetailLineState, TripListItem } from '../api/types'
import type { TravelSideHistory } from './model'
import { TripManager } from './TripManager'

vi.mock('../api/subform')
vi.mock('../api/reference')

/** Default fixture = a ฝ่าย with history on BOTH sides (SGA the larger) —
 * the select stays enabled and new trips default to SGA, preserving the
 * behavior every pre-existing test in this file was written against. */
const BOTH_SIDES: TravelSideHistory = { sides: ['COST', 'SGA'], defaultSide: 'SGA' }

/** Default reference masters — every test needs these resolved (the modal
 * loads them alongside the trips). E1 matches `tripItem()`'s traveler. */
const TRAVELERS = [
  { empcode: 'E1', name: 'สมชาย ใจดี', position: 'Supervisor' },
  { empcode: 'E7', name: 'สมปอง ขยัน', position: 'Officer' },
  { empcode: 'E9', name: 'ใหม่ ทดสอบ', position: 'Manager' },
]
const COUNTRIES: { country: string; country_group: 1 | 2 }[] = [
  { country: 'ประเทศไทย', country_group: 1 },
  { country: 'ญี่ปุ่น', country_group: 2 },
]

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
    project: null,
    purpose: null,
    side: 'COST',
    updated_at: '2026-01-01T00:00:00',
    per_diem_months: { ...blankMonths(), m02: 500, m03: 500 },
    per_diem_error: null,
    ...overrides,
  }
}

/** New-trip happy-path prerequisites: traveler + days + a month + destination
 * (ประเทศไทย → group 1). Tests asserting a specific field override after.
 * `monthButtonIndex` = which card's m05 toggle (multi-card tests). */
function fillNewTripBasics(localId = 'new-0', monthButtonIndex = 0) {
  fireEvent.change(screen.getByLabelText(`traveler_empcode ${localId}`), { target: { value: 'E9' } })
  fireEvent.change(screen.getByLabelText(`days ${localId}`), { target: { value: '3' } })
  fireEvent.click(screen.getAllByRole('button', { name: 'm05' })[monthButtonIndex])
  fireEvent.change(screen.getByLabelText(`destination ${localId}`), { target: { value: 'ประเทศไทย' } })
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
  beforeEach(() => {
    // Reference masters load alongside the trip list on every mount.
    vi.mocked(referenceApi.fetchTravelers).mockResolvedValue(TRAVELERS)
    vi.mocked(referenceApi.fetchCountries).mockResolvedValue(COUNTRIES)
  })
  afterEach(() => vi.resetAllMocks())

  it('shows a loading state then the existing trips', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(screen.getByText(/กำลังโหลด/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
  })

  it('shows an empty state with an "+ เพิ่มทริป" affordance', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /เพิ่มทริป/ })).toBeInTheDocument()
  })

  // FIX #2 — a click on "+ เพิ่มทริป" DURING the initial load used to be
  // silently lost: load()'s setCards(...) replaces the array, discarding the
  // just-added blank card. The button must be disabled until the data lands.
  it('disables "+ เพิ่มทริป" while the initial load is in-flight, then a post-load click adds a card that survives', async () => {
    let resolveTrips!: (trips: TripListItem[]) => void
    vi.mocked(subformApi.fetchTrips).mockImplementation(
      () =>
        new Promise<TripListItem[]>((resolve) => {
          resolveTrips = resolve
        }),
    )
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    const addBtn = screen.getByRole('button', { name: /เพิ่มทริป/ })
    expect(addBtn).toBeDisabled()

    resolveTrips([])
    await waitFor(() => expect(addBtn).toBeEnabled())

    fireEvent.click(addBtn)
    expect(screen.getByTestId('trip-card-new-0')).toBeInTheDocument()
  })

  it('shows an error state with retry on fetch failure', async () => {
    vi.mocked(subformApi.fetchTrips)
      .mockRejectedValueOnce(new ApiError(502, 'เซิร์ฟเวอร์ขัดข้อง'))
      .mockResolvedValueOnce([])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('เซิร์ฟเวอร์ขัดข้อง')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'ลองใหม่' }))
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
  })

  it('shows the server per-diem total for a freshly-loaded (non-dirty) trip', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
    expect(screen.getByText(/จากเซิร์ฟเวอร์/)).toBeInTheDocument()
    expect(screen.getByText(/1,000/)).toBeInTheDocument()
  })

  it('shows "รอคำนวณหลังบันทึก" (never a client-computed number) once the trip is edited', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('days existing-10'), { target: { value: '9' } })
    expect(screen.getByText(/ระบบจะคำนวณให้หลังกดบันทึก/)).toBeInTheDocument()
  })

  it('surfaces a per_diem_error from the read path without blocking the rest of the card', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([
      tripItem({ per_diem_months: null, per_diem_error: 'no master_currency_rate for fiscal_year=2027' }),
    ])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
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
      position: 'Manager',
      destination: 'ประเทศไทย',
      country_group: 1,
      days: 3,
      travel_months: ['05'],
      project: null,
      purpose: null,
      side: 'SGA',
      updated_at: '2026-01-02T00:00:00',
      per_diem_months: { ...blankMonths(), m05: 900 },
    })
    const onSaved = vi.fn()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={onSaved} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fillNewTripBasics()
    fireEvent.click(screen.getByTestId('save-trip-new-0'))

    await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalled())
    const payload = vi.mocked(subformApi.createTrip).mock.calls[0][0]
    expect(payload.traveler_empcode).toBe('E9')
    expect(payload.travel_months).toEqual(['05'])
    expect(payload.destination).toBe('ประเทศไทย')
    expect(payload.country_group).toBe(1) // derived from ประเทศไทย, never hand-picked
    expect(onSaved).toHaveBeenCalled()
    await waitFor(() => expect(screen.getByText(/900/)).toBeInTheDocument())
  })

  it('sends a client_token on create, keeps the SAME token on retry after an error, and re-enables the save button', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    vi.mocked(subformApi.createTrip)
      .mockRejectedValueOnce(new Error('network down')) // lost response — the classic retry case
      .mockResolvedValueOnce({
        trip_id: 99, cost_center: 'CC1', fiscal_year: 2027, traveler_empcode: 'E9',
        traveler_name: 'ใหม่ ทดสอบ', position: 'Manager', destination: 'ประเทศไทย',
        country_group: 1, days: 3, travel_months: ['05'], project: null, purpose: null, side: 'SGA',
        updated_at: '2026-01-02T00:00:00', per_diem_months: { ...blankMonths(), m05: 900 },
      })
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fillNewTripBasics()

    fireEvent.click(screen.getByTestId('save-trip-new-0'))
    await waitFor(() => expect(screen.getByText('บันทึกทริปไม่สำเร็จ')).toBeInTheDocument())
    expect(screen.getByTestId('save-trip-new-0')).toBeEnabled() // user can retry

    fireEvent.click(screen.getByTestId('save-trip-new-0'))
    await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalledTimes(2))
    const first = vi.mocked(subformApi.createTrip).mock.calls[0][0]
    const second = vi.mocked(subformApi.createTrip).mock.calls[1][0]
    expect(first.client_token).toBeTruthy()
    expect(second.client_token).toBe(first.client_token) // same intent -> same token -> server dedups
  })

  it('each new trip card carries its own client_token (a new intent regenerates)', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    vi.mocked(subformApi.createTrip).mockImplementation(async (payload) => ({
      trip_id: payload.traveler_empcode === 'E9' ? 99 : 100,
      cost_center: 'CC1', fiscal_year: 2027, traveler_empcode: payload.traveler_empcode,
      traveler_name: 'ใหม่ ทดสอบ', position: 'Manager', destination: 'ประเทศไทย',
      country_group: 1, days: 3, travel_months: ['05'], project: null, purpose: null, side: 'SGA',
      updated_at: '2026-01-02T00:00:00', per_diem_months: { ...blankMonths(), m05: 900 },
    }))
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fillNewTripBasics('new-0', 0)
    fireEvent.click(screen.getByTestId('save-trip-new-0'))
    await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fireEvent.change(screen.getByLabelText('traveler_empcode new-1'), { target: { value: 'E7' } })
    fireEvent.change(screen.getByLabelText('days new-1'), { target: { value: '4' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'm05' })[1])
    fireEvent.change(screen.getByLabelText('destination new-1'), { target: { value: 'ญี่ปุ่น' } })
    fireEvent.click(screen.getByTestId('save-trip-new-1'))
    await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalledTimes(2))

    const first = vi.mocked(subformApi.createTrip).mock.calls[0][0]
    const second = vi.mocked(subformApi.createTrip).mock.calls[1][0]
    expect(first.client_token).toBeTruthy()
    expect(second.client_token).toBeTruthy()
    expect(second.client_token).not.toBe(first.client_token)
  })

  it('disables the save button while the create is in flight (double-click cannot fire twice)', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    let resolveCreate: (value: Awaited<ReturnType<typeof subformApi.createTrip>>) => void = () => {}
    vi.mocked(subformApi.createTrip).mockImplementation(
      () => new Promise((resolve) => { resolveCreate = resolve }),
    )
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fillNewTripBasics()
    fireEvent.click(screen.getByTestId('save-trip-new-0'))

    await waitFor(() => expect(screen.getByTestId('save-trip-new-0')).toBeDisabled())
    fireEvent.click(screen.getByTestId('save-trip-new-0')) // double-click during flight
    expect(subformApi.createTrip).toHaveBeenCalledTimes(1)

    resolveCreate({
      trip_id: 99, cost_center: 'CC1', fiscal_year: 2027, traveler_empcode: 'E9',
      traveler_name: 'ใหม่ ทดสอบ', position: 'Manager', destination: 'ประเทศไทย',
      country_group: 1, days: 3, travel_months: ['05'], project: null, purpose: null, side: 'SGA',
      updated_at: '2026-01-02T00:00:00', per_diem_months: { ...blankMonths(), m05: 900 },
    })
    await waitFor(() => expect(screen.getByTestId('save-trip-existing-99')).toBeEnabled())
  })

  it('rejects saving a trip with no traveler/days/months (client-side validation)', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
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
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('side existing-10'), { target: { value: 'SGA' } })
    fireEvent.click(screen.getByTestId('save-trip-existing-10'))

    await waitFor(() => expect(subformApi.updateTrip).toHaveBeenCalled())
    const payload = vi.mocked(subformApi.updateTrip).mock.calls[0][0]
    expect(payload.side).toBe('SGA')
    expect(payload.trip_id).toBe(10)
  })

  it('clearing the project input on an EXISTING trip sends "" (not null) — null would tell the backend to leave the old value untouched', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem({ project: 'Alpha' })])
    mockNoManualLines()
    vi.mocked(subformApi.updateTrip).mockResolvedValue({ ...tripItem(), project: '' } as never)
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
    expect(screen.getByLabelText('project existing-10')).toHaveValue('Alpha')

    fireEvent.change(screen.getByLabelText('project existing-10'), { target: { value: '' } })
    fireEvent.click(screen.getByTestId('save-trip-existing-10'))

    await waitFor(() => expect(subformApi.updateTrip).toHaveBeenCalled())
    const payload = vi.mocked(subformApi.updateTrip).mock.calls[0][0]
    expect(payload.project).toBe('')
    expect(payload.project).not.toBeNull()
  })

  it('shows a 500-class error as a clear "ไม่สามารถคำนวณเบี้ยเลี้ยงได้" message, never a silent fallback', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    vi.mocked(subformApi.createTrip).mockRejectedValue(
      new ApiError(500, 'เซิร์ฟเวอร์ขัดข้อง', 'no master_currency_rate for fiscal_year=2027'),
    )
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fillNewTripBasics()
    fireEvent.click(screen.getByTestId('save-trip-new-0'))

    await waitFor(() => expect(screen.getByText(/ไม่สามารถคำนวณเบี้ยเลี้ยงได้/)).toBeInTheDocument())
    expect(screen.getByText(/no master_currency_rate/)).toBeInTheDocument()
  })

  it('a manual expense type only allows input on the trip travel_months, and saves via saveDetailLine with trip_id', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
    mockNoManualLines()
    vi.mocked(subformApi.saveDetailLine).mockResolvedValue(detailLine({ m02: 1000, total_year: 1000 }))
    const onSaved = vi.fn()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={onSaved} />)
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

  describe('traveler + destination dropdowns (2026-07-17)', () => {
    function mockCreateOk() {
      vi.mocked(subformApi.createTrip).mockResolvedValue({
        trip_id: 99, cost_center: 'CC1', fiscal_year: 2027, traveler_empcode: 'E9',
        traveler_name: 'ใหม่ ทดสอบ', position: 'Manager', destination: 'ประเทศไทย',
        country_group: 1, days: 3, travel_months: ['05'], project: null, purpose: null, side: 'SGA',
        updated_at: '2026-01-02T00:00:00', per_diem_months: { ...blankMonths(), m05: 900 },
      })
    }

    async function renderEmpty() {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
    }

    it('traveler is a dropdown of names from /reference/travelers with the placeholder — no free-typed empcode', async () => {
      await renderEmpty()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))

      const select = screen.getByLabelText('traveler_empcode new-0') as HTMLSelectElement
      expect(select.tagName).toBe('SELECT')
      expect(referenceApi.fetchTravelers).toHaveBeenCalledWith('CC1')
      expect(screen.getByRole('option', { name: '— เลือกผู้เดินทาง —' })).toBeInTheDocument()
      // label = ชื่อ, value = empcode
      const somchai = screen.getByRole('option', { name: 'สมชาย ใจดี' }) as HTMLOptionElement
      expect(somchai.value).toBe('E1')
    })

    it('selecting a traveler auto-displays the read-only position (no position input exists)', async () => {
      await renderEmpty()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))

      expect(screen.getByTestId('position-new-0')).toHaveTextContent('—')
      fireEvent.change(screen.getByLabelText('traveler_empcode new-0'), { target: { value: 'E9' } })
      expect(screen.getByTestId('position-new-0')).toHaveTextContent('Manager')
      expect(screen.queryByLabelText('position new-0')).not.toBeInTheDocument()
    })

    it('an existing trip shows its response traveler name + position even when absent from the current list', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([
        tripItem({ traveler_empcode: 'EGONE', traveler_name: 'อดีต พนักงาน', position: 'Director' }),
      ])
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      expect(screen.getByTestId('position-existing-10')).toHaveTextContent('Director')
      // the select still displays the stored traveler via a fallback option
      const fallback = screen.getByRole('option', { name: 'อดีต พนักงาน' }) as HTMLOptionElement
      expect(fallback.value).toBe('EGONE')
      expect((screen.getByLabelText('traveler_empcode existing-10') as HTMLSelectElement).value).toBe('EGONE')
    })

    it('the manual กลุ่มปลายทาง select is GONE; picking ญี่ปุ่น auto-sets country_group 2', async () => {
      mockCreateOk()
      await renderEmpty()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))

      expect(screen.queryByLabelText('country_group new-0')).not.toBeInTheDocument()

      fillNewTripBasics()
      fireEvent.change(screen.getByLabelText('destination new-0'), { target: { value: 'ญี่ปุ่น' } })
      fireEvent.click(screen.getByTestId('save-trip-new-0'))

      await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalled())
      const payload = vi.mocked(subformApi.createTrip).mock.calls[0][0]
      expect(payload.destination).toBe('ญี่ปุ่น')
      expect(payload.country_group).toBe(2)
    })

    it('picking อื่นๆ (Other) auto-sets country_group 3', async () => {
      mockCreateOk()
      await renderEmpty()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))

      fillNewTripBasics()
      fireEvent.change(screen.getByLabelText('destination new-0'), { target: { value: 'อื่นๆ (Other)' } })
      fireEvent.click(screen.getByTestId('save-trip-new-0'))

      await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalled())
      const payload = vi.mocked(subformApi.createTrip).mock.calls[0][0]
      expect(payload.destination).toBe('อื่นๆ (Other)')
      expect(payload.country_group).toBe(3)
    })

    it('project and purpose inputs are included in the payload', async () => {
      mockCreateOk()
      await renderEmpty()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))

      fillNewTripBasics()
      fireEvent.change(screen.getByLabelText('project new-0'), { target: { value: 'PRJ-X' } })
      fireEvent.change(screen.getByLabelText('purpose new-0'), { target: { value: 'ประชุมลูกค้า' } })
      fireEvent.click(screen.getByTestId('save-trip-new-0'))

      await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalled())
      const payload = vi.mocked(subformApi.createTrip).mock.calls[0][0]
      expect(payload.project).toBe('PRJ-X')
      expect(payload.purpose).toBe('ประชุมลูกค้า')
    })

    it('save is blocked with a Thai message until a destination is picked (group derives from it)', async () => {
      await renderEmpty()
      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))

      fireEvent.change(screen.getByLabelText('traveler_empcode new-0'), { target: { value: 'E9' } })
      fireEvent.change(screen.getByLabelText('days new-0'), { target: { value: '3' } })
      fireEvent.click(screen.getByRole('button', { name: 'm05' }))
      fireEvent.click(screen.getByTestId('save-trip-new-0'))

      await waitFor(() => expect(screen.getByText('กรุณาเลือกปลายทาง')).toBeInTheDocument())
      expect(subformApi.createTrip).not.toHaveBeenCalled()
    })
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
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={onSaved} />)
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
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
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
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: 'ลบทริป' }))

      await waitFor(() => expect(subformApi.fetchTrips).toHaveBeenCalledTimes(2))
      expect(screen.getByText(/ถูกแก้ไขหรือถูกลบโดยผู้อื่น/)).toBeInTheDocument()
    })

    it('removes an unsaved (never-persisted) trip card locally without calling the API or confirming', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      expect(screen.getByTestId('trip-card-new-0')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'ลบทริป' }))

      expect(window.confirm).not.toHaveBeenCalled()
      expect(subformApi.deleteTrip).not.toHaveBeenCalled()
      expect(screen.queryByTestId('trip-card-new-0')).not.toBeInTheDocument()
    })
  })

  describe('accounting side (ฝั่งบัญชี) derivation — ฝ่าย-level history', () => {
    it('single-side ฝ่าย (SGA-only) + non-admin → new trip locked to SGA, select disabled', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      render(
        <TripManager costCenter="CC1" fiscalYear={2027} sideHistory={{ sides: ['SGA'], defaultSide: 'SGA' }} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />,
      )
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      const select = screen.getByLabelText('side new-0')
      expect(select).toHaveValue('SGA')
      expect(select).toBeDisabled()
    })

    it('single-side ฝ่าย + admin → select stays enabled (only admin may introduce a new side)', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      render(
        <TripManager costCenter="CC1" fiscalYear={2027} sideHistory={{ sides: ['COST'], defaultSide: 'COST' }} isAdmin={true} onClose={vi.fn()} onSaved={vi.fn()} />,
      )
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      const select = screen.getByLabelText('side new-0')
      expect(select).toHaveValue('COST')
      expect(select).toBeEnabled()
    })

    it('an EXISTING trip in a single-side ฝ่าย is also locked for non-admin', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()]) // side COST
      mockNoManualLines()
      render(
        <TripManager costCenter="CC1" fiscalYear={2027} sideHistory={{ sides: ['COST'], defaultSide: 'COST' }} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />,
      )
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
      expect(screen.getByLabelText('side existing-10')).toBeDisabled()
    })

    it('both-side ฝ่าย → both options offered, default = the larger-total side', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      render(
        <TripManager costCenter="CC1" fiscalYear={2027} sideHistory={{ sides: ['COST', 'SGA'], defaultSide: 'COST' }} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />,
      )
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      const select = screen.getByLabelText('side new-0')
      expect(select).toHaveValue('COST')
      expect(select).toBeEnabled()
      expect(screen.getByRole('option', { name: /5xxx/ })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /6xxx/ })).toBeInTheDocument()
    })

    it('no-history ฝ่าย → placeholder "— เลือกฝั่ง —", save blocked until a side is picked, then saves with it', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      vi.mocked(subformApi.createTrip).mockResolvedValue({
        trip_id: 99, cost_center: 'CC1', fiscal_year: 2027, traveler_empcode: 'E9',
        traveler_name: 'ใหม่ ทดสอบ', position: 'Manager', destination: 'ประเทศไทย',
        country_group: 1, days: 3, travel_months: ['05'], project: null, purpose: null, side: 'COST',
        updated_at: '2026-01-02T00:00:00', per_diem_months: { ...blankMonths(), m05: 900 },
      })
      render(
        <TripManager costCenter="CC1" fiscalYear={2027} sideHistory={{ sides: [], defaultSide: null }} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />,
      )
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      fillNewTripBasics()

      const select = screen.getByLabelText('side new-0')
      expect(select).toBeEnabled() // nothing to lock to — the user decides
      expect(select).toHaveValue('')
      expect(screen.getByRole('option', { name: '— เลือกฝั่ง —' })).toBeInTheDocument()
      expect(screen.getByTestId('save-trip-new-0')).toBeDisabled() // no silent default — blocked

      fireEvent.change(select, { target: { value: 'COST' } })
      expect(screen.getByTestId('save-trip-new-0')).toBeEnabled()

      fireEvent.click(screen.getByTestId('save-trip-new-0'))
      await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalled())
      expect(vi.mocked(subformApi.createTrip).mock.calls[0][0].side).toBe('COST')
    })
  })

  it('calls onClose when the close button is clicked', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    const onClose = vi.fn()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={onClose} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'ปิด' }))
    expect(onClose).toHaveBeenCalled()
  })
})
