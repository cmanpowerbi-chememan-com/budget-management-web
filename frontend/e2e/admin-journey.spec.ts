/** Admin (ผู้ดูแลระบบ) end-to-end journey — dual-role admin toggle (ADR-0014,
 * default OFF, resets the selected ฝ่าย, persists across reload), attachments
 * upload/list/download, and a pure admin's always-on wide-open view. */
import { DEPT, dualRoleAdminWorld, installMocks, ok, PLANNING_YEAR, pureAdminWorld, parseMultipartFields, test, expect } from './fixtures'

test.describe('admin journey', () => {
  test('3.1 the admin toggle is OFF by default, switches admin_view_enabled on refetch, resets the ฝ่าย, and persists across reload', async ({ page }) => {
    const world = dualRoleAdminWorld({ budgetGridQueue: [[]] })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${PLANNING_YEAR}`)
    await expect(page.getByRole('button', { name: DEPT })).toBeVisible()

    await expect.poll(() => world.captured.budgetQueries.length).toBeGreaterThan(0)
    expect(world.captured.budgetQueries[0].admin_view_enabled).toBe('false')

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
    await expect(page.getByRole('button', { name: '— เลือกฝ่าย —' })).toBeVisible() // ADR-0014 reset

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

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${PLANNING_YEAR}`)
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
