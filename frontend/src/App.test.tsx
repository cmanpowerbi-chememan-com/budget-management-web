import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function mockAuthAndScope() {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/me')) {
        return Promise.resolve(jsonResponse(200, { email: 'user@chememan.com', app_env: 'local' }))
      }
      if (url.includes('/scope/departments')) {
        return Promise.resolve(
          jsonResponse(200, [
            { cost_center: '10CA013000', department: 'ฝ่ายบัญชี', division: 'Div A', c_level: 'CTO' },
          ]),
        )
      }
      if (url.includes('/scope')) {
        return Promise.resolve(
          jsonResponse(200, {
            email: 'user@chememan.com',
            is_admin: false,
            role: 'filler',
            fill_cost_centers: ['10CA013000'],
            see_cost_centers: ['10CA013000', '10CA013001'],
          }),
        )
      }
      if (url.includes('/budget/gl-accounts')) {
        return Promise.resolve(jsonResponse(200, []))
      }
      if (url.includes('/budget')) {
        return Promise.resolve(jsonResponse(200, []))
      }
      return Promise.reject(new Error(`unexpected fetch in test: ${url}`))
    }),
  )
}

describe('App shell + budget grid (A7/A8)', () => {
  beforeEach(() => {
    mockAuthAndScope()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.history.pushState({}, '', '/')
  })

  it('mounts the real budget grid (ฝ่าย picker + year picker) once auth/scope resolve', async () => {
    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: /เพิ่ม transaction/i })).toBeInTheDocument())
    expect(screen.getByRole('combobox', { name: /ปีงบประมาณ/ })).toBeInTheDocument()
  })

  it('pre-fills the ฝ่าย picker from the ADR-0016 deep-link when the department is in the caller\'s scope', async () => {
    const currentYear = new Date().getFullYear()
    window.history.pushState({}, '', `/?dept=ฝ่ายบัญชี&year=${currentYear}`)

    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: 'ฝ่ายบัญชี' })).toBeInTheDocument())
  })

  it('shows the resolved user email, name, and Fill scope (division/ฝ่าย/CC pill) in the V3 header', async () => {
    render(<App />)

    await waitFor(() => expect(screen.getByText('user@chememan.com')).toBeInTheDocument())
    expect(screen.getByText('user')).toBeInTheDocument() // name = email local-part
    await waitFor(() => expect(screen.getByText('Div A')).toBeInTheDocument()) // สายงาน from /scope/departments
    expect(screen.getByText('ฝ่ายบัญชี')).toBeInTheDocument()
    expect(screen.getByText('Cost Centers')).toBeInTheDocument()
    // Fill CC pill = 1 (fill_cost_centers), never a See count anywhere in the header.
    expect(screen.getByTestId('v3-cc-count')).toHaveTextContent('1')
    expect(screen.queryByText('See')).not.toBeInTheDocument()
  })

  it('shows a Thai error banner (and no grid) when /me succeeds but /scope fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/me')) {
          return Promise.resolve(jsonResponse(200, { email: 'user@chememan.com', app_env: 'local' }))
        }
        if (url.includes('/scope')) {
          return Promise.resolve(jsonResponse(500, { detail: 'scope lookup failed' }))
        }
        return Promise.reject(new Error(`unexpected fetch in test: ${url}`))
      }),
    )

    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('โหลดข้อมูลสิทธิ์ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง')).toBeInTheDocument(),
    )
    expect(screen.queryByRole('combobox', { name: /ปีงบประมาณ/ })).not.toBeInTheDocument()
  })
})
