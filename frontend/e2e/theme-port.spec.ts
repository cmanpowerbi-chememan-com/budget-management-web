/** Permanent tests for the theme port (issue #30, slices 2+3+4, 2026-09-19).
 * Three of the four areas jakkaritw asked for; the fourth ("readability
 * across the three zones") is deliberately NOT duplicated here — it is
 * already the job of `e2e/contrast.spec.ts`'s existing ratchet, whose 9
 * scenarios already sweep the same 3 zones this port touches. Re-baselining
 * that ratchet against this port's changes is a separate, explicit step
 * (see this task's final report) — it is a hard gate this file does not
 * attempt to route around.
 *
 * Same seam as contrast.spec.ts: the rendered DOM through the browser-driven
 * test layer, real computed values, no component internals. Mocks only the
 * network (`e2e/fixtures.ts`) — no live backend/DB is ever touched.
 *
 * 1. TestThemeParity      — computed colour/radius/gradient of representative
 *    elements across the 3 zones vs the approved theme's own values
 *    (.scratch/theme-customizer/extracted-theme-signed-off.json).
 * 2. TestCssTsMirrorLock  — the 3 places a CSS fact is duplicated into
 *    TypeScript (GridTable.tsx's measurer inline style; model.ts's
 *    COLUMN_WIDTH_MEASURE_PADDING / MONTH_COLUMN_WIDTH_FLOOR /
 *    TOTAL_YEAR_COLUMN_WIDTH_FLOOR) read back against the LIVE rendered
 *    values, not hardcoded expectations — if one side drifts from the
 *    other, this fails, by construction.
 * 3. TestFrozenEdgeShadow — the .frz-5/.frz-edge box-shadow present on every
 *    body-row state that exists in THIS app today: the sap/approved/pending
 *    layer rows and the subtotal row. Production has no zebra striping and
 *    no tbody-row hover rule (confirmed by grep — that is prototype-only),
 *    so "odd/even/hovered" from the PRD's own wording has no distinct CSS
 *    state to test here; a hover interaction is still exercised to prove it
 *    does not clobber the shadow (nothing competes for the property today,
 *    which this test also locks in place).
 */
import type { Locator, Page } from '@playwright/test'
import { test, expect, installMocks, fillerWorld, makeBudgetRow, DEPT, CC, GL_OFFICE_COST, GL_TRAVEL_PERDIEM_COST, DEEP_LINK_YEAR } from './fixtures'
import { COLUMN_WIDTH_MEASURE_PADDING, MONTH_COLUMN_WIDTH_FLOOR, TOTAL_YEAR_COLUMN_WIDTH_FLOOR } from '../src/grid/model'

const DEEP_LINK = `/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`

function rows() {
  return [
    makeBudgetRow({
      costCenter: CC,
      glAccount: GL_OFFICE_COST,
      sap: { m01: 120_000 },
      pending: { m01: 130_000 },
      pendingUpdatedAt: 'PEND-1',
    }),
    makeBudgetRow({
      costCenter: CC,
      glAccount: GL_TRAVEL_PERDIEM_COST,
      sap: { m03: 18_000 },
      pending: { m03: 22_000 },
      pendingUpdatedAt: 'PEND-2',
    }),
  ]
}

async function gotoGrid(page: Page) {
  await installMocks(page, fillerWorld({ budgetGridQueue: [rows(), rows()] }))
  await page.goto(DEEP_LINK)
  await expect(page.getByTestId('side-section-COST')).toBeVisible()
}

test.describe('theme port — parity', () => {
  test('nav + page-title paint the light shell directly (var(--paper)/var(--accent))', async ({ page }) => {
    await gotoGrid(page)
    const navBg = await page.locator('.nav').first().evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(navBg).toBe('rgb(245, 247, 250)') // --paper

    const titleColor = await page.locator('.page-title').first().evaluate((el) => getComputedStyle(el).color)
    expect(titleColor).toBe('rgb(0, 128, 94)') // --accent / --cman-green
  })

  test('user-bar + grid-toolbar paint the new gradient (new surface area)', async ({ page }) => {
    await gotoGrid(page)
    for (const selector of ['.user-bar', '.grid-toolbar']) {
      const bgImage = await page.locator(selector).first().evaluate((el) => getComputedStyle(el).backgroundImage)
      expect(bgImage, `${selector} background-image`).toContain('gradient')
      expect(bgImage, `${selector} gradient start stop`).toContain('rgb(0, 128, 94)')
      expect(bgImage, `${selector} gradient end stop`).toContain('rgb(27, 53, 100)')
    }
  })

  test('bare text sitting directly on the gradient bars is white', async ({ page }) => {
    await gotoGrid(page)
    for (const selector of ['.v3-name', '.v3-email', '.v3-division', '.legend', '.legend-note']) {
      const color = await page.locator(selector).first().evaluate((el) => getComputedStyle(el).color)
      expect(color, selector).toBe('rgb(255, 255, 255)')
    }
  })

  test('status legend dots keep Laddawan\'s hues and gain a readability ring on the dark bar', async ({ page }) => {
    await gotoGrid(page)
    const dotColor = (cls: string) => page.locator(`.legend-dot.${cls}`).first().evaluate((el) => getComputedStyle(el).backgroundColor)
    expect(await dotColor('sap')).toBe('rgb(47, 97, 172)') // --status-sap = --cman-blue (post-swap)
    expect(await dotColor('approved')).toBe('rgb(9, 83, 45)') // --status-approved = --cman-green-dark (post-swap)
    expect(await dotColor('pending')).toBe('rgb(162, 74, 14)') // --status-pending = #a24a0e (Laddawan)

    const ringShadow = await page.locator('.legend-dot.sap').first().evaluate((el) => getComputedStyle(el).boxShadow)
    expect(ringShadow, 'legend-dot ring').not.toBe('none')
  })

  test('the 3 radius scales are distinct and match the approved theme (10px/4px/999px)', async ({ page }) => {
    await gotoGrid(page)
    const toolbarRadius = await page.locator('.grid-toolbar').first().evaluate((el) => getComputedStyle(el).borderRadius)
    expect(toolbarRadius, '--r on .grid-toolbar').toBe('10px')

    const pillRadius = await page.locator('.role-badge').first().evaluate((el) => getComputedStyle(el).borderRadius)
    expect(pillRadius, '--r-chip on .role-badge').toBe('999px')

    const cellRadius = await page.locator('.month-value').first().evaluate((el) => getComputedStyle(el).borderRadius)
    expect(cellRadius, '--r-cell on .month-value').toBe('4px')
  })

  test('data-table header text uses the darkened --ink-3 (PRD #25 Phase 4), same as the group-head row', async ({ page }) => {
    await gotoGrid(page)
    // Compared against a fresh reference element rather than a hardcoded rgb
    // string — robust to color-mix()'s exact oklab math, and directly proves
    // "reads the --ink-3 token", which is the actual requirement.
    const [headColor, groupHeadColor, reference] = await Promise.all([
      page.locator('.data-table thead tr.col-row th').first().evaluate((el) => getComputedStyle(el).color),
      page.locator('.data-table thead tr.group-head-row th').first().evaluate((el) => getComputedStyle(el).color),
      page.evaluate(() => {
        const probe = document.createElement('div')
        probe.style.color = 'var(--ink-3)'
        document.body.appendChild(probe)
        const c = getComputedStyle(probe).color
        probe.remove()
        return c
      }),
    ])
    expect(headColor).toBe(reference)
    expect(groupHeadColor).toBe(reference)
  })

  test('pending-readonly money pill is wired to --status-pending, not a hardcoded neutral fill', async ({ page }) => {
    await gotoGrid(page)
    const reference = await page.evaluate(() => {
      const probe = document.createElement('div')
      probe.style.color = 'var(--status-pending)'
      document.body.appendChild(probe)
      const c = getComputedStyle(probe).color
      probe.remove()
      return c
    })
    // :not(.zero) — a $0 month shares this class too, but the LAST rule in
    // the cascade (.month-value.zero, must stay last per this port's own
    // notes) repaints it --ink-3; picking one of those by accident would
    // silently test the wrong rule. m01 is fixture-populated (130,000) so
    // it is never zero.
    const pillColor = await page
      .locator('.month-value.pending-readonly:not(.zero)')
      .first()
      .evaluate((el) => getComputedStyle(el).color)
    expect(pillColor).toBe(reference)
    expect(pillColor).toBe('rgb(162, 74, 14)') // #a24a0e, Laddawan's pending hue
  })
})

test.describe('theme port — CSS <-> TypeScript mirror lock', () => {
  test('measurer header style mirrors the real .data-table thead th typography', async ({ page }) => {
    await gotoGrid(page)
    const [measured, real] = await Promise.all([
      page
        .locator('[data-testid="col-width-measurer"] [data-measure-col="cc"]')
        .first()
        .evaluate((el) => {
          const cs = getComputedStyle(el)
          return { fontSize: cs.fontSize, fontWeight: cs.fontWeight, letterSpacing: cs.letterSpacing, textTransform: cs.textTransform }
        }),
      page
        .locator('.data-table thead tr.col-row th')
        .first()
        .evaluate((el) => {
          const cs = getComputedStyle(el)
          return { fontSize: cs.fontSize, fontWeight: cs.fontWeight, letterSpacing: cs.letterSpacing, textTransform: cs.textTransform }
        }),
    ])
    expect(measured, 'GridTable.tsx headerLabelStyle vs .data-table thead th').toEqual(real)
  })

  test('COLUMN_WIDTH_MEASURE_PADDING mirrors the real cell padding (20px) + the documented 12px slack', async ({ page }) => {
    await gotoGrid(page)
    const paddingLeftRight = await page.locator('.data-table thead th').first().evaluate((el) => {
      const cs = getComputedStyle(el)
      return parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight)
    })
    expect(paddingLeftRight, '.data-table thead th left+right padding').toBe(20)
    expect(COLUMN_WIDTH_MEASURE_PADDING, 'model.ts COLUMN_WIDTH_MEASURE_PADDING').toBe(paddingLeftRight + 12)
  })

  test('MONTH_COLUMN_WIDTH_FLOOR / TOTAL_YEAR_COLUMN_WIDTH_FLOOR mirror the CSS rule they document (98px/112px)', async ({ page }) => {
    // Two reasons this reads the parsed CSSOM rule rather than any rendered
    // element: (1) the REAL rendered <col> takes its width from an inline
    // style (GridTable.tsx's moneyColWidths, a fit-to-content pass) which
    // can legitimately exceed the floor once real money text is wide enough
    // — reading it live would make this test depend on this file's own
    // fixture amounts, not the CSS<->TS relationship it exists to lock; (2)
    // model.ts's own doc comment on these constants says a <col> element's
    // computed style is UA-inconsistent, which is confirmed empirically
    // here too (a detached <col> probe measured 700px, not 98px, in this
    // exact Chromium build) — the parsed stylesheet rule is the one place
    // this value is unambiguous.
    await gotoGrid(page)
    const [monthColWidth, totalYearColWidth] = await page.evaluate(() => {
      const widthOf = (mustInclude: string[], mustExclude: string[]): string | null => {
        for (const sheet of Array.from(document.styleSheets)) {
          let rules: CSSRuleList
          try {
            rules = sheet.cssRules
          } catch {
            continue
          }
          for (const rule of Array.from(rules)) {
            if (!(rule instanceof CSSStyleRule)) continue
            const sel = rule.selectorText
            if (mustInclude.every((s) => sel.includes(s)) && !mustExclude.some((s) => sel.includes(s)) && rule.style.width) {
              return rule.style.width
            }
          }
        }
        return null
      }
      return [widthOf(['.m-col'], ['.total-year-col']), widthOf(['.total-year-col'], [])]
    })
    expect(monthColWidth, '.data-table col.m-col CSS rule width').toBe(`${MONTH_COLUMN_WIDTH_FLOOR}px`)
    expect(totalYearColWidth, '.data-table col.total-year-col CSS rule width').toBe(`${TOTAL_YEAR_COLUMN_WIDTH_FLOOR}px`)
  })
})

test.describe('theme port — frozen-edge shadow', () => {
  test('the edge shadow is present on every body-row state this app renders today', async ({ page }) => {
    await gotoGrid(page)

    const shadowOf = (locator: Locator) => locator.first().evaluate((el) => getComputedStyle(el).boxShadow)

    // Each of the 3 fixed layer sub-rows a transaction always renders
    // (GridTable.tsx: data-status="sap"/"approved"/"pending"), all carrying
    // the shared .frz-5 class the edge-shadow rule keys on.
    for (const status of ['sap', 'approved', 'pending'] as const) {
      const shadow = await shadowOf(page.locator(`tr[data-status="${status}"] .status-cell.frz-5`))
      expect(shadow, `tr[data-status=${status}] .status-cell.frz-5`).not.toBe('none')
    }

    // The group subtotal row (always rendered under a multi-row side/group).
    const subtotalShadow = await shadowOf(page.locator('.subtotal-row .frz-edge'))
    expect(subtotalShadow, '.subtotal-row .frz-edge').not.toBe('none')

    // Hover interaction — production has no tbody-row hover rule (confirmed
    // by grep; that is a prototype-only feature this port does not add), so
    // this proves the shadow survives an interaction event rather than
    // proving a hover-specific fill doesn't clobber it (there is none to
    // clobber it with).
    const firstSapCell = page.locator('tr[data-status="sap"] .status-cell.frz-5').first()
    await firstSapCell.hover()
    const shadowAfterHover = await firstSapCell.evaluate((el) => getComputedStyle(el).boxShadow)
    expect(shadowAfterHover, 'tr[data-status=sap] .status-cell.frz-5 after hover').not.toBe('none')
  })
})
