/** Generator for the theme-shell-green-*.png comparison set (this folder) —
 * renders the main filler grid once per candidate shell palette.
 *
 * NOT part of the e2e suite (playwright.config.ts's testDir is frontend/e2e).
 * To re-run: copy this file into frontend/e2e/, point OUT at a real output
 * dir, `npx playwright test e2e/theme-shell-green-shot.spec.ts --workers=1`,
 * then delete the copy — leaving it there adds screenshot-only tests to every
 * suite run.
 *
 * Nothing on disk changes when it runs: each palette is a runtime
 * `:root:root` override injected after load, so tokens.css / global.css stay
 * untouched.
 *
 * Contrast numbers quoted below are from theme-shell-green-contrast.py
 * (same folder) — WCAG 2.x, AA small text needs 4.5. */
import {
  approvalState,
  CC,
  DEEP_LINK_YEAR,
  DEPT,
  fillerWorld,
  GL_ENTERTAIN_EXT,
  GL_OFFICE_COST,
  GL_OFFICE_SGA,
  installMocks,
  makeBudgetRow,
  test,
  expect,
} from './fixtures'

const OUT = 'C:/04.budget_management_web/design/mockups'

interface Variant {
  /** file suffix: theme-shell-green-<name>.png */
  name: string
  /** extra token overrides on top of the green tier */
  vars: Record<string, string>
}

/** `--paper` (page shell) and `--accent` (button fills) are the same green in
 * this theme, so a shade swap always moves both. */
function greenTier(base: string, step: string): Record<string, string> {
  return {
    '--paper': base,
    '--accent': base,
    '--c-forest': base,
    '--accent-2': step,
    '--c-mint': step,
    '--c-blue': step,
  }
}

const VARIANTS: Variant[] = [
  // 1. Literal swap — jakkaritw's picked shade, every ink/on-shell token left
  //    exactly as the live #1a472a theme has it. Cream 3.67, muted 2.34, gold
  //    1.99: this is the "what the shade really does to the current scheme"
  //    reference render.
  { name: 'sea-2E8B57', vars: greenTier('#2E8B57', '#3FA06E') },

  // 2. Same picked shade, on-shell text pushed to the maximum contrast a light
  //    ink can reach here (white = 4.25 — no light color clears AA 4.5 on this
  //    green). The gold on-shell accent is retired: 1.99 on this shell, dead at
  //    any size, so those spots fall back to white.
  {
    name: 'sea-2E8B57-white-ink',
    vars: {
      ...greenTier('#2E8B57', '#3FA06E'),
      '--ink-on-shell': '#ffffff',
      '--ink-on-shell-2': '#ffffff',
      '--accent-on-shell': '#ffffff',
      '--line-on-shell': 'rgba(255, 255, 255, 0.55)',
    },
  },

  // 3. Sea-green HUE at a depth the current cream+gold scheme still passes on
  //    (#1a4e31: cream 8.33, muted 5.32, gold 4.51, white 9.64) — the
  //    "keep every existing token, change the color only" option.
  { name: 'sea-deep-1A4E31', vars: greenTier('#1a4e31', '#2d6a4f') },
]

for (const variant of VARIANTS) {
  test(`theme shell green — ${variant.name}`, async ({ page }) => {
    const world = fillerWorld({
      budgetGridQueue: [
        [
          makeBudgetRow({
            costCenter: CC,
            glAccount: GL_ENTERTAIN_EXT,
            sap: { m01: 20000, total_year: 20000 },
            pending: { m01: 25000, total_year: 25000 },
            pendingUpdatedAt: 'PEND-ENT',
          }),
          makeBudgetRow({
            costCenter: CC,
            glAccount: GL_OFFICE_COST,
            sap: { m01: 120000, m02: 98500, m03: 110250, total_year: 328750 },
            pending: { m01: 0, total_year: 0 },
            pendingUpdatedAt: 'PEND-COST',
          }),
          makeBudgetRow({
            costCenter: CC,
            glAccount: GL_OFFICE_SGA,
            sap: { m01: 45000, m02: 47500, total_year: 92500 },
            pending: { m01: 50000, m02: 50000, total_year: 100000 },
            pendingUpdatedAt: 'PEND-SGA',
          }),
        ],
      ],
      approvalStatusByDept: { [DEPT]: approvalState() },
    })
    await installMocks(page, world)

    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.goto(`/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`)
    await expect(page.getByRole('button', { name: DEPT })).toBeVisible()
    await expect(page.getByTestId(`txn-${CC}-${GL_OFFICE_SGA}`)).toBeVisible()

    // `:root:root` (specificity 0,2,0) beats tokens.css's plain `:root`
    // regardless of stylesheet order.
    const decls = Object.entries(variant.vars)
      .map(([k, v]) => `${k}:${v};`)
      .join('')
    await page.addStyleTag({ content: `:root:root{${decls}}` })
    await page.waitForTimeout(500)

    await page.screenshot({ path: `${OUT}/theme-shell-green-${variant.name}.png`, fullPage: true })
  })
}
