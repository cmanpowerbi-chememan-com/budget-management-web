import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchAttachments, fetchDownloadUrl, uploadAttachment } from './attachments'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('fetchAttachments', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /attachments with department + fiscal_year', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, []))
    vi.stubGlobal('fetch', fetchSpy)

    await fetchAttachments('ฝ่ายบัญชี', 2027)

    const url = String(fetchSpy.mock.calls[0][0])
    expect(url).toContain('/attachments?')
    expect(url).toContain(encodeURIComponent('ฝ่ายบัญชี'))
    expect(url).toContain('fiscal_year=2027')
  })

  it('returns the parsed list', async () => {
    const items = [{ item_id: '1', name: 'a.pdf', size: 10, created_by: null, created_at: null, web_url: null }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, items)))

    await expect(fetchAttachments('Accounting', 2027)).resolves.toEqual(items)
  })
})

describe('uploadAttachment', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('POSTs multipart form data to /attachments/upload', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse(200, { item_id: '1', name: 'a.pdf', size: 3, created_by: null, created_at: null, web_url: null }),
    )
    vi.stubGlobal('fetch', fetchSpy)
    const file = new File([new Uint8Array([1, 2, 3])], 'a.pdf', { type: 'application/pdf' })

    const result = await uploadAttachment('Accounting', 2027, file)

    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/attachments/upload')
    expect((init as RequestInit).method).toBe('POST')
    const form = (init as RequestInit).body as FormData
    expect(form.get('department')).toBe('Accounting')
    expect(form.get('fiscal_year')).toBe('2027')
    expect(form.get('file')).toBe(file)
    expect(result.item_id).toBe('1')
  })
})

describe('fetchDownloadUrl', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('calls GET /attachments/download-url and returns the url string', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, { url: 'https://download.example/x' }))
    vi.stubGlobal('fetch', fetchSpy)

    const url = await fetchDownloadUrl('Accounting', 2027, 'item-1')

    expect(String(fetchSpy.mock.calls[0][0])).toContain('/attachments/download-url?')
    expect(url).toBe('https://download.example/x')
  })
})
