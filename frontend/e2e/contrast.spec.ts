/** Permanent WCAG contrast ratchet — the Sea Green shell theme (jakkaritw,
 * 2026-08-15) has effectively ZERO regression coverage from the rest of the
 * permanent suite: vitest/jsdom runs no CSS cascade at all, and the 4 e2e
 * journey specs assert text/roles/testids only. Every design token could
 * turn hot pink and 638 unit tests + 26 journey e2e tests would stay green.
 * This spec is the one thing that has ever caught a real theme regression
 * (as a throwaway script, deleted after each use, during the theme work) —
 * promoted here per the gate's 08 verdict so it survives between sessions.
 *
 * WHAT THIS CATCHES — walks every rendered element on each mocked scenario
 * below and, for each one, reads its COMPUTED (already-cascaded) color and
 * flags: text under 4.5:1 (3:1 for WCAG "large text" — font-size>=24px, or
 * >=18.66px at weight>=700) against the background actually painted behind
 * it; ~1px borders under 3:1; and (new here) a keyboard focus-visible ring
 * under 3:1 against the area it's drawn over.
 *
 * WHAT THIS DELIBERATELY IGNORES — this is a RATCHET, not a zero-violation
 * gate: `contrast-baseline.json` holds ~751 pre-existing violations
 * (`--ink-3` #86806f body text at 3.74:1, `--line`/`--line-2` hairline
 * borrows) that are jakkaritw's own accepted design trade-offs, not bugs.
 * The spec asserts only `new == 0` (a violation whose kind+selector+sample
 * key is not in the baseline at all) AND `worsened == 0` (a baselined key
 * whose CURRENT ratio has dropped more than a 0.05 tolerance below the
 * ratio recorded in the baseline) — never `total == 0`. A ratio-less key
 * (just kind+selector) would hide a regression on an already-broken
 * selector getting WORSE (e.g. 5.60 -> 1.83) — the ratio is stored
 * specifically so that class of regression cannot go invisible again.
 *
 * HOW TO UPDATE THE BASELINE — after a deliberate, reviewed design change
 * that legitimately moves the accepted violation set (never as a way to
 * silence a surprise failure):
 *   UPDATE_CONTRAST_BASELINE=1 npx playwright test e2e/contrast.spec.ts
 * This is an explicit, printed act (see the banner in `test.beforeAll`) —
 * it skips every assertion and instead overwrites `contrast-baseline.json`
 * with whatever the current tree measures. Review the resulting diff like
 * any other code change before committing it.
 *
 * TWO BLIND-SPOT FIXES CARRIED OVER FROM THE THROWAWAY VERSION (each one
 * hid a real bug during the theme work — do not re-simplify these away):
 *  1. Borders are checked against BOTH the element's own background (the
 *     fill just inside the box) AND the effective background behind the
 *     element (whatever is rendered just outside the box, walking from the
 *     PARENT) — flagged only if BOTH fail. A border can look fine against
 *     its own fill (e.g. white on a solid green button, ~4.2:1) while being
 *     essentially invisible against the light card it actually sits on
 *     (the SessionExpiredDialog `.btn-submit` case, ~1:1) — checking only
 *     one side missed exactly that.
 *  2. Text is checked using a LEAF-based rule (an element with zero element
 *     children and non-empty `textContent`, OR an element with a direct
 *     text-node child), not "has a direct text-node child" alone — every
 *     element is still walked individually (`querySelectorAll('*')`), so a
 *     wrapper like `.v3-gl-pill` that carries no text of its own is
 *     correctly skipped while its text-bearing children (`.n`/`.t`) are
 *     each checked using THEIR OWN ancestor-walked background, not a
 *     background guessed from the outer wrapper.
 *
 * Also new here: a keyboard FOCUS pass (the throwaway copy had none). Every
 * focusable element is focused via Node-side `Locator.focus()` — NOT
 * `el.focus()` inside `page.evaluate()` — followed by one harmless
 * `page.keyboard.press('Shift')`. Both steps are load-bearing: EVERY
 * scenario here clicks through the UI before the audit runs, and
 * Chromium's `:focus-visible` heuristic tracks the last input modality
 * seen on the PAGE, not just the current focus() call — so even
 * `Locator.focus()` alone still resolves `:focus-visible` to `false`
 * after a prior click (verified empirically); the follow-up keypress is
 * what actually flips it back to keyboard modality (see `focusPass()`'s
 * own doc comment for the measured before/after). The ring's
 * `outline-color` is then read against the background it's drawn over
 * (the ring paints OUTSIDE the box via `outline-offset`, i.e. over the
 * PARENT's background, not the element's own fill). All
 * transitions/animations are disabled page-wide (an injected stylesheet,
 * right after each `page.goto`) for the whole test, not just the focus
 * pass — a mid-transition read on `.btn-add` produced a flaky false `new`
 * violation before this was added.
 *
 * Scenarios reuse the same 9 mocked worlds the throwaway audit covered
 * (`e2e/fixtures.ts` — no live backend/DB is ever touched, matching every
 * other spec in this folder). Wired into the default `npx playwright test`
 * run (`playwright.config.ts`'s `testDir`/`testIgnore` do not exclude this
 * file) — no separate invocation needed for normal CI/local runs.
 *
 * NOTE: imports `test`/`expect` from @playwright/test directly, NOT from
 * ./fixtures — the fixtures wrapper fails a test on any console.error,
 * unrelated to what this spec measures (same reasoning as the throwaway
 * `_contrast-audit.spec.ts` it replaces).
 */
import { test, expect, type Page } from '@playwright/test'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  approverWorld,
  CC,
  DEEP_LINK_YEAR,
  DEPT,
  DEPT2,
  dualRoleAdminWorld,
  fillerWorld,
  GL_ENTERTAIN_EXT,
  GL_OFFICE_COST,
  GL_OFFICE_SGA,
  GL_TRAVEL_PERDIEM_COST,
  installMocks,
  makeBudgetRow,
  noScopeWorld,
  approvalState,
} from './fixtures'

const __dirname = dirname(fileURLToPath(import.meta.url))
const BASELINE_PATH = join(__dirname, 'contrast-baseline.json')
const UPDATE_MODE = process.env.UPDATE_CONTRAST_BASELINE === '1'
const WORSEN_TOLERANCE = 0.05

const DEEP_LINK = `/?dept=${encodeURIComponent(DEPT)}&year=${DEEP_LINK_YEAR}`

function richRows() {
  return [
    makeBudgetRow({
      costCenter: CC,
      glAccount: GL_OFFICE_COST,
      sap: { m01: 120_000, m02: 98_500, m03: 110_250 },
      pending: { m01: 130_000, m02: 100_000, m03: 115_000 },
      pendingUpdatedAt: 'PEND-1',
    }),
    makeBudgetRow({
      costCenter: CC,
      glAccount: GL_OFFICE_SGA,
      sap: { m01: 45_000, m02: 47_500 },
      pending: { m01: 50_000, m02: 50_000 },
      pendingUpdatedAt: 'PEND-2',
    }),
    makeBudgetRow({
      costCenter: CC,
      glAccount: GL_ENTERTAIN_EXT,
      sap: { m01: 20_000 },
      pending: { m01: 25_000 },
      pendingUpdatedAt: 'PEND-ENT-1',
    }),
    makeBudgetRow({
      costCenter: CC,
      glAccount: GL_TRAVEL_PERDIEM_COST,
      sap: { m03: 18_000 },
      pending: { m03: 22_000 },
      pendingUpdatedAt: 'PEND-TRV-1',
    }),
  ]
}

// ---------------------------------------------------------------------------
// Violation + baseline shapes
// ---------------------------------------------------------------------------
interface Violation {
  kind: 'text' | 'border' | 'focus'
  selector: string
  sample: string
  fg: string
  bg: string
  ratio: number
  required: number
}

interface BaselineEntry {
  kind: string
  selector: string
  sample: string
  ratio: number
  required: number
}

/** The baseline key deliberately EXCLUDES fg/bg/rgb — only `kind + selector
 * + sample` (per the gate's ratchet design). Including the raw colors would
 * make every baseline entry churn on every run for no reason; the ratio is
 * tracked SEPARATELY (not part of the key) precisely so a same-key ratio
 * regression ("worsened") is still detectable. */
function keyOf(v: { kind: string; selector: string; sample: string }): string {
  return `${v.kind}|${v.selector}|${v.sample}`
}

function loadBaseline(): Map<string, BaselineEntry> {
  const map = new Map<string, BaselineEntry>()
  if (!existsSync(BASELINE_PATH)) return map
  const raw = JSON.parse(readFileSync(BASELINE_PATH, 'utf-8')) as BaselineEntry[]
  for (const entry of raw) map.set(keyOf(entry), entry)
  return map
}
const baseline = loadBaseline()
/** Only populated/used in UPDATE_MODE — accumulates across all tests in
 * this file. Safe as a plain module-level Map because the whole describe
 * block below is forced to `mode: 'serial'` (one worker, one process). */
const collected = new Map<string, BaselineEntry>()

function dedupe(violations: Violation[]): Violation[] {
  const map = new Map<string, Violation>()
  for (const v of violations) {
    const key = keyOf(v)
    const existing = map.get(key)
    if (!existing || v.ratio < existing.ratio) map.set(key, v)
  }
  return Array.from(map.values())
}

async function assertNoRegressions(violations: Violation[], testName: string) {
  const deduped = dedupe(violations)

  if (UPDATE_MODE) {
    for (const v of deduped) {
      const key = keyOf(v)
      const existing = collected.get(key)
      if (!existing || v.ratio < existing.ratio) {
        collected.set(key, { kind: v.kind, selector: v.selector, sample: v.sample, ratio: v.ratio, required: v.required })
      }
    }
    console.log(`[contrast] ${testName}: recorded ${deduped.length} violation(s) toward the new baseline`)
    return
  }

  const newOnes: Violation[] = []
  const worsened: { v: Violation; baselineRatio: number }[] = []
  for (const v of deduped) {
    const base = baseline.get(keyOf(v))
    if (!base) {
      newOnes.push(v)
      continue
    }
    if (base.ratio - v.ratio > WORSEN_TOLERANCE) worsened.push({ v, baselineRatio: base.ratio })
  }

  if (newOnes.length === 0 && worsened.length === 0) return

  const lines: string[] = []
  if (newOnes.length > 0) {
    lines.push(`${newOnes.length} NEW violation(s) not in contrast-baseline.json:`)
    for (const v of newOnes) {
      lines.push(`  [NEW]     ${v.kind} ${v.selector} "${v.sample}" ratio=${v.ratio} (needs ${v.required}) fg=${v.fg} bg=${v.bg}`)
    }
  }
  if (worsened.length > 0) {
    lines.push(`${worsened.length} WORSENED violation(s) (dropped more than ${WORSEN_TOLERANCE} below the baseline ratio):`)
    for (const { v, baselineRatio } of worsened) {
      lines.push(`  [WORSE]   ${v.kind} ${v.selector} "${v.sample}" ${baselineRatio} -> ${v.ratio} (fg=${v.fg} bg=${v.bg})`)
    }
  }
  throw new Error(`contrast ratchet failed on "${testName}":\n${lines.join('\n')}`)
}

// ---------------------------------------------------------------------------
// In-page checks — each function below is handed whole to `page.evaluate()`,
// so it must be fully self-contained (no closures over the outer module);
// the color-parsing/effective-background helpers are duplicated between the
// two functions for that reason.
// ---------------------------------------------------------------------------

/** Full-DOM structural pass: text contrast + border contrast (both
 * blind-spot fixes, see file header). */
function structuralAudit(): Violation[] {
  // Chromium serializes some computed colors (e.g. anything that went
  // through `color-mix(in oklab, ...)`) as `oklab(...)`, not `rgb()` — a
  // plain rgb()-only regex silently treats those as unparseable and skips
  // right past an OPAQUE layer as if it were transparent, which then
  // misreports the far-away shell color underneath as the "effective
  // background". Canvas 2D's fillStyle setter/getter accepts and
  // normalizes EVERY valid CSS color syntax (oklab, oklch, color(), hsl,
  // named, color-mix results, etc.) to a plain hex/rgba string — used here
  // purely as a color-space normalizer, nothing is ever drawn.
  const normCanvas = document.createElement('canvas')
  const normCtx = normCanvas.getContext('2d') as CanvasRenderingContext2D
  function normalize(str: string): string {
    normCtx.fillStyle = '#000000'
    try {
      normCtx.fillStyle = str
    } catch {
      /* leave as reset default if the browser truly can't parse it */
    }
    return normCtx.fillStyle
  }

  // Chromium's canvas fillStyle does NOT round-trip `oklab()`/`oklch()`,
  // so the normalizer above hands them back unparseable — convert
  // explicitly instead (Ottosson's oklab -> linear sRGB -> gamma).
  function oklabToRgb(L: number, a: number, b: number) {
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
    const lin = [
      4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
    ]
    const [r, g, bb] = lin.map((c) => {
      const v = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.abs(c) ** (1 / 2.4) - 0.055
      return Math.max(0, Math.min(255, Math.round(v * 255)))
    })
    return { r, g, b: bb }
  }

  function parseModernColor(str: string): { r: number; g: number; b: number; a: number } | null {
    const m = str.match(/^okl(ab|ch)\(([^)]+)\)$/i)
    if (!m) return null
    const parts = m[2].split('/')
    const nums = parts[0].trim().split(/\s+/).map(parseFloat)
    const alpha = parts[1] !== undefined ? parseFloat(parts[1]) : 1
    if (nums.length < 3 || nums.some(Number.isNaN)) return null
    const [L, x, y] = nums
    const [aa, bb] =
      m[1].toLowerCase() === 'ch' ? [x * Math.cos((y * Math.PI) / 180), x * Math.sin((y * Math.PI) / 180)] : [x, y]
    return { ...oklabToRgb(L, aa, bb), a: Number.isNaN(alpha) ? 1 : alpha }
  }

  function parseColor(str: string | null): { r: number; g: number; b: number; a: number } | null {
    if (!str) return null
    if (str === 'transparent') return { r: 0, g: 0, b: 0, a: 0 }
    const modern = parseModernColor(str.trim())
    if (modern) return modern
    const normalized = normalize(str)
    const hexMatch = normalized.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i)
    if (hexMatch) {
      return { r: parseInt(hexMatch[1], 16), g: parseInt(hexMatch[2], 16), b: parseInt(hexMatch[3], 16), a: 1 }
    }
    const m = normalized.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/)
    if (!m) return null
    return { r: parseFloat(m[1]), g: parseFloat(m[2]), b: parseFloat(m[3]), a: m[4] !== undefined ? parseFloat(m[4]) : 1 }
  }

  function effectiveBackground(el: Element): { r: number; g: number; b: number } {
    const chain: { r: number; g: number; b: number; a: number }[] = []
    let node: Element | null = el
    while (node) {
      const bg = parseColor(getComputedStyle(node).backgroundColor)
      if (bg && bg.a > 0) chain.push(bg)
      if (bg && bg.a >= 0.999) break
      node = node.parentElement
    }
    let acc = { r: 255, g: 255, b: 255 }
    for (let i = chain.length - 1; i >= 0; i--) {
      const layer = chain[i]
      acc = {
        r: layer.r * layer.a + acc.r * (1 - layer.a),
        g: layer.g * layer.a + acc.g * (1 - layer.a),
        b: layer.b * layer.a + acc.b * (1 - layer.a),
      }
    }
    return acc
  }

  function effectiveForeground(el: Element, cs: CSSStyleDeclaration): { r: number; g: number; b: number } {
    const fg = parseColor(cs.color)
    if (!fg) return { r: 0, g: 0, b: 0 }
    if (fg.a >= 0.999) return fg
    const bg = effectiveBackground(el)
    return {
      r: fg.r * fg.a + bg.r * (1 - fg.a),
      g: fg.g * fg.a + bg.g * (1 - fg.a),
      b: fg.b * fg.a + bg.b * (1 - fg.a),
    }
  }

  function luminance({ r, g, b }: { r: number; g: number; b: number }): number {
    const lin = (c: number) => {
      c /= 255
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
  }

  function ratio(c1: { r: number; g: number; b: number }, c2: { r: number; g: number; b: number }): number {
    const l1 = luminance(c1)
    const l2 = luminance(c2)
    const hi = Math.max(l1, l2)
    const lo = Math.min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)
  }

  function describe(el: Element): string {
    const cls = typeof el.className === 'string' && el.className.trim() ? `.${el.className.trim().replace(/\s+/g, '.')}` : ''
    return `${el.tagName.toLowerCase()}${cls}`
  }

  function rgbString(c: { r: number; g: number; b: number }): string {
    return `rgb(${Math.round(c.r)}, ${Math.round(c.g)}, ${Math.round(c.b)})`
  }

  const violations: Violation[] = []
  const all = document.body.querySelectorAll('*')

  for (const el of Array.from(all)) {
    if (el.closest('svg')) continue
    const tag = el.tagName
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') continue

    const rect = el.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) continue
    const cs = getComputedStyle(el)
    if (cs.visibility === 'hidden' || cs.display === 'none') continue
    if (parseFloat(cs.opacity) === 0) continue

    // Blind-spot fix 2 (nested text): a plain "direct text-node child"
    // check alone is what missed `.v3-gl-pill` in the throwaway version —
    // its own visible text lives entirely in child `.n`/`.t` spans, so it
    // correctly has none. We still catch that text correctly because we
    // walk EVERY element (`querySelectorAll('*')`) and check each leaf
    // independently — a zero-children element with non-empty `textContent`
    // is also treated as text-bearing even when its content did not arrive
    // as a literal direct text-node child. Either way, the check always
    // runs against THAT element's own ancestor-walked background
    // (`effectiveBackground`/`effectiveForeground` below), never a
    // background guessed from an outer wrapper.
    let hasOwnText = false
    if (el.children.length === 0) {
      hasOwnText = (el.textContent ?? '').trim().length > 0
    } else {
      for (const child of Array.from(el.childNodes)) {
        if (child.nodeType === 3 && (child.textContent ?? '').trim().length > 0) {
          hasOwnText = true
          break
        }
      }
    }

    if (hasOwnText) {
      const fg = effectiveForeground(el, cs)
      const bg = effectiveBackground(el)
      const fontSize = parseFloat(cs.fontSize)
      const weight = parseInt(cs.fontWeight, 10) || 400
      const isLarge = fontSize >= 24 || (weight >= 700 && fontSize >= 18.66)
      const required = isLarge ? 3.0 : 4.5
      const r = ratio(fg, bg)
      if (r < required - 0.005) {
        violations.push({
          kind: 'text',
          selector: describe(el),
          sample: (el.textContent ?? '').trim().slice(0, 40),
          fg: rgbString(fg),
          bg: rgbString(bg),
          ratio: Math.round(r * 100) / 100,
          required,
        })
      }
    }

    // ~1px solid borders — one representative side is enough (this
    // codebase uses uniform `border: 1px solid ...` shorthand throughout).
    for (const side of ['Top', 'Right', 'Bottom', 'Left'] as const) {
      const width = parseFloat(cs[`border${side}Width` as 'borderTopWidth'])
      const style = cs[`border${side}Style` as 'borderTopStyle']
      if (!(width >= 0.5 && width <= 1.5) || style === 'none') continue
      const borderColor = parseColor(cs[`border${side}Color` as 'borderTopColor'])
      if (!borderColor || borderColor.a <= 0) continue

      // Blind-spot fix 1 (border): check against BOTH the element's OWN
      // effective background (the fill just inside the box — walk starts
      // AT `el`) and the background behind the element (whatever renders
      // just outside the box — walk starts at the PARENT, skipping el's
      // own fill layer). A white border on a solid-green button can read
      // fine against its own fill (~4.2:1) while being nearly invisible
      // against the light card that button actually sits on
      // (SessionExpiredDialog's `.btn-submit`, ~1:1) — checking only one
      // side missed exactly that. Flag only if BOTH fail.
      const ownBg = effectiveBackground(el)
      const behindBg = effectiveBackground(el.parentElement ?? el)
      const composite = (bg: { r: number; g: number; b: number }) =>
        borderColor.a >= 0.999
          ? borderColor
          : {
              r: borderColor.r * borderColor.a + bg.r * (1 - borderColor.a),
              g: borderColor.g * borderColor.a + bg.g * (1 - borderColor.a),
              b: borderColor.b * borderColor.a + bg.b * (1 - borderColor.a),
            }
      const ratioOwn = ratio(composite(ownBg), ownBg)
      const ratioBehind = ratio(composite(behindBg), behindBg)
      if (ratioOwn < 3.0 - 0.005 && ratioBehind < 3.0 - 0.005) {
        const worse = ratioOwn <= ratioBehind ? { r: ratioOwn, bg: ownBg } : { r: ratioBehind, bg: behindBg }
        violations.push({
          kind: 'border',
          selector: `${describe(el)} (border-${side.toLowerCase()})`,
          sample: '',
          fg: rgbString(composite(worse.bg)),
          bg: rgbString(worse.bg),
          ratio: Math.round(worse.r * 100) / 100,
          required: 3.0,
        })
      }
      break
    }
  }

  return violations
}

/** Focus-ring pass: reads `document.activeElement` only — called once per
 * focused element from `focusPass()` below, right after a Node-side
 * `Locator.focus()`. Self-contained for the same page.evaluate()
 * serialization reason as `structuralAudit` above (small helper
 * duplication is intentional, not an oversight). */
function focusRingViolation(): Violation | null {
  function parseColor(str: string | null): { r: number; g: number; b: number; a: number } | null {
    if (!str) return null
    if (str === 'transparent') return { r: 0, g: 0, b: 0, a: 0 }
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d') as CanvasRenderingContext2D
    ctx.fillStyle = '#000000'
    try {
      ctx.fillStyle = str
    } catch {
      /* leave reset default */
    }
    const normalized = ctx.fillStyle
    const hexMatch = normalized.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i)
    if (hexMatch) {
      return { r: parseInt(hexMatch[1], 16), g: parseInt(hexMatch[2], 16), b: parseInt(hexMatch[3], 16), a: 1 }
    }
    const m = normalized.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/)
    if (!m) return null
    return { r: parseFloat(m[1]), g: parseFloat(m[2]), b: parseFloat(m[3]), a: m[4] !== undefined ? parseFloat(m[4]) : 1 }
  }

  function effectiveBackground(el: Element): { r: number; g: number; b: number } {
    const chain: { r: number; g: number; b: number; a: number }[] = []
    let node: Element | null = el
    while (node) {
      const bg = parseColor(getComputedStyle(node).backgroundColor)
      if (bg && bg.a > 0) chain.push(bg)
      if (bg && bg.a >= 0.999) break
      node = node.parentElement
    }
    let acc = { r: 255, g: 255, b: 255 }
    for (let i = chain.length - 1; i >= 0; i--) {
      const layer = chain[i]
      acc = {
        r: layer.r * layer.a + acc.r * (1 - layer.a),
        g: layer.g * layer.a + acc.g * (1 - layer.a),
        b: layer.b * layer.a + acc.b * (1 - layer.a),
      }
    }
    return acc
  }

  function luminance({ r, g, b }: { r: number; g: number; b: number }): number {
    const lin = (c: number) => {
      c /= 255
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
  }

  function ratio(c1: { r: number; g: number; b: number }, c2: { r: number; g: number; b: number }): number {
    const l1 = luminance(c1)
    const l2 = luminance(c2)
    const hi = Math.max(l1, l2)
    const lo = Math.min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)
  }

  function describe(el: Element): string {
    const cls = typeof el.className === 'string' && el.className.trim() ? `.${el.className.trim().replace(/\s+/g, '.')}` : ''
    return `${el.tagName.toLowerCase()}${cls}`
  }

  function rgbString(c: { r: number; g: number; b: number }): string {
    return `rgb(${Math.round(c.r)}, ${Math.round(c.g)}, ${Math.round(c.b)})`
  }

  function sampleFor(el: Element): string {
    const text = (el.textContent ?? '').trim()
    if (text) return text.slice(0, 40)
    const aria = el.getAttribute('aria-label')
    if (aria) return aria.slice(0, 40)
    const testid = el.getAttribute('data-testid')
    if (testid) return `[data-testid=${testid}]`
    const href = el.getAttribute('href')
    if (href) return `[href=${href}]`
    return ''
  }

  const el = document.activeElement
  if (!el || el === document.body) return null
  // Only elements the browser itself judges to be showing a keyboard-style
  // ring are worth checking — our CSS only styles `:focus-visible`
  // (global.css), so an element that does NOT match it falls back to
  // whatever native default the browser would show (or none), which this
  // spec is not trying to police.
  if (!el.matches(':focus-visible')) return null

  const cs = getComputedStyle(el)
  if (cs.outlineStyle === 'none') return null
  const outlineWidth = parseFloat(cs.outlineWidth)
  if (!(outlineWidth > 0)) return null
  const outlineColor = parseColor(cs.outlineColor)
  if (!outlineColor || outlineColor.a <= 0) return null

  // `outline-offset` paints the ring OUTSIDE the box, so the background it
  // sits over is the PARENT's effective background, not the element's own
  // fill (same "behind the element" concept as the border fix above).
  const behindBg = effectiveBackground(el.parentElement ?? el)
  const composited =
    outlineColor.a >= 0.999
      ? outlineColor
      : {
          r: outlineColor.r * outlineColor.a + behindBg.r * (1 - outlineColor.a),
          g: outlineColor.g * outlineColor.a + behindBg.g * (1 - outlineColor.a),
          b: outlineColor.b * outlineColor.a + behindBg.b * (1 - outlineColor.a),
        }
  const r = ratio(composited, behindBg)
  if (r >= 3.0 - 0.005) return null

  return {
    kind: 'focus',
    selector: `${describe(el)} (focus-ring)`,
    sample: sampleFor(el),
    fg: rgbString(composited),
    bg: rgbString(behindBg),
    ratio: Math.round(r * 100) / 100,
    required: 3.0,
  }
}

const DISABLE_MOTION_CSS = `*, *::before, *::after { transition: none !important; animation: none !important; }`

/** Injected right after each `page.goto()`, before any interaction — a
 * mid-transition read (e.g. `.btn-add`'s hover/appear transition) produced
 * a flaky false "new" violation before this existed. Covers the WHOLE test,
 * not just the focus pass, since the structural walk hit the same flake. */
async function preparePage(page: Page): Promise<void> {
  await page.addStyleTag({ content: DISABLE_MOTION_CSS })
}

const FOCUSABLE_SELECTOR = 'button, a[href], input, select, textarea, [tabindex]'

/** Focuses every visible, enabled, in-tab-order element on the CURRENT page
 * state (no re-navigation — folded into the same page visit the structural
 * pass already did) via Node-side `Locator.focus()`, reading the ring
 * contrast after each one. Deliberately does NOT de-duplicate by
 * tag+class: this codebase repoints `--focus-ring` per ANCESTOR context
 * (e.g. `.approval-bar .btn-submit` vs `.btn-submit` inside a plain
 * `.modal`, or `.approval-bar > .btn-reject`'s direct-child combinator
 * distinguishing it from the SAME class's second instance inside
 * `.reject-panel`) — two elements sharing a class can legitimately have
 * different effective rings, so every instance is checked individually.
 *
 * The `page.keyboard.press('Shift')` right after `focus()` is load-bearing,
 * not decorative: every scenario in this file clicks through the UI (opens
 * a picker/subform/reject-panel/admin-toggle) BEFORE the audit runs, and
 * Chromium's `:focus-visible` heuristic keys off the LAST input modality
 * seen anywhere on the page, not just "was this particular focus() call
 * synthetic" — so `Locator.focus()` alone still resolves `:focus-visible`
 * to `false` (and `outline-style: none`) after a prior mouse click,
 * silently skipping the whole ring check (verified empirically against
 * `.btn-approve` in the "05 approver" scenario: `focus-visible=false`
 * right after `.focus()`, `true` the instant a harmless key is pressed on
 * the now-focused element — Shift alone has no side effect on any control
 * in this app: no text insertion, no dropdown open, no button activation).
 * A bare page freshly loaded with NO prior click does not need the nudge
 * (proven separately), but every real scenario here has one, so the nudge
 * always runs. */
async function focusPass(page: Page): Promise<Violation[]> {
  const infos = await page.locator(FOCUSABLE_SELECTOR).evaluateAll((els) =>
    els.map((el) => {
      const e = el as HTMLElement
      const rect = e.getBoundingClientRect()
      const cs = getComputedStyle(e)
      const visible = rect.width > 0 && rect.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'
      const disabled = 'disabled' in e && (e as HTMLButtonElement).disabled === true
      const tabindex = e.getAttribute('tabindex')
      return { visible, disabled, skip: tabindex === '-1' }
    }),
  )

  const violations: Violation[] = []
  for (let i = 0; i < infos.length; i++) {
    const info = infos[i]
    if (!info.visible || info.disabled || info.skip) continue
    const locator = page.locator(FOCUSABLE_SELECTOR).nth(i)
    try {
      await locator.focus()
      await page.keyboard.press('Shift')
    } catch {
      continue // an element that changed under us (e.g. detached) — skip, not a violation
    }
    const v = await page.evaluate(focusRingViolation)
    if (v) violations.push(v)
  }
  return violations
}

async function auditPage(page: Page): Promise<Violation[]> {
  const structural = await page.evaluate(structuralAudit)
  const focus = await focusPass(page)
  return [...structural, ...focus]
}

// ---------------------------------------------------------------------------
// Scenarios — same 9 mocked worlds the throwaway `_contrast-audit.spec.ts`
// covered (filler grid, department picker, special-GL subform, trip
// manager, approver pending + rejected, admin + admin-mode + attachments,
// no-scope empty state, fullscreen grid overlay).
// ---------------------------------------------------------------------------
test.describe('contrast ratchet — Sea Green shell theme', () => {
  // Forced serial (single worker, one process) so `collected` (used only in
  // UPDATE_MODE) can safely accumulate across tests in this file — without
  // this, playwright.config.ts's `fullyParallel: true` could shard these
  // tests across separate worker processes with no shared memory.
  test.describe.configure({ mode: 'serial' })

  test.beforeAll(() => {
    if (UPDATE_MODE) {
      console.log('[contrast] UPDATE_CONTRAST_BASELINE=1 — regenerating contrast-baseline.json; ratchet assertions are SKIPPED this run')
    }
  })

  test.afterAll(() => {
    if (!UPDATE_MODE) return
    const sorted = Array.from(collected.values()).sort(
      (a, b) => a.kind.localeCompare(b.kind) || a.selector.localeCompare(b.selector) || a.sample.localeCompare(b.sample),
    )
    writeFileSync(BASELINE_PATH, `${JSON.stringify(sorted, null, 2)}\n`, 'utf-8')
    console.log(`[contrast] wrote ${sorted.length} baseline entries to ${BASELINE_PATH}`)
  })

  test('01 filler main grid', async ({ page }) => {
    await installMocks(page, fillerWorld({ budgetGridQueue: [richRows(), richRows(), richRows()] }))
    await page.goto(DEEP_LINK)
    await preparePage(page)
    await expect(page.getByTestId('side-section-COST')).toBeVisible()
    await assertNoRegressions(await auditPage(page), '01 filler main grid')
  })

  test('02 department picker open', async ({ page }) => {
    await installMocks(page, fillerWorld({ budgetGridQueue: [richRows(), richRows()] }))
    await page.goto(DEEP_LINK)
    await preparePage(page)
    await page.getByRole('button', { name: DEPT }).click()
    await assertNoRegressions(await auditPage(page), '02 department picker open')
  })

  test('03 special-GL subform (Entertainment) + new line', async ({ page }) => {
    await installMocks(page, fillerWorld({ budgetGridQueue: [richRows(), richRows()], detailLinesQueue: [[]] }))
    await page.goto(DEEP_LINK)
    await preparePage(page)
    await page.getByTestId(`open-subform-${CC}-${GL_ENTERTAIN_EXT}`).click()
    await expect(page.getByTestId('detail-subform')).toBeVisible()
    await page.getByRole('button', { name: '+ เพิ่มรายการ' }).click()
    await assertNoRegressions(await auditPage(page), '03 special-GL subform')
  })

  test('04 trip manager + new trip', async ({ page }) => {
    await installMocks(page, fillerWorld({ budgetGridQueue: [richRows(), richRows()], tripsQueue: [[]], detailLinesQueue: [[]] }))
    await page.goto(DEEP_LINK)
    await preparePage(page)
    await page.getByTestId(`open-subform-${CC}-${GL_TRAVEL_PERDIEM_COST}`).click()
    await expect(page.getByTestId('trip-manager')).toBeVisible()
    await page.getByRole('button', { name: '+ เพิ่มทริป' }).click()
    await expect(page.getByTestId('trip-card-new-0')).toBeVisible()
    await assertNoRegressions(await auditPage(page), '04 trip manager')
  })

  test('05 approver view — pending, approve/reject visible + reject panel open', async ({ page }) => {
    const world = approverWorld({
      budgetGridQueue: [richRows(), richRows()],
      approvalStatusByDept: {
        [DEPT2]: approvalState({ department: DEPT2, status: 'PENDING_APPROVER1', can_act: true, current_position: 'Manager' }),
      },
    })
    await installMocks(page, world)
    await page.goto(`/?dept=${encodeURIComponent(DEPT2)}&year=${DEEP_LINK_YEAR}`)
    await preparePage(page)
    await expect(page.getByTestId('approval-status-chip')).toBeVisible()
    await page.getByTestId('approval-reject-btn').click()
    await expect(page.getByTestId('approval-reject-panel')).toBeVisible()
    await assertNoRegressions(await auditPage(page), '05 approver pending + reject panel')
  })

  test('06 approver view — rejected status + reject reason', async ({ page }) => {
    const world = approverWorld({
      budgetGridQueue: [richRows(), richRows()],
      approvalStatusByDept: {
        [DEPT2]: approvalState({ department: DEPT2, status: 'REJECTED', reject_reason: 'ยอดรวมไม่ตรงกับที่ตกลงไว้ กรุณาแก้ไข' }),
      },
    })
    await installMocks(page, world)
    await page.goto(`/?dept=${encodeURIComponent(DEPT2)}&year=${DEEP_LINK_YEAR}`)
    await preparePage(page)
    await expect(page.getByTestId('approval-status-chip')).toBeVisible()
    await assertNoRegressions(await auditPage(page), '06 approver rejected status')
  })

  test('07 admin view + admin mode on + attachments modal', async ({ page }) => {
    const world = dualRoleAdminWorld({ budgetGridQueue: [richRows(), richRows(), richRows()] })
    await installMocks(page, world)
    await page.goto(DEEP_LINK)
    await preparePage(page)
    await expect(page.getByTestId('admin-mode-toggle')).toBeVisible()
    await page.getByTestId('admin-mode-toggle').click()
    await expect(page.getByTestId('admin-mode-checkbox')).toBeChecked()
    // The toggle triggers an ASYNC refetch (admin_view_enabled=true, same
    // pattern as admin-journey.spec.ts 3.1) that flips many cells' editable
    // styling — waiting only for the checkbox's own (synchronous) checked
    // state raced the grid's re-render and made this scenario's violation
    // count flaky across runs (measured 28/79/81 on 3 back-to-back runs of
    // the exact same code). Poll for the refetch landing, THEN let the
    // network fully settle before auditing.
    await expect.poll(() => world.captured.budgetQueries.at(-1)?.admin_view_enabled).toBe('true')
    await page.waitForLoadState('networkidle')
    await assertNoRegressions(await auditPage(page), '07a admin mode on')

    await page.getByRole('button', { name: 'แนบไฟล์' }).click()
    await expect(page.getByTestId('attachments-modal')).toBeVisible()
    await assertNoRegressions(await auditPage(page), '07b attachments modal')
  })

  test('08 no-scope empty state', async ({ page }) => {
    await installMocks(page, noScopeWorld())
    await page.goto('/')
    await preparePage(page)
    await expect(page.getByTestId('no-scope-empty-state')).toBeVisible()
    await assertNoRegressions(await auditPage(page), '08 no-scope empty state')
  })

  test('09 fullscreen grid overlay', async ({ page }) => {
    await installMocks(page, fillerWorld({ budgetGridQueue: [richRows(), richRows()] }))
    await page.goto(DEEP_LINK)
    await preparePage(page)
    await page.getByTestId('enter-fullscreen-btn').first().click()
    await assertNoRegressions(await auditPage(page), '09 fullscreen grid overlay')
  })
})
