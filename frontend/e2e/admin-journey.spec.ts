/** Admin (ผู้ดูแลระบบ) end-to-end journey — dual-role admin toggle (ADR-0014,
 * default OFF, re-auto-selects the first ฝ่าย of the new scope after a
 * hat-switch (jakkaritw decision 2026-07-24 — the 2026-07-21 "never land
 * unselected" rule applies after toggling too), persists across reload),
 * attachments upload/list/download, and a pure admin's always-on wide-open
 * view. */
import { CC, CC2, C_LEVEL, DEEP_LINK_YEAR, DEPT, DEPT2, DIVISION, dualRoleAdminWorld, installMocks, ok, PLANNING_YEAR, pureAdminWorld, parseMultipartFields, test, expect } from './fixtures'

test.describe('admin journey', () => {
  test('3.1 the admin toggle is OFF by default, switches admin_view_enabled on refetch, re-auto-selects the first ฝ่าย of the new scope, and persists across reload', async ({ page }) => {
    // No ?dept= deep link (ADR-0016: a deep link still valid in the new
    // scope would win the re-resolution). Personal scope = [DEPT] only;
    // the admin-wide list is swapped in BEFORE the click so the refetch
    // returns [DEPT2, DEPT] — the picker must then land on DEPT2 (first in
    // hierarchy order), NOT on the previously-picked DEPT.
    const world = dualRoleAdminWorld({ budgetGridQueue: [[]] })
    await installMocks(page, world)

    await page.goto('/')
    await expect(page.getByRole('button', { name: DEPT })).toBeVisible()

    await expect.poll(() => world.captured.budgetQueries.length).toBeGreaterThan(0)
    expect(world.captured.budgetQueries[0].admin_view_enabled).toBe('false')

    world.departments = [
      { cost_center: CC2, department: DEPT2, division: DIVISION, c_level: C_LEVEL },
      { cost_center: CC, department: DEPT, division: DIVISION, c_level: C_LEVEL },
    ]

    const toggle = page.getByTestId('admin-mode-checkbox')
    await expect(toggle).not.toBeChecked()
    // The checkbox itself is visually hidden by the custom switch styling
    // (`.admin-toggle-sw`) — click the enclosing <label> (the visible
    // control), which natively toggles the nested input, exactly like a
    // real user would.
    await page.getByTestId('admin-mode-toggle').click()
    await expect(toggle).toBeChecked()

    await expect.poll(() => world.captured.budgetQueries.at(-1)?.admin_view_enabled).toBe('true')
    await expect.poll(() => world.captured.departmentsQueries.at(-1)?.admin_view_enabled).toBe('true')
    // 2026-07-24 decision: the "never land unselected" rule applies after a
    // hat-switch too — the first ฝ่าย of the new scope is auto-selected, the
    // placeholder never appears.
    await expect(page.getByRole('button', { name: DEPT2 })).toBeVisible()
    await expect(page.getByRole('button', { name: '— เลือกฝ่าย —' })).toHaveCount(0)

    await page.reload()
    await expect(page.getByTestId('admin-mode-checkbox')).toBeChecked() // sessionStorage persists
  })

  test('3.2 attachments: upload captures the multipart fields, the list refreshes, and download uses the mocked URL', async ({ page }) => {
    const uploadedItem = { item_id: 'a1', name: 'invoice.pdf', size: 2048, created_by: 'admin.dual@chememan.com', created_at: '2027-01-01T00:00:00Z', web_url: null }
    const world = dualRoleAdminWorld({
      budgetGridQueue: [[]],
      attachments: [], // empty until the upload's onServed hook appends it — mirrors a real backend, immune to StrictMode's extra mount-triggered reads
      uploadQueue: [ok(uploadedItem, () => world.attachments.push(uploadedItem))],
      downloadUrl: 'https://cmandwprd.sharepoint.com/mock-download/invoice.pdf?sig=abc',
    })
    await installMocks(page, world)
    await page.addInitScript(() => {
      // @ts-expect-error test-only capture hook
      window.__openedUrls = []
      const originalOpen = window.open.bind(window)
      window.open = (url?: string | URL, ...rest: unknown[]) => {
        // @ts-expect-error test-only capture hook
        window.__openedUrls.push(String(url))
        return originalOpen(url as string, ...(rest as []))
      }
    })

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    await page.getByRole('button', { name: 'แนบไฟล์' }).click()
    await expect(page.getByTestId('attachments-modal')).toBeVisible()
    await expect(page.getByText('ยังไม่มีไฟล์ในโฟลเดอร์นี้')).toBeVisible()

    await page.getByTestId('attachments-upload-input').setInputFiles({
      name: 'invoice.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4 fixture'),
    })

    await expect.poll(() => world.captured.uploadRaw.length).toBeGreaterThan(0)
    const fields = parseMultipartFields(world.captured.uploadRaw.at(-1)!)
    expect(fields.department).toBe(DEPT)
    expect(fields.fiscal_year).toBe(String(PLANNING_YEAR))
    expect(fields.filename).toBe('invoice.pdf')

    await expect(page.getByTestId('attachments-item-a1')).toContainText('invoice.pdf')

    await page.getByRole('button', { name: 'เปิด/ดาวน์โหลด' }).click()
    await expect
      .poll(async () => page.evaluate(() => (window as unknown as { __openedUrls: string[] }).__openedUrls))
      .toEqual(['https://cmandwprd.sharepoint.com/mock-download/invoice.pdf?sig=abc'])
  })

  test('3.3 a pure admin (no Fill/See) sees the grid wide-open from the start, with NO admin toggle rendered', async ({ page }) => {
    const world = pureAdminWorld({ budgetGridQueue: [[]] })
    await installMocks(page, world)

    await page.goto('/')

    await expect(page.getByTestId('admin-mode-toggle')).toHaveCount(0)
    await expect.poll(() => world.captured.budgetQueries.length).toBeGreaterThan(0)
    expect(world.captured.budgetQueries[0].admin_view_enabled).toBe('true')
  })
})
