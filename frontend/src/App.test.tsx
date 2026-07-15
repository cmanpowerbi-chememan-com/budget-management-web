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
      return Promise.reject(new Error(`unexpected fetch in test: ${url}`))
    }),
  )
}

describe('App shell (A7)', () => {
  beforeEach(() => {
    mockAuthAndScope()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.history.pushState({}, '', '/')
  })

  it('shows the deep-link filter chip when ?dept and ?year are present (ADR-0016)', async () => {
    const currentYear = new Date().getFullYear()
    window.history.pushState({}, '', `/?dept=ฝ่ายบัญชี&year=${currentYear}`)

    render(<App />)

    await waitFor(() => expect(screen.getByTestId('filter-chip')).toHaveTextContent('ฝ่ายบัญชี'))
    expect(screen.getByTestId('filter-chip')).toHaveTextContent(String(currentYear))
  })

  it('shows the empty-filter placeholder with no deep-link params', async () => {
    window.history.pushState({}, '', '/')

    render(<App />)

    await waitFor(() => expect(screen.getByTestId('filter-chip')).toBeInTheDocument())
    expect(screen.getByTestId('filter-chip')).toHaveClass('filter-chip-empty')
    expect(screen.getByTestId('filter-chip')).not.toHaveTextContent('🔗')
  })

  it('renders the grid placeholder — the real grid arrives in A8', () => {
    render(<App />)

    expect(screen.getByTestId('grid-placeholder')).toBeInTheDocument()
  })

  it('shows the resolved user email and Fill/See CC counts once loaded', async () => {
    render(<App />)

    await waitFor(() => expect(screen.getByText('user@chememan.com')).toBeInTheDocument())
    expect(screen.getByText('1 CC')).toBeInTheDocument()
    expect(screen.getByText('2 CC')).toBeInTheDocument()
  })
})
