/** Edge-state journeys — no-scope empty state, SAP outage (loud error, never
 * a silent empty grid), a /scope failure banner, an out-of-scope deep-link
 * dept being safely ignored, and the two specific 403 Thai messages
 * (past_deadline / department_locked) mapped in `src/api/client.ts`. */
import { CC, DEPT, err, fillerWorld, GL_OFFICE_COST, installMocks, makeBudgetRow, noScopeWorld, PLANNING_YEAR, test, expect } from './fixtures'

test.describe('edge states', () => {
  test('4.1 a no-scope caller sees the friendly empty state, never the grid', async ({ page }) => {
    const world = noScopeWorld()
    await installMocks(page, world)

    await page.goto('/')

    await expect(page.getByTestId('no-scope-empty-state')).toContainText('คุณไม่มีสิทธิ์กรอกงบประมาณ')
    await expect(page.getByRole('combobox', { name: /ปีงบประมาณ/ })).toHaveCount(0)
    expect(world.captured.budgetQueries.length).toBe(0)
    expect(world.captured.departmentsQueries.length).toBe(0)
  })

  test('4.2 a SAP outage (502 on GET /budget) shows a loud Thai error, never a silent empty grid', async ({ page }) => {
    const world = fillerWorld({ budgetGridErrorStatus: 502 })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${PLANNING_YEAR}`)

    await expect(page.getByRole('alert')).toContainText('เซิร์ฟเวอร์ขัดข้อง')
    await expect(page.getByTestId('side-section-COST')).toHaveCount(0)
    await expect(page.getByText('ไม่มีรายการที่ตรงกับตัวกรองนี้')).toHaveCount(0) // not the silent-empty state either
  })

  test('4.3 a /scope failure shows the error banner and the grid never mounts', async ({ page }) => {
    const world = fillerWorld({ scopeErrorStatus: 500 })
    await installMocks(page, world)

    await page.goto('/')

    await expect(page.getByText('โหลดข้อมูลสิทธิ์ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง')).toBeVisible()
    await expect(page.getByRole('combobox', { name: /ปีงบประมาณ/ })).toHaveCount(0)
  })

  test('4.4 an out-of-scope deep-link department is safely ignored (never applied as a bearer of access)', async ({ page }) => {
    const world = fillerWorld({ budgetGridQueue: [[]] }) // departments list does NOT include "แผนกไม่มีจริง"
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent('แผนกไม่มีจริง')}&year=${PLANNING_YEAR}`)

    await expect(page.getByRole('button', { name: '— เลือกฝ่าย —' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'แผนกไม่มีจริง' })).toHaveCount(0)
  })

  test('4.5a a past-deadline save shows its OWN specific Thai message (distinct from department_locked)', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_COST, pending: { m01: 100 }, pendingUpdatedAt: 'PEND-1' })]],
      saveRowQueue: [err(403, `the submission deadline for fiscal_year=${PLANNING_YEAR} has passed`)],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${PLANNING_YEAR}`)
    const m01 = page.getByTestId(`pending-input-${CC}-${GL_OFFICE_COST}-m01`)
    await m01.fill('200')
    await m01.blur()

    await expect(page.getByText('พ้นกำหนดส่งงบประมาณของปีนี้แล้ว — กรุณาติดต่อผู้ดูแลระบบ')).toBeVisible()
  })

  test('4.5b a department-locked save shows its OWN specific Thai message (distinct from past_deadline)', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_COST, pending: { m01: 100 }, pendingUpdatedAt: 'PEND-1' })]],
      saveRowQueue: [err(403, `${DEPT}/${PLANNING_YEAR} is PENDING_APPROVER1 — mid-approval or approved, editing is locked`)],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${PLANNING_YEAR}`)
    const m01 = page.getByTestId(`pending-input-${CC}-${GL_OFFICE_COST}-m01`)
    await m01.fill('200')
    await m01.blur()

    await expect(page.getByText('ฝ่ายนี้อยู่ระหว่างรออนุมัติ/อนุมัติแล้ว — แก้ไขไม่ได้')).toBeVisible()
  })
})
