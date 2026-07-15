import { afterEach, describe, expect, it, vi } from 'vitest'
import { approveDepartment, fetchApprovalStatus, fetchPendingForMe, rejectDepartment, submitDepartment } from './approval'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('fetchApprovalStatus', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /approval/status with department + fiscal_year query params', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { status: 'DRAFT' }))
    vi.stubGlobal('fetch', fetchSpy)

    await fetchApprovalStatus('ฝ่ายบัญชี', 2027)

    const url = String(fetchSpy.mock.calls[0][0])
    expect(url).toContain('/approval/status?')
    expect(url).toContain(encodeURIComponent('ฝ่ายบัญชี'))
    expect(url).toContain('fiscal_year=2027')
  })
})

describe('submitDepartment', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('POSTs to /approval/submit with department + fiscal_year', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { status: 'PENDING_APPROVER1' }))
    vi.stubGlobal('fetch', fetchSpy)

    const result = await submitDepartment('Accounting', 2027)

    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/approval/submit')
    expect((init as RequestInit).method).toBe('POST')
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ department: 'Accounting', fiscal_year: 2027 })
    expect(result.status).toBe('PENDING_APPROVER1')
  })
})

describe('approveDepartment', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('POSTs to /approval/approve with an optional comment', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { status: 'APPROVED' }))
    vi.stubGlobal('fetch', fetchSpy)

    await approveDepartment('Accounting', 2027, 'looks good')

    const [, init] = fetchSpy.mock.calls[0]
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      department: 'Accounting', fiscal_year: 2027, comment: 'looks good',
    })
  })

  it('sends comment: null when none is given', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { status: 'APPROVED' }))
    vi.stubGlobal('fetch', fetchSpy)

    await approveDepartment('Accounting', 2027)

    const [, init] = fetchSpy.mock.calls[0]
    expect(JSON.parse((init as RequestInit).body as string).comment).toBeNull()
  })
})

describe('rejectDepartment', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('POSTs to /approval/reject with the required reason', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { status: 'REJECTED' }))
    vi.stubGlobal('fetch', fetchSpy)

    await rejectDepartment('Accounting', 2027, 'ตัวเลขไม่ถูกต้อง')

    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/approval/reject')
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      department: 'Accounting', fiscal_year: 2027, reason: 'ตัวเลขไม่ถูกต้อง',
    })
  })
})

describe('fetchPendingForMe', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /approval/pending-for-me with fiscal_year', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { departments: ['Accounting'] }))
    vi.stubGlobal('fetch', fetchSpy)

    const result = await fetchPendingForMe(2027)

    expect(String(fetchSpy.mock.calls[0][0])).toContain('/approval/pending-for-me?fiscal_year=2027')
    expect(result.departments).toEqual(['Accounting'])
  })
})
