/** Filler (ผู้กรอกงบประมาณ) end-to-end journey — deep-link load, 3-layer
 * grid, inline Pending edit + 409 conflict, special-GL subform (add/delete),
 * Trip Manager (per-diem never computed client-side), Submit. Every step
 * asserts a REAL payload, DOM value, or captured request param — never just
 * "page rendered". */
import { ENTERTAINMENT_EXTERNAL_VALUES } from '../src/subform/glDropdownConstants'
import {
  approvalState,
  CC,
  DEEP_LINK_YEAR,
  DEPT,
  err,
  fillerWorld,
  GL_ENTERTAIN_EXT,
  GL_OFFICE_COST,
  GL_OFFICE_SGA,
  GL_TRAVEL_PERDIEM_COST,
  installMocks,
  makeBudgetRow,
  ok,
  PLANNING_YEAR,
  test,
  expect,
} from './fixtures'
import type { World } from './fixtures'

/** Number of GET /budget calls that actually carried the resolved
 * department (excludes the pre-resolution `department=undefined` noise both
 * React StrictMode's double-mount and the async deep-link resolution
 * produce — see fixtures.ts's `/budget` dispatch comment). This is what
 * "the grid refetched" should mean for a spec, not a raw call count. */
function realBudgetFetchCount(world: World): number {
  return world.captured.budgetQueries.filter((q) => q.department === DEPT).length
}

test.describe('filler journey', () => {
  test('1.1 deep-link dept+year prefill the picker chip and drive the grid fetch params', async ({ page }) => {
    const world = fillerWorld({ budgetGridQueue: [[]] })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)

    await expect(page.getByRole('button', { name: DEPT })).toBeVisible()
    // aria-label renamed to "ปีฐาน (SAP/Approved · Pending = ปีถัดไป)" (YearPicker.tsx)
    // — the picker's underlying `value` is still the PLANNING year (Y+1), only
    // the label's semantics changed, so the assertion itself is unchanged.
    await expect(page.getByRole('combobox', { name: /ปีฐาน/ })).toHaveValue(String(PLANNING_YEAR))

    await expect.poll(() => world.captured.budgetQueries.length).toBeGreaterThan(0)
    const query = world.captured.budgetQueries.at(-1)!
    expect(query.department).toBe(DEPT)
    expect(query.year).toBe(String(PLANNING_YEAR))
  })

  test('1.2 renders structurally-separate COST/SGA sections, each with a subtotal, and the 3-layer transaction block', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [
        [
          makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_COST, sap: { m01: 100 }, pending: { m01: 200 }, pendingUpdatedAt: 'PEND-1' }),
          makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_SGA, sap: { m01: 50 }, pending: { m01: 0 }, pendingUpdatedAt: 'PEND-2' }),
        ],
      ],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)

    const costSection = page.getByTestId('side-section-COST')
    const sgaSection = page.getByTestId('side-section-SGA')
    await expect(costSection).toBeVisible()
    await expect(sgaSection).toBeVisible()
    // Each section's subtotal row is now 3-way — SAP/Approved/Pending each
    // get their own "รวมทั้งหมด · <layer>" label (jakkaritw's 3-layer
    // transaction block) — so /รวมทั้งหมด/ alone now matches 3 cells per
    // section; assert all 3 layer labels explicitly instead of one loose regex.
    await expect(costSection.getByText('รวมทั้งหมด · SAP · ใช้จริง', { exact: false })).toBeVisible()
    await expect(costSection.getByText('รวมทั้งหมด · Approved · งบ')).toBeVisible()
    await expect(costSection.getByText('รวมทั้งหมด · Pending · รออนุมัติ')).toBeVisible()
    await expect(sgaSection.getByText('รวมทั้งหมด · SAP · ใช้จริง', { exact: false })).toBeVisible()
    await expect(sgaSection.getByText('รวมทั้งหมด · Approved · งบ')).toBeVisible()
    await expect(sgaSection.getByText('รวมทั้งหมด · Pending · รออนุมัติ')).toBeVisible()
    // one known gl_group header, rendered per-row (GridTable has no separate
    // group-header row — the group name shows on every row's GL Group cell).
    await expect(costSection.getByText('Office Expenses').first()).toBeVisible()

    // 3-layer block for the COST row: SAP (read-only), Approved (read-only), Pending (editable).
    // Displayed amounts carry two decimals in all three layers (commit 9110837);
    // the editable Pending INPUT still holds the raw value, hence '200' below.
    await expect(page.getByTestId(`sap-value-${CC}-${GL_OFFICE_COST}-m01`)).toHaveText('100.00')
    await expect(page.getByTestId(`board-value-${CC}-${GL_OFFICE_COST}-m01`)).toHaveText('—')
    await expect(page.getByTestId(`pending-input-${CC}-${GL_OFFICE_COST}-m01`)).toHaveValue('200')
  })

  test('1.3 editing a Pending cell saves the exact payload and the UI shows the SERVER-recomputed row, not client math', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_COST, pending: { m01: 100, m02: 200 }, pendingUpdatedAt: 'PEND-TOKEN-1' })]],
      saveRowQueue: [
        ok({
          cost_center: CC, gl_account: GL_OFFICE_COST, fiscal_year: PLANNING_YEAR,
          m01: 1500, m02: 777, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
          // total_year deliberately NOT the naive client sum (1500+200=1700) —
          // proves the UI trusts the server response, not local arithmetic.
          total_year: 123456,
          remark: null, template: 'USER', gl_name: null, gl_group: null, c_level: null, division: null, department: null,
          updated_at: 'PEND-TOKEN-2',
        }),
      ],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)

    const m01 = page.getByTestId(`pending-input-${CC}-${GL_OFFICE_COST}-m01`)
    await m01.fill('1500')
    await m01.blur()

    await expect.poll(() => world.captured.saveRowBodies.length).toBeGreaterThan(0)
    expect(world.captured.saveRowBodies.at(-1)).toMatchObject({
      cost_center: CC,
      gl_account: GL_OFFICE_COST,
      fiscal_year: PLANNING_YEAR,
      m01: 1500,
      expected_updated_at: 'PEND-TOKEN-1', // echoed verbatim from the GET
    })

    // The cell the user edited shows the server's own m01...
    await expect(m01).toHaveValue('1500')
    // ...and a month the user NEVER touched (m02) also flips to the
    // server's value — proof the whole row was replaced by the server
    // response (mergeSavedRow), not a locally-recomputed total.
    await expect(page.getByTestId(`pending-input-${CC}-${GL_OFFICE_COST}-m02`)).toHaveValue('777')
  })

  test('1.4 a 409 conflict shows the Thai message, refetches the grid, and REVERTS to the refetched server value', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [
        [makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_COST, pending: { m01: 100 }, pendingUpdatedAt: 'PEND-TOKEN-A' })],
        [makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_COST, pending: { m01: 555 }, pendingUpdatedAt: 'PEND-TOKEN-B' })],
      ],
      saveRowQueue: [err(409, 'row changed by someone else')],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)

    const m01 = page.getByTestId(`pending-input-${CC}-${GL_OFFICE_COST}-m01`)
    await m01.fill('999')
    await m01.blur()

    await expect(page.getByText(/ถูกแก้ไขโดยผู้อื่น/)).toBeVisible()
    await expect.poll(() => realBudgetFetchCount(world)).toBeGreaterThanOrEqual(2) // the 409 catch called loadGrid() again
    await expect(m01).toHaveValue('555') // refetched server truth, NOT the typed 999
  })

  test('1.5 a special-GL Pending cell blocks direct edit and its affordance opens the subform for that (cc, gl)', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_ENTERTAIN_EXT, pending: { m01: 0 }, pendingUpdatedAt: 'PEND-ENT-1' })]],
      detailLinesQueue: [[]],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)

    // No editable input for this special-GL cell at all.
    await expect(page.locator(`[data-testid="pending-cell-${CC}-${GL_ENTERTAIN_EXT}-m01"] input`)).toHaveCount(0)
    await expect(page.getByTestId(`pending-input-${CC}-${GL_ENTERTAIN_EXT}-m01`)).toHaveCount(0)

    await page.getByTestId(`open-subform-${CC}-${GL_ENTERTAIN_EXT}`).click()

    await expect(page.getByTestId('detail-subform')).toBeVisible()
    await expect.poll(() => world.captured.detailQueries.length).toBeGreaterThan(0)
    const query = world.captured.detailQueries.at(-1)!
    expect(query.cost_center).toBe(CC)
    expect(query.gl_account).toBe(GL_ENTERTAIN_EXT)
  })

  test('1.6 subform: the GL-conditional dropdown offers ONLY the fixture values; saving refetches and the parent cell shows the server sum', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [
        [makeBudgetRow({ costCenter: CC, glAccount: GL_ENTERTAIN_EXT, pending: { m01: 0 }, pendingUpdatedAt: 'PEND-ENT-1' })],
        [makeBudgetRow({ costCenter: CC, glAccount: GL_ENTERTAIN_EXT, pending: { m01: 5000 }, pendingUpdatedAt: 'PEND-ENT-2' })],
      ],
      detailLinesQueue: [[]],
      saveDetailQueue: [
        ok({
          detail_id: 777, cost_center: CC, gl_account: GL_ENTERTAIN_EXT, fiscal_year: PLANNING_YEAR, trip_id: null, gl_group: 'Entertainment',
          line_label: null,
          m01: 5000, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
          total_year: 5000, meta_json: { 'ประเภทการรับรอง': 'Customer', 'รายละเอียด': 'lunch with client' }, updated_at: 'DETAIL-TOKEN-1',
        }),
      ],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    await page.getByTestId(`open-subform-${CC}-${GL_ENTERTAIN_EXT}`).click()
    await expect(page.getByTestId('detail-subform')).toBeVisible()

    await page.getByRole('button', { name: '+ เพิ่มรายการ' }).click()

    const dropdown = page.getByLabel('ประเภทการรับรอง')
    const options = await dropdown.locator('option').allTextContents()
    // The blank placeholder plus EXACTLY the fixture's external values — never
    // the internal-entertainment set (this GL doesn't end in the internal suffix).
    expect(options).toEqual(['— เลือก —', ...ENTERTAINMENT_EXTERNAL_VALUES])

    await dropdown.selectOption('Customer')
    // รายละเอียด (text) is required too now (jakkaritw 2026-08-20) — every
    // enterable field must be filled or the save is blocked client-side.
    await page.getByLabel('รายละเอียด').fill('lunch with client')
    await page.getByLabel('m01 new-0').fill('5000')
    await page.getByTestId('save-all').click()

    await expect.poll(() => world.captured.detailBodies.length).toBeGreaterThan(0)
    expect(world.captured.detailBodies.at(-1)).toMatchObject({
      detail_id: null,
      cost_center: CC,
      gl_account: GL_ENTERTAIN_EXT,
      fiscal_year: PLANNING_YEAR,
      trip_id: null,
      m01: 5000,
      meta_json: { 'ประเภทการรับรอง': 'Customer' },
    })

    await expect.poll(() => realBudgetFetchCount(world)).toBeGreaterThanOrEqual(2) // onSaved() refetches the grid
    await expect(page.getByTestId(`pending-cell-${CC}-${GL_ENTERTAIN_EXT}-m01`)).toHaveText('5,000.00')
  })

  test('1.7 deleting a detail line confirms, sends the id + lock token, and the grid refetches', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [
        [makeBudgetRow({ costCenter: CC, glAccount: GL_ENTERTAIN_EXT, pending: { m01: 5000 }, pendingUpdatedAt: 'PEND-ENT-2' })],
        [makeBudgetRow({ costCenter: CC, glAccount: GL_ENTERTAIN_EXT, pending: { m01: 0 }, pendingUpdatedAt: 'PEND-ENT-3' })],
      ],
      detailLinesQueue: [
        [
          {
            detail_id: 42, cost_center: CC, gl_account: GL_ENTERTAIN_EXT, fiscal_year: PLANNING_YEAR, trip_id: null, gl_group: 'Entertainment',
            line_label: null,
            m01: 5000, m02: 0, m03: 0, m04: 0, m05: 0, m06: 0, m07: 0, m08: 0, m09: 0, m10: 0, m11: 0, m12: 0,
            total_year: 5000, meta_json: { 'ประเภทการรับรอง': 'Customer' }, updated_at: 'DETAIL-TOKEN-1',
          },
        ],
      ],
      deleteDetailQueue: [ok({ ok: true })],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    await page.getByTestId(`open-subform-${CC}-${GL_ENTERTAIN_EXT}`).click()
    await expect(page.getByTestId('detail-row-existing-42')).toBeVisible()

    let dialogMessage = ''
    page.once('dialog', (dialog) => {
      dialogMessage = dialog.message()
      void dialog.accept()
    })
    await page.getByTestId('detail-row-existing-42').getByRole('button', { name: 'ลบ' }).click()

    expect(dialogMessage).toBe('ลบรายการนี้?')
    await expect.poll(() => world.captured.deleteDetailParams.length).toBeGreaterThan(0)
    expect(world.captured.deleteDetailParams.at(-1)).toMatchObject({ detail_id: '42', expected_updated_at: 'DETAIL-TOKEN-1' })

    await expect.poll(() => realBudgetFetchCount(world)).toBeGreaterThanOrEqual(2)
    await expect(page.getByTestId(`pending-cell-${CC}-${GL_ENTERTAIN_EXT}-m01`)).toHaveText('—')
  })

  test('1.8 Trip Manager creates a trip and shows ONLY the server-computed per-diem, never a client-side number', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_TRAVEL_PERDIEM_COST, pending: { m01: 0 }, pendingUpdatedAt: 'PEND-TRV-1' })]],
      tripsQueue: [[]],
      detailLinesQueue: [[]],
      saveTripQueue: [
        ok({
          trip_id: 501, cost_center: CC, fiscal_year: PLANNING_YEAR, traveler_empcode: '100123', traveler_name: 'สมชาย ทดสอบ',
          position: 'Officer', destination: 'ญี่ปุ่น', country_group: 2, days: 5, travel_months: ['03', '04'],
          project: null, purpose: null, side: 'COST',
          updated_at: 'TRIP-TOKEN-1', per_diem_months: { m03: 3000, m04: 3000 },
        }),
      ],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    await page.getByTestId(`open-subform-${CC}-${GL_TRAVEL_PERDIEM_COST}`).click()
    await expect(page.getByTestId('trip-manager')).toBeVisible()

    await page.getByRole('button', { name: '+ เพิ่มทริป' }).click()
    const card = page.getByTestId('trip-card-new-0')
    await expect(card).toContainText('ระบบจะคำนวณให้หลังกดบันทึก')

    // traveler AND destination are both searchable comboboxes, NOT native
    // <select>s (traveler: jakkaritw, 2026-08-04, commit 1e441de; destination:
    // jakkaritw, 2026-08-23, same interaction shape) — type to filter, then
    // click the matching option. Position auto-displays read-only; the
    // destination pick AUTO-SETS country_group (ญี่ปุ่น → 2) — the manual
    // group select no longer exists.
    const travelerInput = card.getByLabel('traveler_empcode new-0')
    await travelerInput.click()
    await travelerInput.fill('สมชาย')
    await card.getByRole('option', { name: /สมชาย ทดสอบ/ }).click()
    await expect(travelerInput).toHaveValue('สมชาย ทดสอบ')
    await expect(card.getByTestId('position-new-0')).toHaveText('Officer')
    expect(await card.getByLabel('country_group new-0').count()).toBe(0)
    const destinationInput = card.getByLabel('destination new-0')
    await destinationInput.click()
    await destinationInput.fill('ญี่ปุ่น')
    await card.getByRole('option', { name: 'ญี่ปุ่น' }).click()
    await expect(destinationInput).toHaveValue('ญี่ปุ่น')
    await card.getByLabel('days new-0').fill('5')
    await card.getByRole('button', { name: 'Mar', exact: true }).click()
    await card.getByRole('button', { name: 'Apr', exact: true }).click()
    // ฝั่งบัญชี (accounting side) is now locked to the GL row that opened this
    // subform, disabled for every user incl. admins (jakkaritw, 2026-08-04,
    // commit 1e441de) — the modal was opened from GL_TRAVEL_PERDIEM_COST, so
    // the select is already COST and cannot be changed; assert the lock
    // instead of calling selectOption (which times out on a disabled control).
    const sideSelect = card.getByLabel('side new-0')
    await expect(sideSelect).toBeDisabled()
    await expect(sideSelect).toHaveValue('COST')
    // Consolidated save-all (2026-07-19) — one bottom-bar button saves every
    // card/line in the modal; the per-card "บันทึกทริป" button was removed.
    await page.getByTestId('save-all').click()

    await expect.poll(() => world.captured.tripBodies.length).toBeGreaterThan(0)
    expect(world.captured.tripBodies.at(-1)).toMatchObject({
      cost_center: CC,
      fiscal_year: PLANNING_YEAR,
      traveler_empcode: '100123',
      destination: 'ญี่ปุ่น',
      country_group: 2,
      days: 5,
      travel_months: ['03', '04'],
      side: 'COST',
      trip_id: null,
      expected_updated_at: null,
    })

    const savedCard = page.getByTestId('trip-card-existing-501')
    await expect(savedCard).toContainText('เฉลี่ยจากเซิร์ฟเวอร์')
    await expect(savedCard).toContainText('6,000')
  })

  test('1.9 Submit confirms with a summary, posts the payload, and the status chip flips to รออนุมัติ ขั้น 1', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_COST, pending: { m01: 100 }, pendingUpdatedAt: 'PEND-1' })]],
      // can_submit: true set explicitly -- the fixture default is now
      // fail-closed `false` (gate review, 2026-08-16); this scenario needs
      // the Submit button visible and clickable, so it opts in on purpose.
      approvalStatusByDept: { [DEPT]: approvalState({ department: DEPT, status: 'DRAFT', can_submit: true }) },
      submitQueue: [
        ok(approvalState({ department: DEPT, status: 'PENDING_APPROVER1', current_position: 1, current_approver_empcode: '999999' })),
      ],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    await expect(page.getByTestId('approval-submit-btn')).toBeVisible()

    let dialogMessage = ''
    page.once('dialog', (dialog) => {
      dialogMessage = dialog.message()
      void dialog.accept()
    })
    await page.getByTestId('approval-submit-btn').click()

    expect(dialogMessage).toContain(DEPT)
    expect(dialogMessage).toContain(`ปี ${PLANNING_YEAR}`)
    expect(dialogMessage).toContain('จำนวน 1 รายการ')

    await expect.poll(() => world.captured.submitBodies.length).toBeGreaterThan(0)
    expect(world.captured.submitBodies.at(-1)).toEqual({ department: DEPT, fiscal_year: PLANNING_YEAR })

    const chip = page.getByTestId('approval-status-chip')
    await expect(chip).toContainText('Pending')
    await expect(chip).toContainText('Step 1')
  })

  // Filler-blocked-hint fix (2026-08-16, jakkaritw: "ใส่ข้อความให้ผู้กรอกด้วย"):
  // pinned in the permanent suite, not just a unit test -- a blocked Filler
  // must see WHY the Submit button is gone, same as a blocked admin already did.
  test('1.10 a blocked Filler sees the Thai reason instead of a silently-absent Submit button', async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [[makeBudgetRow({ costCenter: CC, glAccount: GL_OFFICE_COST, pending: { m01: 100 }, pendingUpdatedAt: 'PEND-1' })]],
      approvalStatusByDept: {
        [DEPT]: approvalState({
          department: DEPT, status: 'DRAFT', can_submit: false, submit_blocked_reason: 'year_not_open',
        }),
      },
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)

    await expect(page.getByTestId('approval-submit-blocked-hint')).toContainText('not open for submission yet')
    await expect(page.getByTestId('approval-submit-btn')).not.toBeVisible()
  })
})
