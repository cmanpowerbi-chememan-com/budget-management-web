import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ScopeState } from '../auth/useScope'
import { UserBar } from './UserBar'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function stubFetch(handlers: { departments?: unknown; budget?: unknown; departmentsStatus?: number; budgetStatus?: number }) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/scope/departments')) {
        return Promise.resolve(jsonResponse(handlers.departmentsStatus ?? 200, handlers.departments ?? []))
      }
      if (url.includes('/budget')) {
        return Promise.resolve(jsonResponse(handlers.budgetStatus ?? 200, handlers.budget ?? []))
      }
      return Promise.reject(new Error(`unexpected fetch in test: ${url}`))
    }),
  )
}

function scope(overrides: Partial<ScopeState> = {}): ScopeState {
  return {
    role: 'filler',
    isAdmin: false,
    fillCostCenters: [],
    seeCostCenters: [],
    email: null,
    loading: false,
    error: null,
    ...overrides,
  }
}

describe('UserBar', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('shows the loading status while auth/scope are still resolving', () => {
    stubFetch({})
    render(<UserBar email={null} authLoading authError={null} scope={scope({ loading: true })} />)

    expect(screen.getByTestId('user-bar')).toBeInTheDocument()
    expect(screen.getByText('กำลังโหลดข้อมูลผู้ใช้…')).toBeInTheDocument()
  })

  it('shows the Thai auth error banner', () => {
    stubFetch({})
    render(<UserBar email={null} authLoading={false} authError="boom" scope={scope()} />)

    expect(screen.getByText('โหลดข้อมูลผู้ใช้ไม่สำเร็จ — กรุณาลองรีเฟรชหน้าใหม่')).toBeInTheDocument()
  })

  it('shows the Thai scope error banner', () => {
    stubFetch({})
    render(<UserBar email={null} authLoading={false} authError={null} scope={scope({ error: 'boom' })} />)

    expect(screen.getByText('โหลดข้อมูลสิทธิ์ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง')).toBeInTheDocument()
  })

  it('renders avatar initials, email-local name, email, and ONE Thai role badge for a filler', async () => {
    stubFetch({
      departments: [{ cost_center: '10CA013000', department: 'ฝ่ายบัญชี', division: 'สายงานการเงิน', c_level: null }],
    })

    render(
      <UserBar
        email="anurakb@chememan.com"
        authLoading={false}
        authError={null}
        scope={scope({ fillCostCenters: ['10CA013000'], seeCostCenters: ['10CA013000', '10CA013001'] })}
      />,
    )

    expect(screen.getByText('anurakb')).toBeInTheDocument() // name = email local-part
    expect(screen.getByText('anurakb@chememan.com')).toBeInTheDocument()
    expect(screen.getByText('ผู้กรอกงบประมาณ')).toBeInTheDocument() // Thai roleLabel, the only badge
    expect(screen.queryByText('USER')).not.toBeInTheDocument()
    expect(screen.queryByText('Admin')).not.toBeInTheDocument()
    expect(screen.getByText('AN')).toBeInTheDocument() // initials from "anurakb"

    await waitFor(() => expect(screen.getByText('สายงานการเงิน')).toBeInTheDocument())
    expect(screen.getByText('ฝ่ายบัญชี')).toBeInTheDocument()
  })

  it('never shows a See-scope count anywhere in the header (Fill-only by design)', async () => {
    stubFetch({
      departments: [{ cost_center: '10CA013000', department: 'ฝ่ายบัญชี', division: 'สายงานการเงิน', c_level: null }],
    })

    render(
      <UserBar
        email="anurakb@chememan.com"
        authLoading={false}
        authError={null}
        scope={scope({ fillCostCenters: ['10CA013000'], seeCostCenters: ['10CA013000', '10CA013001', 'X', 'Y'] })}
      />,
    )

    await waitFor(() => expect(screen.getByText('ฝ่ายบัญชี')).toBeInTheDocument())
    expect(screen.queryByText('See')).not.toBeInTheDocument()
    expect(screen.queryByText('4')).not.toBeInTheDocument() // the See count, must never render
  })

  it('shows the Fill Cost Centers pill count immediately (no fetch needed) and the ฝ่าย count/chips', async () => {
    stubFetch({
      departments: [
        { cost_center: 'CC1', department: 'ฝ่ายบัญชี', division: 'สายงานการเงิน', c_level: null },
        { cost_center: 'CC2', department: 'ฝ่ายการเงิน', division: 'สายงานการเงิน', c_level: null },
      ],
    })

    render(
      <UserBar
        email="user@chememan.com"
        authLoading={false}
        authError={null}
        scope={scope({ fillCostCenters: ['CC1', 'CC2'] })}
      />,
    )

    expect(screen.getByText('Cost Centers')).toBeInTheDocument()
    expect(screen.getByTestId('v3-cc-count')).toHaveTextContent('2') // Fill CC count, immediate

    await waitFor(() => expect(screen.getByText('ฝ่ายการเงิน')).toBeInTheDocument())
    expect(screen.getByText('ฝ่ายบัญชี')).toBeInTheDocument()
    expect(screen.getByTestId('v3-dept-count')).toHaveTextContent('2')
  })

  it('shows "…" for the GL Codes pill while loading, then the resolved distinct count', async () => {
    let resolveBudget!: (rows: unknown) => void
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/scope/departments')) return Promise.resolve(jsonResponse(200, []))
        if (url.includes('/budget')) {
          return new Promise((resolve) => {
            resolveBudget = (rows) => resolve(jsonResponse(200, rows))
          })
        }
        return Promise.reject(new Error(`unexpected fetch in test: ${url}`))
      }),
    )

    render(
      <UserBar email="user@chememan.com" authLoading={false} authError={null} scope={scope({ fillCostCenters: ['CC1'] })} />,
    )

    expect(screen.getByText('GL Codes')).toBeInTheDocument()
    expect(screen.getByTestId('v3-gl-count')).toHaveTextContent('…')

    resolveBudget([
      { cost_center: 'CC1', gl_account: 'GL1', sap: {}, board: {}, pending: {}, editable: true },
      { cost_center: 'CC1', gl_account: 'GL2', sap: {}, board: {}, pending: {}, editable: true },
    ])

    await waitFor(() => expect(screen.getByTestId('v3-gl-count')).toHaveTextContent('2'))
  })

  // laddawank-no-division-chip: a manager with no Fill scope (not a Filler
  // anywhere) but a real See scope shows her real สายงาน/ฝ่าย instead of
  // "ไม่ระบุสายงาน", while still NOT getting the Fill-only Cost
  // Centers/GL Codes pills — the existing "ดูอย่างเดียว" role badge (not a
  // new label) is what marks this as viewing, not editing.
  it('See-only user (empty Fill, real See scope) shows their real สายงาน/ฝ่าย, not "ไม่ระบุสายงาน"', async () => {
    stubFetch({
      departments: [{ cost_center: '10IT011300', department: 'Data & Analytic', division: 'Digital Technology', c_level: null }],
    })

    render(
      <UserBar
        email="laddawank@chememan.com"
        authLoading={false}
        authError={null}
        scope={scope({ role: 'see_only', fillCostCenters: [], seeCostCenters: ['10IT011300'] })}
      />,
    )

    await waitFor(() => expect(screen.getByText('Digital Technology')).toBeInTheDocument())
    expect(screen.queryByText('ไม่ระบุสายงาน')).not.toBeInTheDocument()
    expect(screen.getByText('Data & Analytic')).toBeInTheDocument()
    expect(screen.getByText('ดูอย่างเดียว')).toBeInTheDocument() // existing role badge marks this as view-only
    expect(screen.queryByText('Cost Centers')).not.toBeInTheDocument() // Fill-gated pills stay hidden
    expect(screen.queryByText('GL Codes')).not.toBeInTheDocument()
  })

  it('does not render the ฝ่าย/CC/GL segments at all when the caller has no Fill cost centers', () => {
    stubFetch({ departments: [] })

    render(
      <UserBar
        email="approver@chememan.com"
        authLoading={false}
        authError={null}
        scope={scope({ role: 'see_only', fillCostCenters: [], seeCostCenters: ['CC1'] })}
      />,
    )

    expect(screen.queryByText('Cost Centers')).not.toBeInTheDocument()
    expect(screen.queryByText('GL Codes')).not.toBeInTheDocument()
    expect(screen.getByText('ดูอย่างเดียว')).toBeInTheDocument() // see_only role label still shows
  })

  it('shows the pure-admin "sees everything" note instead of the hierarchy, with no Fill/See fetch triggered', () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    render(
      <UserBar
        email="jakkaritw@chememan.com"
        authLoading={false}
        authError={null}
        scope={scope({ role: 'admin', isAdmin: true, fillCostCenters: [], seeCostCenters: [] })}
      />,
    )

    expect(screen.getByText('เห็นข้อมูลทั้งหมด · ทุก Cost Center')).toBeInTheDocument()
    expect(screen.getByText('ผู้ดูแลระบบ')).toBeInTheDocument()
    expect(screen.queryByText('Cost Centers')).not.toBeInTheDocument()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('shows the full hierarchy (not the allnote) for a dual-role admin who still has their own Fill scope', async () => {
    stubFetch({
      departments: [{ cost_center: 'CC1', department: 'ฝ่ายบัญชี', division: 'สายงานการเงิน', c_level: null }],
    })

    render(
      <UserBar
        email="nipapornt@chememan.com"
        authLoading={false}
        authError={null}
        scope={scope({ role: 'admin', isAdmin: true, fillCostCenters: ['CC1'], seeCostCenters: ['CC1'] })}
      />,
    )

    expect(screen.queryByText('เห็นข้อมูลทั้งหมด · ทุก Cost Center')).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('ฝ่ายบัญชี')).toBeInTheDocument())
  })

  describe('Logout control', () => {
    it('renders a Thai-labelled link that navigates straight to the Easy Auth logout endpoint', () => {
      stubFetch({})
      render(
        <UserBar
          email="anurakb@chememan.com"
          authLoading={false}
          authError={null}
          scope={scope({ fillCostCenters: [], seeCostCenters: [] })}
        />,
      )

      // Asserting the real navigation target (href), not a mocked helper's
      // internals — this is a plain <a>, no onClick/navigate() indirection.
      const link = screen.getByRole('link', { name: 'ออกจากระบบ' })
      expect(link).toHaveAttribute('href', '/.auth/logout')
    })

    it('is keyboard-reachable (a native anchor takes focus without any extra tabIndex wiring)', () => {
      stubFetch({})
      render(<UserBar email="anurakb@chememan.com" authLoading={false} authError={null} scope={scope()} />)

      const link = screen.getByRole('link', { name: 'ออกจากระบบ' })
      link.focus()
      expect(link).toHaveFocus()
    })

    it('still renders for the no-scope role (role="none") — a stuck user needs a way out too', () => {
      stubFetch({})
      render(
        <UserBar
          email="nobody@chememan.com"
          authLoading={false}
          authError={null}
          scope={scope({ role: 'none', isAdmin: false, fillCostCenters: [], seeCostCenters: [] })}
        />,
      )

      expect(screen.getByRole('link', { name: 'ออกจากระบบ' })).toBeInTheDocument()
    })

    it('still renders for a pure admin (the "sees everything" note branch)', () => {
      const fetchSpy = vi.fn()
      vi.stubGlobal('fetch', fetchSpy)
      render(
        <UserBar
          email="jakkaritw@chememan.com"
          authLoading={false}
          authError={null}
          scope={scope({ role: 'admin', isAdmin: true, fillCostCenters: [], seeCostCenters: [] })}
        />,
      )

      expect(screen.getByRole('link', { name: 'ออกจากระบบ' })).toBeInTheDocument()
    })

    it('does NOT render during the initial auth/scope loading status line', () => {
      stubFetch({})
      render(<UserBar email={null} authLoading authError={null} scope={scope({ loading: true })} />)

      expect(screen.queryByRole('link', { name: 'ออกจากระบบ' })).not.toBeInTheDocument()
    })

    it('does NOT render on the auth-error banner (that branch has no other control either)', () => {
      stubFetch({})
      render(<UserBar email={null} authLoading={false} authError="boom" scope={scope()} />)

      expect(screen.queryByRole('link', { name: 'ออกจากระบบ' })).not.toBeInTheDocument()
    })

    it('does NOT render on the scope-error banner (that branch has no other control either)', () => {
      stubFetch({})
      render(<UserBar email={null} authLoading={false} authError={null} scope={scope({ error: 'boom' })} />)

      expect(screen.queryByRole('link', { name: 'ออกจากระบบ' })).not.toBeInTheDocument()
    })
  })
})
