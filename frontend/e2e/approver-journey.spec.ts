/** Approver (ผู้อนุมัติ) end-to-end journey — รออนุมัติ badge, step-gated
 * approve/reject, required reject reason, resubmit chain-reset, and a
 * concurrent-approve 409. The approver here is `see_only` (not necessarily a
 * Filler of the department they approve) per the project's own decision. */
import { approvalState, approverWorld, DEPT, DEPT2, err, installMocks, ok, PLANNING_YEAR, test, expect } from './fixtures'

test.describe('approver journey', () => {
  test('2.1 the รออนุมัติ badge marks only the department pending on this approver', async ({ page }) => {
    const world = approverWorld({ pendingForMe: { departments: [DEPT] }, budgetGridQueue: [[]] })
    await installMocks(page, world)

    await page.goto('/')
    await expect.poll(() => world.captured.pendingForMeQueries.length).toBeGreaterThan(0)
    expect(world.captured.pendingForMeQueries.at(-1)).toMatchObject({ fiscal_year: String(PLANNING_YEAR) })

    await page.getByRole('button', { name: '— เลือกฝ่าย —' }).click()
    const deptRow = page.locator('.dept-picker-row', { hasText: DEPT })
    const dept2Row = page.locator('.dept-picker-row', { hasText: DEPT2 })
    await expect(deptRow.getByText('รออนุมัติ')).toBeVisible()
    await expect(dept2Row.getByText('รออนุมัติ')).toHaveCount(0)
  })

  test('2.2 Approve/Reject show ONLY on the department where it is this approver\'s turn', async ({ page }) => {
    const world = approverWorld({
      budgetGridQueue: [[]],
      approvalStatusByDept: {
        [DEPT]: approvalState({ department: DEPT, status: 'PENDING_APPROVER1', current_position: 1, current_approver_empcode: '123456', can_act: true }),
        [DEPT2]: approvalState({ department: DEPT2, status: 'PENDING_APPROVER1', current_position: 1, current_approver_empcode: '999999', can_act: false }),
      },
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${PLANNING_YEAR}`)
    await expect(page.getByTestId('approval-approve-btn')).toBeVisible()
    await expect(page.getByTestId('approval-reject-btn')).toBeVisible()

    await page.getByRole('button', { name: DEPT }).click()
    await page.locator('.dept-picker-row', { hasText: DEPT2 }).click()

    await expect(page.getByTestId('approval-status-chip')).toBeVisible()
    await expect(page.getByTestId('approval-approve-btn')).toHaveCount(0)
    await expect(page.getByTestId('approval-reject-btn')).toHaveCount(0)
  })

  test('2.3 Reject requires a non-empty reason, then posts it and the chip shows ตีกลับ + the reason', async ({ page }) => {
    const world = approverWorld({
      budgetGridQueue: [[]],
      approvalStatusByDept: {
        [DEPT]: approvalState({ department: DEPT, status: 'PENDING_APPROVER1', current_position: 1, current_approver_empcode: '123456', can_act: true }),
      },
      rejectQueue: [
        ok(
          approvalState({
            department: DEPT, status: 'REJECTED', current_position: null, can_act: false,
            reject_reason: 'ข้อมูลไม่ครบ', rejected_by_empcode: '123456',
          }),
        ),
      ],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${PLANNING_YEAR}`)
    await page.getByTestId('approval-reject-btn').click()

    const confirmBtn = page.getByTestId('approval-reject-confirm-btn')
    await expect(confirmBtn).toBeDisabled() // blocked: reason is empty

    await page.getByTestId('approval-reject-reason-input').fill('ข้อมูลไม่ครบ')
    await expect(confirmBtn).toBeEnabled()
    await confirmBtn.click()

    await expect.poll(() => world.captured.rejectBodies.length).toBeGreaterThan(0)
    expect(world.captured.rejectBodies.at(-1)).toEqual({ department: DEPT, fiscal_year: PLANNING_YEAR, reason: 'ข้อมูลไม่ครบ' })

    await expect(page.getByTestId('approval-status-chip')).toContainText('ถูกตีกลับ')
    await expect(page.getByTestId('approval-reject-reason')).toContainText('ข้อมูลไม่ครบ')
  })

  test('2.4 after a reject, resubmitting elsewhere resets the chain back to รออนุมัติ ขั้น 1 on refetch', async ({ page }) => {
    const world = approverWorld({
      budgetGridQueue: [[]],
      approvalStatusByDept: {
        [DEPT]: approvalState({ department: DEPT, status: 'REJECTED', reject_reason: 'ข้อมูลไม่ครบ', current_position: null, can_act: false }),
      },
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${PLANNING_YEAR}`)
    await expect(page.getByTestId('approval-status-chip')).toContainText('ถูกตีกลับ')

    // Simulate "meanwhile, the filler resubmitted elsewhere" by mutating the
    // mock backend's CURRENT state directly (not a canned queue — GET
    // /approval/status is mount-triggered, so a queue would be silently
    // double-drained by React StrictMode's dev-only double-mount before this
    // point is ever reached; see fixtures.ts).
    world.approvalStatusByDept[DEPT] = approvalState({
      department: DEPT, status: 'PENDING_APPROVER1', current_position: 1, current_approver_empcode: '123456', can_act: true,
    })

    // Switch away and back — forces ApprovalActionBar to refetch this
    // department's status.
    await page.getByRole('button', { name: DEPT }).click()
    await page.locator('.dept-picker-row', { hasText: DEPT2 }).click()
    await page.getByRole('button', { name: DEPT2 }).click()
    await page.locator('.dept-picker-row', { hasText: DEPT, exact: false }).first().click()

    const chip = page.getByTestId('approval-status-chip')
    await expect(chip).toContainText('รออนุมัติ')
    await expect(chip).toContainText('ขั้น 1')
  })

  test('2.5 a concurrent approve returns 409, shows the Thai message, and refetches the status', async ({ page }) => {
    const world = approverWorld({
      budgetGridQueue: [[]],
      approvalStatusByDept: {
        [DEPT]: approvalState({ department: DEPT, status: 'PENDING_APPROVER1', current_position: 1, current_approver_empcode: '123456', can_act: true }),
      },
      approveQueue: [
        err(409, 'approval_status changed by someone else', () => {
          // The reason the approve raced: someone else's approval already
          // landed and moved the chain to position 2 — the refetch below
          // must see THIS, not the stale position-1 state.
          world.approvalStatusByDept[DEPT] = approvalState({
            department: DEPT, status: 'PENDING_APPROVER2', current_position: 2, current_approver_empcode: '101032', can_act: false,
          })
        }),
      ],
    })
    await installMocks(page, world)

    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${PLANNING_YEAR}`)
    page.once('dialog', (dialog) => void dialog.accept())
    await page.getByTestId('approval-approve-btn').click()

    await expect(page.getByTestId('approval-action-message')).toContainText('มีการเปลี่ยนแปลงสถานะโดยผู้อื่นระหว่างนี้')
    // load() ran again after the 409 — the chip reflects the FRESH (position 2) truth.
    await expect(page.getByTestId('approval-status-chip')).toContainText('ขั้น 2')
  })
})
