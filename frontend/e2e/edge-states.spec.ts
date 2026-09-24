/** Edge-state journeys — no-scope empty state, SAP outage (loud error, never
 * a silent empty grid), a /scope failure banner, an out-of-scope deep-link
 * dept being safely ignored, and the two specific 403 Thai messages
 * (past_deadline / department_locked) mapped in `src/api/client.ts`. */
import { CC, DEEP_LINK_YEAR, DEPT, err, fillerWorld, GL_OFFICE_COST, GL_TRAVEL_PERDIEM_COST, installMocks, makeBudgetRow, noScopeWorld, PLANNING_YEAR, test, expect } from './fixtures'

test.describe('edge states', () => {
  test('4.1 a no-scope caller sees the friendly empty state, never the grid', async ({ page }) => {
    const world = noScopeWorld()
    await installMocks(page, world)

    await page.goto('/')

    await expect(page.getByTestId('no-scope-empty-state')).toContainText('ไม่มีสิทธิ์เข้าถึงระบบงบประมาณ')
    await expect(page.getByRole('combobox', { name: /ปีฐาน/ })).toHaveCount(0)
    expect(world.captured.budgetQueries.length).toBe(0)
    expect(world.captured.departmentsQueries.length).toBe(0)
  })

  test('4.2 a SAP outage (502 on GET /budget) shows a loud Thai error, never a silent empty grid', async ({ page }) => {
    const world = fillerWorld({ budgetGridErrorStatus: 502 })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)

    // Scoped to the app's own error banner (`.grid-error`, role="alert" in
    // GridTable.tsx) rather than a bare getByRole('alert'): Next.js's App
    // Router always injects its own empty `#__next-route-announcer__`
    // (role="alert", accessibility live-region for route changes), which
    // made the unscoped role query ambiguous post-migration. Same assertion
    // intent, unambiguous locator.
    await expect(page.locator('.grid-error')).toContainText('เซิร์ฟเวอร์ขัดข้อง')
    await expect(page.getByTestId('side-section-COST')).toHaveCount(0)
    await expect(page.getByText('ไม่มีรายการที่ตรงกับตัวกรองนี้')).toHaveCount(0) // not the silent-empty state either
  })

  test('4.3 a /scope failure shows the error banner and the grid never mounts', async ({ page }) => {
    const world = fillerWorld({ scopeErrorStatus: 500 })
    await installMocks(page, world)

    await page.goto('/')

    await expect(page.getByText('โหลดข้อมูลสิทธิ์ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง')).toBeVisible()
    await expect(page.getByRole('combobox', { name: /ปีฐาน/ })).toHaveCount(0)
  })

  test('4.4 an out-of-scope deep-link department is safely ignored (never applied as a bearer of access)', async ({ page }) => {
    const world = fillerWorld({ budgetGridQueue: [[]] }) // departments list does NOT include "แผนกไม่มีจริง"
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent('แผนกไม่มีจริง')}&year=${DEEP_LINK_YEAR}`)

    // The unmatched deep-link dept is never applied — instead of landing on
    // it (or unselected), the picker falls through to the same "never land
    // unselected" default as no deep-link at all (resolveInitialDept,
    // 2026-07-21 jakkaritw): here the caller's only real ฝ่าย, DEPT.
    await expect(page.getByRole('button', { name: DEPT })).toBeVisible()
    await expect(page.getByRole('button', { name: 'แผนกไม่มีจริง' })).toHaveCount(0)
    await expect.poll(() => world.captured.budgetQueries.at(-1)?.department).toBe(DEPT)
  })

  test('4.5a a past-deadline save shows its OWN specific Thai message (distinct from department_locked)', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_COST, pending: { m01: 100 }, pendingUpdatedAt: 'PEND-1' })]],
      saveRowQueue: [err(403, `the submission deadline for fiscal_year=${PLANNING_YEAR} has passed`)],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    const m01 = page.getByTestId(`pending-input-${CC}-${GL_OFFICE_COST}-m01`)
    await m01.fill('200')
    await m01.blur()

    await expect(page.getByText('พ้นกำหนดส่งงบประมาณของปีนี้แล้ว — กรุณาติดต่อผู้ดูแลระบบ')).toBeVisible()
  })

  test('4.5b a department-locked save shows its OWN specific message (distinct from past_deadline)', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_COST, pending: { m01: 100 }, pendingUpdatedAt: 'PEND-1' })]],
      saveRowQueue: [err(403, `${DEPT}/${PLANNING_YEAR} is PENDING_APPROVER1 — mid-approval or approved, editing is locked`)],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    const m01 = page.getByTestId(`pending-input-${CC}-${GL_OFFICE_COST}-m01`)
    await m01.fill('200')
    await m01.blur()

    // 6a9d323 (2026-09-09, UAT-34) reverted this message to Thai; copied
    // character-for-character from `messageForStatus` in src/api/client.ts:88.
    await expect(page.getByText('บันทึกไม่สำเร็จ — ฝ่ายนี้ส่งขออนุมัติแล้ว จึงแก้ไขไม่ได้ กรุณาโหลดหน้าใหม่')).toBeVisible()
  })

  test('4.6 the userbar always offers a real Logout control pointing at the Easy Auth logout endpoint', async ({ page }) => {
    const world = fillerWorld()
    await installMocks(page, world)

    await page.goto('/')

    const link = page.getByRole('link', { name: 'ออกจากระบบ' })
    await expect(link).toBeVisible()
    await expect(link).toHaveAttribute('href', '/.auth/logout')
  })

  test('4.7 a grand-total figure this large never overflows into the next cell (no clipping either) — jakkaritw 2026-08-20', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[
        makeBudgetRow({
          costCenter: CC,
          glAccount: GL_OFFICE_COST,
          // Real staging figures jakkaritw reported: a total_year this large
          // ran straight into the small January figure beside it, no gap, no
          // wrap — the "121,394,056,573.9" / "3,601,222.21" pair.
          sap: { total_year: 121394056573.9, m01: 3601222.21 },
        }),
      ]],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    await expect(page.getByText('รวมทั้งหมด · SAP · ใช้จริง')).toBeVisible()

    // Range-based geometry measurement, not a screenshot: the content's own
    // painted extent inside each cell — works whether the figure is a bare
    // text node or wrapped in a .month-value span — proves each cell's
    // content stays inside its own box, i.e. never bleeds into its
    // neighbour.
    const overflow = await page.evaluate(() => {
      const row = [...document.querySelectorAll('tr')].find((tr) =>
        tr.textContent?.includes('รวมทั้งหมด · SAP · ใช้จริง'),
      )
      if (!row) throw new Error('grand-total SAP row not found')
      const yearCell = row.querySelector('td.total-year-cell') as HTMLElement
      const janCell = row.querySelector('td.month-cell:not(.total-year-cell)') as HTMLElement
      const measure = (cell: HTMLElement) => {
        const range = document.createRange()
        range.selectNodeContents(cell)
        const content = range.getBoundingClientRect()
        const box = cell.getBoundingClientRect()
        return { contentRight: content.right, cellRight: box.right, cellLeft: box.left }
      }
      return { year: measure(yearCell), jan: measure(janCell) }
    })

    // The huge total_year figure must stay inside its OWN cell...
    expect(overflow.year.contentRight).toBeLessThanOrEqual(overflow.year.cellRight + 0.5)
    // ...which means it can never have painted over Jan's cell either.
    expect(overflow.year.contentRight).toBeLessThanOrEqual(overflow.jan.cellLeft + 0.5)
  })

  test('4.8 dragging a text selection from inside Trip Manager onto the backdrop does not close it, and a genuine backdrop click asks to confirm unsaved changes (bug fix 2026-09-24)', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_TRAVEL_PERDIEM_COST, pending: { m01: 0 }, pendingUpdatedAt: 'PEND-TRV-1' })]],
      tripsQueue: [[]],
      detailLinesQueue: [[]],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    await page.getByTestId(`open-subform-${CC}-${GL_TRAVEL_PERDIEM_COST}`).click()
    await expect(page.getByTestId('trip-manager')).toBeVisible()

    await page.getByRole('button', { name: '+ เพิ่มทริป' }).click()
    const card = page.getByTestId('trip-card-new-0')
    const projectInput = card.getByLabel('project new-0')
    await projectInput.fill('โครงการทดสอบลากเมาส์')

    // A real drag: mousedown INSIDE the project input, drag left past the
    // modal's own edge, mouseup over the dim backdrop. The root cause (see
    // TripManager.tsx / backdropDismiss.ts): the browser fires `click` on the
    // nearest common ancestor of the press/release targets — the backdrop —
    // which a naive `e.target === e.currentTarget` check cannot distinguish
    // from a real backdrop click.
    const modalBox = await page.getByTestId('trip-manager').boundingBox()
    const inputBox = await projectInput.boundingBox()
    if (!modalBox || !inputBox) throw new Error('trip-manager or project input has no bounding box')
    const dragY = inputBox.y + inputBox.height / 2
    await page.mouse.move(inputBox.x + inputBox.width - 4, dragY)
    await page.mouse.down()
    await page.mouse.move(modalBox.x - 8, dragY, { steps: 12 })
    await page.mouse.up()

    // Still open, and the typed Project survived — nothing was lost.
    await expect(page.getByTestId('trip-manager')).toBeVisible()
    await expect(projectInput).toHaveValue('โครงการทดสอบลากเมาส์')

    // A genuine backdrop click (no drag) on this now-dirty card must ask
    // before discarding it — it must NOT close immediately the way a plain
    // onClose() used to.
    await page.mouse.click(modalBox.x - 20, modalBox.y + 100)
    await expect(page.getByTestId('confirm-dialog')).toBeVisible()
    await page.getByTestId('confirm-cancel').click()
    await expect(page.getByTestId('trip-manager')).toBeVisible()
  })

  test('4.9 a REVERSE drag — press starting on the backdrop, release inside Trip Manager — also does not close it (08003e1 fix on top of 4.8)', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_TRAVEL_PERDIEM_COST, pending: { m01: 0 }, pendingUpdatedAt: 'PEND-TRV-1' })]],
      tripsQueue: [[]],
      detailLinesQueue: [[]],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    await page.getByTestId(`open-subform-${CC}-${GL_TRAVEL_PERDIEM_COST}`).click()
    await expect(page.getByTestId('trip-manager')).toBeVisible()

    await page.getByRole('button', { name: '+ เพิ่มทริป' }).click()
    const card = page.getByTestId('trip-card-new-0')
    const projectInput = card.getByLabel('project new-0')
    await projectInput.fill('โครงการทดสอบลากย้อนกลับ')

    // The reverse of 4.8's drag: mousedown OUTSIDE the modal, on the dim
    // backdrop, then drag INTO the Project input and release there. `click`
    // still lands on the backdrop (same common-ancestor rule as 4.8), but
    // `onMouseUp` narrows the press flag to false because the release landed
    // inside the modal, not on the backdrop — so this direction never even
    // reaches `onCancel` (08003e1's mouseup narrowing, on top of c61f144's
    // forward-drag fix from 4.8).
    const modalBox = await page.getByTestId('trip-manager').boundingBox()
    const inputBox = await projectInput.boundingBox()
    if (!modalBox || !inputBox) throw new Error('trip-manager or project input has no bounding box')
    const dragY = inputBox.y + inputBox.height / 2
    await page.mouse.move(modalBox.x - 8, dragY)
    await page.mouse.down()
    await page.mouse.move(inputBox.x + 20, dragY, { steps: 12 })
    await page.mouse.up()

    // Still open, and the typed Project survived — nothing was lost, and no
    // confirm was even asked (the click never reached onCancel).
    await expect(page.getByTestId('trip-manager')).toBeVisible()
    await expect(page.getByTestId('confirm-dialog')).toHaveCount(0)
    await expect(projectInput).toHaveValue('โครงการทดสอบลากย้อนกลับ')
  })

  test('4.10 holding Enter on a dirty Trip Manager\'s ✕ does not auto-confirm the discard-unsaved dialog (gate finding 2026-09-25, probe D2)', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_TRAVEL_PERDIEM_COST, pending: { m01: 0 }, pendingUpdatedAt: 'PEND-TRV-1' })]],
      tripsQueue: [[]],
      detailLinesQueue: [[]],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    await page.getByTestId(`open-subform-${CC}-${GL_TRAVEL_PERDIEM_COST}`).click()
    await expect(page.getByTestId('trip-manager')).toBeVisible()

    await page.getByRole('button', { name: '+ เพิ่มทริป' }).click()
    const card = page.getByTestId('trip-card-new-0')
    const projectInput = card.getByLabel('project new-0')
    await projectInput.fill('โครงการทดสอบกด Enter ค้าง')

    const closeBtn = page.getByTestId('trip-manager').getByRole('button', { name: 'Close' })
    await closeBtn.focus()

    // First keydown: ✕'s onClick fires onCancel -> dirty -> opens the
    // discard-unsaved confirm, which focuses ITS OWN Cancel button.
    await page.keyboard.down('Enter')
    await expect(page.getByTestId('confirm-dialog')).toBeVisible()

    // The auto-repeat keydown Chromium fires while the key is still held
    // (Playwright marks this second `down` as `repeat: true`) used to answer
    // the confirm as `true` before this fix — both dialogs must survive it.
    await page.keyboard.down('Enter')
    await expect(page.getByTestId('confirm-dialog')).toBeVisible()
    await expect(page.getByTestId('trip-manager')).toBeVisible()

    await page.keyboard.up('Enter')
    await page.getByTestId('confirm-cancel').click()

    // Declining the confirm keeps Trip Manager open with the typed value intact.
    await expect(page.getByTestId('trip-manager')).toBeVisible()
    await expect(projectInput).toHaveValue('โครงการทดสอบกด Enter ค้าง')
  })
})
