import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import * as referenceApi from '../api/reference'
import * as subformApi from '../api/subform'
import type { DetailLineState, TripListItem } from '../api/types'
import { TRAVEL_GL_BY_TYPE_SIDE } from './glDropdownConstants'
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

/** The one save path for the whole modal — clicked instead of the removed
 * per-card "บันทึกทริป" / per-row "บันทึก" buttons. A stable testid
 * (rather than matching its accessible name, which changes to
 * "กำลังบันทึก…" mid-flight) keeps every test robust to that label swap. */
function saveAllButton() {
  return screen.getByTestId('save-all')
}

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
  fireEvent.click(screen.getAllByRole('button', { name: 'May' })[monthButtonIndex])
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

function tripState(overrides: Partial<Awaited<ReturnType<typeof subformApi.createTrip>>> = {}) {
  return {
    trip_id: 99,
    cost_center: 'CC1',
    fiscal_year: 2027,
    traveler_empcode: 'E9',
    traveler_name: 'ใหม่ ทดสอบ',
    position: 'Manager',
    destination: 'ประเทศไทย',
    country_group: 1 as const,
    days: 3,
    travel_months: ['05'],
    project: null,
    purpose: null,
    side: 'SGA' as const,
    updated_at: '2026-01-02T00:00:00',
    per_diem_months: { ...blankMonths(), m05: 900 },
    ...overrides,
  }
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

  it('adds a new trip, fills it, and saves it via createTrip through save-all; onSaved is called', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    vi.mocked(subformApi.createTrip).mockResolvedValue(tripState())
    const onSaved = vi.fn()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={onSaved} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fillNewTripBasics()
    fireEvent.click(saveAllButton())

    await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalled())
    const payload = vi.mocked(subformApi.createTrip).mock.calls[0][0]
    expect(payload.traveler_empcode).toBe('E9')
    expect(payload.travel_months).toEqual(['05'])
    expect(payload.destination).toBe('ประเทศไทย')
    expect(payload.country_group).toBe(1) // derived from ประเทศไทย, never hand-picked
    expect(onSaved).toHaveBeenCalled()
    // The saved 900 now appears twice by design (the per-diem month cell AND
    // the new "ยอดรวม/ทริป" total column) — getAllByText, not getByText.
    await waitFor(() => expect(screen.getAllByText(/900/).length).toBeGreaterThan(0))
  })

  it('sends a client_token on create, keeps the SAME token on retry after an error, and re-enables save-all', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    vi.mocked(subformApi.createTrip)
      .mockRejectedValueOnce(new Error('network down')) // lost response — the classic retry case
      .mockResolvedValueOnce(tripState())
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fillNewTripBasics()

    fireEvent.click(saveAllButton())
    await waitFor(() => expect(screen.getByTestId('trip-card-error-new-0')).toHaveTextContent('บันทึกทริปไม่สำเร็จ'))
    expect(saveAllButton()).toBeEnabled() // user can retry

    fireEvent.click(saveAllButton())
    await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalledTimes(2))
    const first = vi.mocked(subformApi.createTrip).mock.calls[0][0]
    const second = vi.mocked(subformApi.createTrip).mock.calls[1][0]
    expect(first.client_token).toBeTruthy()
    expect(second.client_token).toBe(first.client_token) // same intent -> same token -> server dedups
  })

  it('each new trip card carries its own client_token (a new intent regenerates)', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    vi.mocked(subformApi.createTrip).mockImplementation(async (payload) =>
      tripState({ trip_id: payload.traveler_empcode === 'E9' ? 99 : 100, traveler_empcode: payload.traveler_empcode }),
    )
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fillNewTripBasics('new-0', 0)
    fireEvent.click(saveAllButton())
    await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalledTimes(1))

    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fireEvent.change(screen.getByLabelText('traveler_empcode new-1'), { target: { value: 'E7' } })
    fireEvent.change(screen.getByLabelText('days new-1'), { target: { value: '4' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'May' })[1])
    fireEvent.change(screen.getByLabelText('destination new-1'), { target: { value: 'ญี่ปุ่น' } })
    fireEvent.click(saveAllButton())
    await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalledTimes(2))

    const first = vi.mocked(subformApi.createTrip).mock.calls[0][0]
    const second = vi.mocked(subformApi.createTrip).mock.calls[1][0]
    expect(first.client_token).toBeTruthy()
    expect(second.client_token).toBeTruthy()
    expect(second.client_token).not.toBe(first.client_token)
  })

  it('disables save-all while the create is in flight (double-click cannot fire twice)', async () => {
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
    fireEvent.click(saveAllButton())

    await waitFor(() => expect(saveAllButton()).toBeDisabled())
    fireEvent.click(saveAllButton()) // double-click during flight
    expect(subformApi.createTrip).toHaveBeenCalledTimes(1)

    resolveCreate(tripState())
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-99')).toBeInTheDocument())
    expect(saveAllButton()).toBeEnabled()
  })

  it('rejects saving a trip with no traveler/days/months (client-side validation)', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
    fireEvent.click(saveAllButton())
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
    fireEvent.click(saveAllButton())

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
    fireEvent.click(saveAllButton())

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
    fireEvent.click(saveAllButton())

    await waitFor(() => expect(screen.getByText(/ไม่สามารถคำนวณเบี้ยเลี้ยงได้/)).toBeInTheDocument())
    expect(screen.getByText(/no master_currency_rate/)).toBeInTheDocument()
  })

  it('a manual expense type only allows input on the trip travel_months, and save-all persists it via saveDetailLine with trip_id', async () => {
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

    fireEvent.click(saveAllButton())

    await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
    const payload = vi.mocked(subformApi.saveDetailLine).mock.calls[0][0]
    expect(payload.trip_id).toBe(10)
    expect(payload.gl_account).toBe('5210400020') // transport, COST (this trip's side)
    expect(payload.m02).toBe(1000)
    expect(onSaved).toHaveBeenCalled()
  })

  describe('traveler + destination dropdowns (2026-07-17)', () => {
    function mockCreateOk() {
      vi.mocked(subformApi.createTrip).mockResolvedValue(tripState())
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
      fireEvent.click(saveAllButton())

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
      fireEvent.click(saveAllButton())

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
      fireEvent.click(saveAllButton())

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
      fireEvent.click(screen.getByRole('button', { name: 'May' }))
      fireEvent.click(saveAllButton())

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

    // REGRESSION (nothing else to lose): with only ONE card in the modal,
    // there is no other unsaved edit that an auto-reload could discard —
    // auto-load() is the simplest-consistent behavior here (kept as-is
    // rather than routing a no-op-loss case through the explicit banner).
    it('a 409 conflict on delete refetches the trips and shows a Thai message (regression: no other unsaved edits, safe to auto-reload)', async () => {
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

    // BUG FIX (financial never-cut): the OTHER card (existing-11) has a
    // persisted manual line cleared to 0 but not yet saved. Deleting card
    // existing-10 must NOT auto-load — that would silently discard the
    // cleared-to-0 edit (and revert it to the stale server value of 500
    // with no warning). Reuses save-all's SAME conflict-banner mechanism
    // (`conflictMessage` + the one "โหลดข้อมูลล่าสุด" button already
    // rendered in the modal body) instead of a parallel one.
    it('a 409 conflict on delete does NOT auto-reload when ANOTHER card has an unsaved edit — banner + explicit reload button appear, the unsaved edit survives until the user reloads', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([
        tripItem({ trip_id: 10 }),
        tripItem({ trip_id: 11, updated_at: '2026-02-01T00:00:00' }),
      ])
      vi.mocked(subformApi.fetchDetailLines).mockImplementation(async (_cc, gl) =>
        gl === TRAVEL_GL_BY_TYPE_SIDE.transport.COST ? [detailLine({ trip_id: 11, m02: 500, total_year: 500 })] : [],
      )
      vi.mocked(subformApi.deleteTrip).mockRejectedValue(new ApiError(409, 'ถูกแก้ไขโดยผู้อื่น'))
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
      expect(screen.getByTestId('trip-card-existing-11')).toBeInTheDocument()

      // Card 11's persisted manual line (500) is cleared to 0 — unsaved.
      // (The input renders a zero value as '' — `months[m] || ''` — so the
      // cleared state is an empty box, not a literal "0".)
      const input = screen.getByLabelText('transport m02 existing-11')
      expect(input).toHaveValue('500')
      fireEvent.change(input, { target: { value: '0' } })
      expect(input).toHaveValue('')

      // Delete card 10 (first "ลบทริป" button = the first card) -> 409.
      fireEvent.click(screen.getAllByRole('button', { name: 'ลบทริป' })[0])

      await waitFor(() => expect(subformApi.deleteTrip).toHaveBeenCalled())
      expect(subformApi.fetchTrips).toHaveBeenCalledTimes(1) // load() NOT auto-called
      // Same message appears twice — once in the batch banner, once on the
      // flagged card itself (asserted specifically below).
      expect(screen.getAllByText(/ถูกแก้ไขหรือถูกลบโดยผู้อื่น/).length).toBeGreaterThanOrEqual(2)
      expect(screen.getByRole('button', { name: 'โหลดข้อมูลล่าสุด' })).toBeInTheDocument()
      // The deleted card stays visible and flagged — never silently wiped.
      expect(screen.getByTestId('trip-card-error-existing-10')).toHaveTextContent('ถูกแก้ไขหรือถูกลบโดยผู้อื่น')
      // Card 11's cleared-to-0 edit is PRESERVED — still '' (never reverted
      // back to '500' by a silent load()).
      expect(screen.getByLabelText('transport m02 existing-11')).toHaveValue('')

      fireEvent.click(screen.getByRole('button', { name: 'โหลดข้อมูลล่าสุด' }))
      await waitFor(() => expect(subformApi.fetchTrips).toHaveBeenCalledTimes(2))
    })

    // RACE FIX (2026-07-19, gate hardening): the guard above used to read
    // the `cards` value CLOSED OVER at the moment deleteTripCard was
    // invoked. If a SIBLING card is edited WHILE this delete's network
    // round-trip is still in flight (nothing disables sibling inputs during
    // a single delete — only save-all's fieldset does that), that closure
    // never sees the fresh edit. The 409 catch would then wrongly conclude
    // "nothing else to lose" and auto-load(), silently discarding it
    // (financial never-cut). Fixed via a ref that always mirrors the
    // latest `cards` state.
    it('a 409 conflict on delete does NOT auto-reload when a sibling card is edited WHILE the delete is in flight (stale-closure race)', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([
        tripItem({ trip_id: 10 }),
        tripItem({ trip_id: 11, updated_at: '2026-02-01T00:00:00' }),
      ])
      vi.mocked(subformApi.fetchDetailLines).mockImplementation(async (_cc, gl) =>
        gl === TRAVEL_GL_BY_TYPE_SIDE.transport.COST ? [detailLine({ trip_id: 11, m02: 500, total_year: 500 })] : [],
      )
      let rejectDelete!: (err: unknown) => void
      vi.mocked(subformApi.deleteTrip).mockImplementation(
        () =>
          new Promise((_resolve, reject) => {
            rejectDelete = reject
          }),
      )
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
      expect(screen.getByTestId('trip-card-existing-11')).toBeInTheDocument()

      // Begin deleting card 10 — deleteTrip is now in flight (pending),
      // and the guard's `cards` closure is fixed at THIS moment: neither
      // card has any unsaved edit yet.
      fireEvent.click(screen.getAllByRole('button', { name: 'ลบทริป' })[0])
      await waitFor(() => expect(subformApi.deleteTrip).toHaveBeenCalled())

      // WHILE the delete is still in flight, edit card 11's persisted
      // manual line down to 0 — an unsaved edit made AFTER the stale
      // closure was captured.
      const input = screen.getByLabelText('transport m02 existing-11')
      expect(input).toHaveValue('500')
      fireEvent.change(input, { target: { value: '0' } })
      expect(input).toHaveValue('')

      // NOW the delete resolves with a 409.
      rejectDelete(new ApiError(409, 'ถูกแก้ไขโดยผู้อื่น'))

      await waitFor(() => expect(screen.getByTestId('trip-card-error-existing-10')).toBeInTheDocument())
      // The guard must see the FRESH edit (via the ref, not the stale
      // closure) — load()/fetchTrips is never auto-called.
      expect(subformApi.fetchTrips).toHaveBeenCalledTimes(1)
      // Same message appears twice — the batch banner AND the flagged card.
      expect(screen.getAllByText(/ถูกแก้ไขหรือถูกลบโดยผู้อื่น/).length).toBeGreaterThanOrEqual(2)
      expect(screen.getByRole('button', { name: 'โหลดข้อมูลล่าสุด' })).toBeInTheDocument()
      // Card 11's edit survives — never silently reverted to the stale '500'.
      expect(screen.getByLabelText('transport m02 existing-11')).toHaveValue('')
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

    it('no-history ฝ่าย → placeholder "— เลือกฝั่ง —"; save-all is blocked by validation until a side is picked, then saves with it', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      vi.mocked(subformApi.createTrip).mockResolvedValue(tripState({ side: 'COST' }))
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

      // No silent default — clicking save-all with no side picked surfaces
      // the same client-side validation every other missing field does.
      fireEvent.click(saveAllButton())
      await waitFor(() => expect(screen.getByText('กรุณาเลือกฝั่งบัญชี')).toBeInTheDocument())
      expect(subformApi.createTrip).not.toHaveBeenCalled()

      fireEvent.change(select, { target: { value: 'COST' } })
      fireEvent.click(saveAllButton())
      await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalled())
      expect(vi.mocked(subformApi.createTrip).mock.calls[0][0].side).toBe('COST')
    })
  })

  it('calls onClose when ยกเลิก is clicked on a clean (non-dirty) modal — no confirm prompt', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
    mockNoManualLines()
    const onClose = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm')
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={onClose} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }))
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('ยกเลิก confirms in Thai before closing when there are unsaved edits; cancelling the confirm keeps the modal open', async () => {
    vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
    mockNoManualLines()
    const onClose = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={onClose} onSaved={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('days existing-10'), { target: { value: '9' } })
    fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }))

    expect(confirmSpy).toHaveBeenCalledWith('มีข้อมูลที่ยังไม่บันทึก ต้องการปิดโดยไม่บันทึก?')
    expect(onClose).not.toHaveBeenCalled() // confirm returned false — stayed open

    confirmSpy.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'ยกเลิก' }))
    expect(onClose).toHaveBeenCalledTimes(1)

    confirmSpy.mockRestore()
  })

  describe('save-all consolidation (2026-07-19)', () => {
    it('NEVER-CUT REGRESSION GUARD: save-all on a brand-new trip with manual expense data threads the trip_id from the createTrip RESPONSE into saveDetailLine — never from stale state', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      vi.mocked(subformApi.createTrip).mockResolvedValue(tripState({ trip_id: 77, side: 'SGA' }))
      vi.mocked(subformApi.saveDetailLine).mockResolvedValue(
        detailLine({ trip_id: 77, gl_account: TRAVEL_GL_BY_TYPE_SIDE.transport.SGA, m05: 1500, total_year: 1500 }),
      )
      const onSaved = vi.fn()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={onSaved} />)
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      fillNewTripBasics() // traveler E9, days 3, month "May" (05), destination ประเทศไทย
      fireEvent.change(screen.getByLabelText('transport m05 new-0'), { target: { value: '1500' } })

      fireEvent.click(saveAllButton())

      await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalledTimes(1))
      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalledTimes(1))
      const linePayload = vi.mocked(subformApi.saveDetailLine).mock.calls[0][0]
      expect(linePayload.trip_id).toBe(77) // threaded from the createTrip RESPONSE
      expect(linePayload.gl_account).toBe(TRAVEL_GL_BY_TYPE_SIDE.transport.SGA)
      expect(linePayload.m05).toBe(1500)
      expect(onSaved).toHaveBeenCalledTimes(1) // one refetch for the whole batch
    })

    it('save-all across TWO new cards saves both trips and their manual lines in one click', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      vi.mocked(subformApi.createTrip)
        .mockResolvedValueOnce(tripState({ trip_id: 201, traveler_empcode: 'E9', side: 'SGA' }))
        .mockResolvedValueOnce(tripState({ trip_id: 202, traveler_empcode: 'E7', side: 'SGA' }))
      vi.mocked(subformApi.saveDetailLine)
        .mockResolvedValueOnce(detailLine({ trip_id: 201, gl_account: TRAVEL_GL_BY_TYPE_SIDE.transport.SGA, m05: 700, total_year: 700 }))
        .mockResolvedValueOnce(detailLine({ trip_id: 202, gl_account: TRAVEL_GL_BY_TYPE_SIDE.transport.SGA, m05: 300, total_year: 300 }))
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      fillNewTripBasics('new-0', 0)
      fireEvent.change(screen.getByLabelText('transport m05 new-0'), { target: { value: '700' } })

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      fireEvent.change(screen.getByLabelText('traveler_empcode new-1'), { target: { value: 'E7' } })
      fireEvent.change(screen.getByLabelText('days new-1'), { target: { value: '2' } })
      fireEvent.click(screen.getAllByRole('button', { name: 'May' })[1])
      fireEvent.change(screen.getByLabelText('destination new-1'), { target: { value: 'ประเทศไทย' } })
      fireEvent.change(screen.getByLabelText('transport m05 new-1'), { target: { value: '300' } })

      fireEvent.click(saveAllButton())

      await waitFor(() => expect(subformApi.createTrip).toHaveBeenCalledTimes(2))
      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalledTimes(2))
      const line1 = vi.mocked(subformApi.saveDetailLine).mock.calls[0][0]
      const line2 = vi.mocked(subformApi.saveDetailLine).mock.calls[1][0]
      expect(line1.trip_id).toBe(201)
      expect(line1.m05).toBe(700)
      expect(line2.trip_id).toBe(202)
      expect(line2.m05).toBe(300)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-201')).toBeInTheDocument())
      expect(screen.getByTestId('trip-card-existing-202')).toBeInTheDocument()
    })

    it('PARTIAL FAILURE: one card fails client-side validation while the other still saves — the batch is never aborted', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      vi.mocked(subformApi.createTrip).mockResolvedValue(tripState({ trip_id: 55 }))
      const onSaved = vi.fn()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={onSaved} />)
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

      // Card new-0: left blank (invalid — no traveler).
      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      // Card new-1: fully filled (valid).
      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))
      fireEvent.change(screen.getByLabelText('traveler_empcode new-1'), { target: { value: 'E9' } })
      fireEvent.change(screen.getByLabelText('days new-1'), { target: { value: '3' } })
      fireEvent.click(screen.getAllByRole('button', { name: 'May' })[1])
      fireEvent.change(screen.getByLabelText('destination new-1'), { target: { value: 'ประเทศไทย' } })

      fireEvent.click(saveAllButton())

      await waitFor(() => expect(screen.getByTestId('trip-card-error-new-0')).toHaveTextContent('กรุณาระบุผู้เดินทาง'))
      expect(subformApi.createTrip).toHaveBeenCalledTimes(1) // only the valid card was attempted
      expect(onSaved).toHaveBeenCalled() // the valid card's write still succeeded
      expect(screen.getByTestId('trip-card-new-0')).toBeInTheDocument() // invalid card is KEPT, not dropped
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-55')).toBeInTheDocument())
    })

    it('disables every input/select/button inside the trip cards while a save-all batch is in flight', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
      mockNoManualLines()
      let resolveUpdate!: (value: Awaited<ReturnType<typeof subformApi.updateTrip>>) => void
      vi.mocked(subformApi.updateTrip).mockImplementation(
        () => new Promise((resolve) => { resolveUpdate = resolve }),
      )
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      fireEvent.change(screen.getByLabelText('days existing-10'), { target: { value: '9' } })
      fireEvent.click(saveAllButton())

      await waitFor(() => expect(saveAllButton()).toBeDisabled())
      expect(screen.getByLabelText('days existing-10')).toBeDisabled()
      expect(screen.getByRole('button', { name: 'ลบทริป' })).toBeDisabled()
      expect(screen.getByRole('button', { name: /เพิ่มทริป/ })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'ยกเลิก' })).toBeDisabled()

      resolveUpdate({ ...tripItem(), days: 9 } as never)
      await waitFor(() => expect(saveAllButton()).toBeEnabled())
    })

    it('a 409 on one card during save-all annotates that card and shows a batch conflict banner with an explicit reload button (never auto-reloads)', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
      mockNoManualLines()
      vi.mocked(subformApi.updateTrip).mockRejectedValue(new ApiError(409, 'ถูกแก้ไขโดยผู้อื่น'))
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      fireEvent.change(screen.getByLabelText('days existing-10'), { target: { value: '9' } })
      fireEvent.click(saveAllButton())

      await waitFor(() => expect(screen.getByTestId('trip-card-error-existing-10')).toBeInTheDocument())
      expect(screen.getByText(/บางรายการถูกแก้ไขโดยผู้อื่น/)).toBeInTheDocument()
      expect(subformApi.fetchTrips).toHaveBeenCalledTimes(1) // NOT auto-reloaded

      fireEvent.click(screen.getByRole('button', { name: 'โหลดข้อมูลล่าสุด' }))
      await waitFor(() => expect(subformApi.fetchTrips).toHaveBeenCalledTimes(2))
    })

    it('a NEW manual line typed then cleared back to zero is never written (no spurious row)', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      const input = screen.getByLabelText('transport m02 existing-10')
      fireEvent.change(input, { target: { value: '500' } })
      fireEvent.change(input, { target: { value: '0' } })

      fireEvent.click(saveAllButton())

      await waitFor(() => expect(saveAllButton()).toBeEnabled())
      expect(subformApi.saveDetailLine).not.toHaveBeenCalled()
    })

    it('editing an EXISTING manual line down to all-zero still saves it (server zeroes the row — never silently skipped)', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
      vi.mocked(subformApi.fetchDetailLines).mockImplementation(async (_cc, gl) =>
        gl === TRAVEL_GL_BY_TYPE_SIDE.transport.COST ? [detailLine({ m02: 500, total_year: 500 })] : [],
      )
      vi.mocked(subformApi.saveDetailLine).mockResolvedValue(detailLine({ m02: 0, total_year: 0 }))
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      const input = screen.getByLabelText('transport m02 existing-10')
      expect(input).toHaveValue('500')
      fireEvent.change(input, { target: { value: '0' } })

      fireEvent.click(saveAllButton())

      await waitFor(() => expect(subformApi.saveDetailLine).toHaveBeenCalled())
      const payload = vi.mocked(subformApi.saveDetailLine).mock.calls[0][0]
      expect(payload.detail_id).toBe(1) // existing row — an UPDATE, never a second INSERT
      expect(payload.m02).toBe(0)
    })
  })

  // 2026-07-19 restyle (mockup 0002.3 gridgeist parity) — new structural
  // assertions for the intro legend, GL-code column, and the per-diem row's
  // read-only-forever guarantee (financial never-cut).
  describe('gridgeist restyle — legend, section labels, GL column, read-only per-diem', () => {
    it('renders the intro legend banner exactly once, even with multiple trip cards', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem(), tripItem({ trip_id: 11, updated_at: '2026-02-01T00:00:00' })])
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())
      expect(screen.getByTestId('trip-card-existing-11')).toBeInTheDocument()

      expect(screen.getAllByTestId('trip-legend')).toHaveLength(1)
      expect(screen.getByText(/1 ทริป = กรอกครั้งเดียว/)).toBeInTheDocument()
    })

    it('renders section labels A (main info) and B (4 expense types) inside a trip card', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      expect(screen.getByText(/A — ข้อมูลหลัก/)).toBeInTheDocument()
      expect(screen.getByText(/B — ค่าใช้จ่าย 4 ประเภท/)).toBeInTheDocument()
    })

    it('the per-diem row has NO editable inputs — every active-month cell is a read-only span', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()]) // travel_months ['02','03']
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      const perDiemRow = screen.getByTestId('per-diem-row-existing-10')
      expect(within(perDiemRow).queryAllByRole('textbox')).toHaveLength(0)
      // The active months' values ARE rendered read-only, with a title
      // explaining they are server-computed.
      const feb = screen.getByTestId('per-diem-value-m02-existing-10')
      expect(feb.tagName).toBe('SPAN')
      expect(feb).toHaveAttribute('title', expect.stringContaining('เซิร์ฟเวอร์'))
    })

    it('the per-diem row and manual rows each show their own GL code for the trip side', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()]) // side: COST
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      expect(within(screen.getByTestId('per-diem-row-existing-10')).getByText(TRAVEL_GL_BY_TYPE_SIDE.per_diem.COST)).toBeInTheDocument()
      expect(screen.getByText(TRAVEL_GL_BY_TYPE_SIDE.transport.COST)).toBeInTheDocument()
      expect(screen.getByText(TRAVEL_GL_BY_TYPE_SIDE.accommodation.COST)).toBeInTheDocument()
      expect(screen.getByText(TRAVEL_GL_BY_TYPE_SIDE.other.COST)).toBeInTheDocument()
    })

    it('the รายละเอียด field is disabled (no backing model field yet) with an explanatory title', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([tripItem()])
      mockNoManualLines()
      render(<TripManager costCenter="CC1" fiscalYear={2027} sideHistory={BOTH_SIDES} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />)
      await waitFor(() => expect(screen.getByTestId('trip-card-existing-10')).toBeInTheDocument())

      const detailInput = screen.getByLabelText('trip-detail-note existing-10')
      expect(detailInput).toBeDisabled()
      expect(detailInput).toHaveAttribute('title', expect.stringContaining('ยังไม่รองรับ'))
      expect(detailInput).toHaveAttribute('placeholder', expect.stringContaining('ค่าวีซ่า'))
    })

    // Option B (2026-07-19 save-all consolidation): a brand-new trip now
    // renders its expense table immediately — one click both creates the
    // trip AND persists its manual lines, so the table can't stay hidden
    // until "after" a separate save. GL chips show "—" until a side is set.
    it('a brand-new (unsaved) trip renders the expense table right away, with GL placeholders until a side is picked', async () => {
      vi.mocked(subformApi.fetchTrips).mockResolvedValue([])
      mockNoManualLines()
      render(
        <TripManager costCenter="CC1" fiscalYear={2027} sideHistory={{ sides: [], defaultSide: null }} isAdmin={false} onClose={vi.fn()} onSaved={vi.fn()} />,
      )
      await waitFor(() => expect(screen.getByText(/ยังไม่มีทริป/)).toBeInTheDocument())

      fireEvent.click(screen.getByRole('button', { name: /เพิ่มทริป/ }))

      const perDiemRow = screen.getByTestId('per-diem-row-new-0')
      expect(perDiemRow).toBeInTheDocument()
      expect(screen.getByText(/ระบบจะคำนวณให้หลังกดบันทึก/)).toBeInTheDocument()
      expect(within(perDiemRow).getByText('—', { selector: '.exp-gl-chip' })).toBeInTheDocument()
    })
  })
})
