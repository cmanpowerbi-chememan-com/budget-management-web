# Plan — Grid fullscreen toggle (⤢ top-left of the budget grid)

**Owner of implementation:** Kimi Code (acts as `05-software-developer`)
**Author of plan:** Claude Code session, 2026-07-31
**Category / route:** NEW_FEATURE (lean) → design (this doc) → GATE ✅ approved by jakkaritw → implement → ONE combined gate agent (06 review + 07 security + 08 test) → deploy needs jakkaritw approval
**Tracker id:** `grid-fullscreen-toggle` (Kimi: `python tracker/task.py add --id grid-fullscreen-toggle --state doing --ai "..." --agent kimi` BEFORE the first edit)

---

## 1. What the user asked for

Screenshot annotation: *"on left top corner add, enlarge symbol to expand table full view on screen"*.

Locked by AskUserQuestion (2026-07-31, jakkaritw):

| Question | Answer |
|---|---|
| What expands? | **Whole grid page** — COST **and** SG&A tables together, page chrome covered |
| Interactivity in fullscreen? | **Everything still works** — edit month cells, remark, delete row, subform ↗, Submit, year/dept picker |

So: fullscreen = the whole `.budget-grid` block lifted into a fixed overlay that covers the nav + page head. Not a browser-native F11 (`requestFullscreen`) — see §8.

---

## 2. Files to touch (4)

| File | Change |
|---|---|
| [frontend/src/grid/GridTable.tsx](../frontend/src/grid/GridTable.tsx) | 2 new optional props, 2 labels, 2 icons, 1 button rendered in the group-head-row's first frozen `<th>` |
| [frontend/src/grid/BudgetGrid.tsx](../frontend/src/grid/BudgetGrid.tsx) | owns `isFullscreen` state, applies `is-fullscreen` to its root div, Esc + body-scroll-lock effect |
| [frontend/src/styles/global.css](../frontend/src/styles/global.css) | `.fs-toggle-btn` (near `.col-toggle-btn`, ~line 1054) + `.budget-grid.is-fullscreen` rules |
| [frontend/src/grid/GridTable.test.tsx](../frontend/src/grid/GridTable.test.tsx) + [BudgetGrid.test.tsx](../frontend/src/grid/BudgetGrid.test.tsx) | new `describe` blocks, §6 |

No backend, no API, no DB, no model.ts change. `model.ts` colSpan helpers stay untouched — see the invariant in §5.1.

---

## 3. Why state lives in `BudgetGrid`, button lives in `GridTable`

The button must sit in the table's top-left corner → its JSX belongs to `GridTable`.
The overlay must contain the toolbar (year picker, dept picker, Submit), the legend, the admin zone and the add-transaction form → all of those live in `BudgetGrid`, **outside** `GridTable` ([BudgetGrid.tsx:333-481](../frontend/src/grid/BudgetGrid.tsx#L333)).

If state stayed local to `GridTable` (like `columnsCollapsed` does at [GridTable.tsx:562](../frontend/src/grid/GridTable.tsx#L562)) the overlay could only ever contain the two tables, and Submit / add-row / year-switch would be unreachable in fullscreen — which contradicts the locked answer "ใช้งานได้ครบเหมือนเดิม".

→ **state in `BudgetGrid`, presentation callback down to `GridTable`.** Same shape as the existing `onOpenSpecial` / `onDeleteRow` props.

Not persisted (no `localStorage`) — same policy already approved for `columnsCollapsed`: always starts collapsed/normal on load.

---

## 4. Implementation sketch

### 4.1 `GridTable.tsx`

Props (both **optional** so the ~40 existing `render(<GridTable …/>)` calls in the test file keep compiling):

```tsx
type GridTableProps = {
  // …existing…
  /** Fullscreen presentation state — owned by BudgetGrid (see plan §3). */
  isFullscreen?: boolean
  /** Flip fullscreen. Undefined in isolated/unit renders → button is a no-op. */
  onToggleFullscreen?: () => void
}
```

Labels next to the existing ones at [GridTable.tsx:85-86](../frontend/src/grid/GridTable.tsx#L85):

```tsx
const ENTER_FULLSCREEN_LABEL = 'ขยายตารางเต็มหน้าจอ'
const EXIT_FULLSCREEN_LABEL = 'ย่อกลับขนาดปกติ (Esc)'
```

Icons in the same style as `ChevronsLeftIcon` / `ChevronsRightIcon` ([GridTable.tsx:94-112](../frontend/src/grid/GridTable.tsx#L94)) — `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `strokeWidth="2"`, round caps:

```tsx
function MaximizeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M15 3h6v6" /><path d="M9 21H3v-6" /><path d="M21 3l-7 7" /><path d="M3 21l7-7" />
    </svg>
  )
}
function MinimizeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 10h6V4" /><path d="M10 14H4v6" /><path d="M14 10l7-7" /><path d="M10 14l-7 7" />
    </svg>
  )
}
```

One shared JSX node declared just before `return` (the group-head-row has **two** branches — collapsed `colSpan={2}` and expanded `colSpan={4}` — and the button goes in both):

```tsx
const fullscreenToggle = (
  <button
    type="button"
    className="fs-toggle-btn"
    title={isFullscreen ? EXIT_FULLSCREEN_LABEL : ENTER_FULLSCREEN_LABEL}
    aria-label={isFullscreen ? EXIT_FULLSCREEN_LABEL : ENTER_FULLSCREEN_LABEL}
    aria-pressed={isFullscreen}
    data-testid={isFullscreen ? 'exit-fullscreen-btn' : 'enter-fullscreen-btn'}
    onClick={() => onToggleFullscreen?.()}
  >
    {isFullscreen ? <MinimizeIcon /> : <MaximizeIcon />}
  </button>
)
```

Placed in the group-head row at [GridTable.tsx:805-816](../frontend/src/grid/GridTable.tsx#L805) — **children only, colSpan/className unchanged**:

```tsx
<tr className="group-head-row">
  {columnsCollapsed ? (
    <th colSpan={2} className="frz frz-1 frz-edge">{fullscreenToggle}</th>
  ) : (
    <>
      <th colSpan={4} className="frz frz-1">{fullscreenToggle}</th>
      <th className="frz frz-5 frz-edge" />
    </>
  )}
  …
```

That `<th>` is already `position: sticky` ([global.css:944-970](../frontend/src/styles/global.css#L944)) so it is a containing block — `position: absolute` inside it works, no extra wrapper needed.

Both side-tables render this row → **2 button instances** on a page with COST + SG&A, exactly like `collapse-columns-btn` today. Either one flips the ONE shared state. Tests must use `getAllByTestId(...)[0]` (the existing file documents this at [GridTable.test.tsx:694-699](../frontend/src/grid/GridTable.test.tsx#L694)).

### 4.2 `BudgetGrid.tsx`

```tsx
const [isFullscreen, setIsFullscreen] = useState(false)

// Fullscreen side-effects: lock the page behind the overlay so a wheel scroll
// moves the grid, not the covered page; Esc as the convenience exit (the ⤡
// button is the primary one). Cleanup restores everything, including on an
// unmount that happens WHILE fullscreen (scope switch, route change).
useEffect(() => {
  if (!isFullscreen) return
  const prevOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== 'Escape' || e.defaultPrevented) return
    const tag = (e.target as HTMLElement | null)?.tagName
    // Esc inside a field belongs to that field/dropdown (AddTransactionForm's
    // GL list closes on Esc, GridTable.tsx filter inputs, month-cell inputs).
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
    // Esc with a subform/trip modal open belongs to the modal, not the grid.
    if (document.querySelector('.modal-backdrop')) return
    setIsFullscreen(false)
  }
  window.addEventListener('keydown', onKey)
  return () => {
    document.body.style.overflow = prevOverflow
    window.removeEventListener('keydown', onKey)
  }
}, [isFullscreen])
```

Root div at [BudgetGrid.tsx:334](../frontend/src/grid/BudgetGrid.tsx#L334):

```tsx
<div className={`budget-grid${isFullscreen ? ' is-fullscreen' : ''}`} data-testid="budget-grid">
```

Pass down at the `<GridTable …>` call ([BudgetGrid.tsx:425](../frontend/src/grid/BudgetGrid.tsx#L425)):

```tsx
isFullscreen={isFullscreen}
onToggleFullscreen={() => setIsFullscreen((v) => !v)}
```

The early-return no-scope branch ([BudgetGrid.tsx:319-329](../frontend/src/grid/BudgetGrid.tsx#L319)) is left alone — no table, no button there.

### 4.3 `global.css`

Append after the `.col-toggle-btn` block (~line 1054):

```css
/* Fullscreen toggle (⤢) — top-LEFT corner of each side-table's group-head
   band (mirror of .col-toggle-btn, which sits top-right on Status). Both
   side-tables render one; either flips the ONE shared state, which lives in
   BudgetGrid because the overlay must also contain the toolbar/Submit. */
.fs-toggle-btn {
  position: absolute;
  top: 2px;
  left: 8px;
  width: 18px;
  height: 18px;
  display: inline-grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: var(--r);
  background: var(--surface);
  color: var(--ink-3);
  cursor: pointer;
  transition: all 140ms ease;
}
.fs-toggle-btn:hover {
  color: var(--ink);
  border-color: var(--ink-3);
}
.fs-toggle-btn svg {
  width: 11px;
  height: 11px;
}
```

And a fullscreen block (put it next to the other `.budget-grid` rules):

```css
/* Fullscreen overlay — the WHOLE grid block (toolbar + legend + admin zone +
   both side-tables + add-transaction form) lifted out of page flow so every
   control stays usable, per the approved scope. z-index 300 is deliberate:
   ABOVE the sticky .nav (z100) so the overlay really covers the page, BELOW
   .modal-backdrop (z500) so a special-GL subform opened from fullscreen still
   paints on top of it. No ancestor has transform/filter/backdrop-filter, so
   position: fixed resolves against the viewport (verified 2026-07-31). */
.budget-grid.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 300;
  overflow: auto;
  padding: 14px 20px 28px;
  background: var(--paper);
}
/* Give the rows back the height the covered page chrome used to eat. The
   normal rule is max-height: calc(100vh - 380px) (global.css .table-wrap). */
.budget-grid.is-fullscreen .table-wrap {
  max-height: calc(100vh - 260px);
}
.budget-grid.is-fullscreen .side-section {
  margin-bottom: 20px;
}
```

Dark mode needs nothing extra — `var(--paper)` / `var(--surface)` / `var(--line)` are already re-defined under `[data-theme='dark']` in [tokens.css:37](../frontend/src/styles/tokens.css#L37).

The `260px` is a first estimate (toolbar + legend + heading). Tune it against the screenshot in §7 — jakkaritw is the visual reviewer.

---

## 5. Invariants that must NOT break

### 5.1 Frozen-column / colSpan math
`identityColSpan` / `fullRowColSpan` / `subtotalLabelColSpan` in [model.ts:416-432](../frontend/src/grid/model.ts#L416) and the inline `--frz1..5` offsets ([GridTable.tsx:719-726](../frontend/src/grid/GridTable.tsx#L719)) assume the exact current cell counts. The button is a **child of an existing `<th>`** — do not add a cell, do not change any `colSpan`, do not touch `model.ts`.

### 5.2 z-index chain in the header
`group-head-row th.frz` is `z-index: 22` on purpose (comment at [global.css:961-971](../frontend/src/styles/global.css#L961)) — it must out-rank the whole col-row `frz-1..5` chain (19,18,17,16,15). Give `.fs-toggle-btn` **no** z-index; it inherits its `<th>`'s stacking context, same as `.col-toggle-btn` does.

### 5.3 Column measurement
`ColumnWidthMeasurer` + the `useLayoutEffect` fit-to-content pass ([GridTable.tsx:588-603](../frontend/src/grid/GridTable.tsx#L588)) must stay mounted and untouched. Do **not** wrap it in anything conditional; do not add `isFullscreen` to that effect's deps — entering fullscreen must not re-measure or clobber a user's dragged widths.

### 5.4 Interaction with compact mode (`columnsCollapsed`)
The two features are independent and must compose: fullscreen + collapsed, fullscreen + expanded, normal + either. The button renders in both column modes (§4.1).

### 5.5 Modal on top
Opening a special-GL subform (`.modal-backdrop`, z500) from inside fullscreen must still work and paint above the overlay. Verify in the Playwright pass.

### 5.6 Cleanup
`document.body.style.overflow` must be restored and the `keydown` listener removed on exit **and** on unmount-while-fullscreen. This is the same class of bug the existing drag code guards against at [GridTable.tsx:632-644](../frontend/src/grid/GridTable.tsx#L632).

---

## 6. Tests (vitest + RTL) — write these, TDD order

Run from `frontend/`: `rtk npx vitest run src/grid`

> Gotcha (already burned this repo): RTL auto-cleanup is a no-op without test globals — `afterEach(cleanup)` in `src/test/setup.ts` is what keeps renders from piling up. Do not "simplify" it away, and use `getAllByTestId(...)[0]` because the button renders once per side-table.

`GridTable.test.tsx` — new `describe('fullscreen toggle')`:
1. renders `enter-fullscreen-btn` once per side-table (2 with COST+SG&A rows), inside the `group-head-row`'s first frozen `<th>`.
2. clicking it calls `onToggleFullscreen` exactly once.
3. `isFullscreen` → renders `exit-fullscreen-btn`, `aria-pressed="true"`, `aria-label` = `'ย่อกลับขนาดปกติ (Esc)'`; and `enter-fullscreen-btn` is gone.
4. button present in BOTH column modes — after clicking `collapse-columns-btn` it is still there (in the `colSpan={2}` `<th>`).
5. structural guard: the group-head first `<th>` still has `colSpan` 4 expanded / 2 collapsed, and the row still has the same cell count as before the feature.
6. omitting both props (existing call style) renders the button and clicking it does not throw.

`BudgetGrid.test.tsx` — new `describe('fullscreen mode')`:
7. default: root has no `is-fullscreen`, `document.body.style.overflow` untouched.
8. click enter → root gets `is-fullscreen`, `document.body.style.overflow === 'hidden'`.
9. click exit → class gone, body overflow restored to its previous value.
10. `fireEvent.keyDown(document.body, { key: 'Escape' })` exits fullscreen.
11. Escape fired from an `<input>` (a column filter or a month cell) does **not** exit.
12. Escape with a `.modal-backdrop` in the DOM does **not** exit.
13. unmount while fullscreen → body overflow restored (assert the style string).
14. interactivity guard: while fullscreen, editing a month cell still fires the existing PUT/commit path (reuse the existing commit test, with fullscreen toggled on first).

---

## 7. Visual verification (project rule — do not Read the screenshot)

Logic first, headless, no image:

```
cd frontend && rtk npx vitest run src/grid
```

Then one Playwright pass against the local dev entry point (`next dev` on **:3000**, API proxied to :8000 — do not spin up your own uvicorn):

1. click `enter-fullscreen-btn`
2. `page.evaluate()` asserts, printed as a compact PASS/FAIL only:
   - `.budget-grid.is-fullscreen` exists
   - its `getBoundingClientRect()` covers the viewport (`top<=0`, `left<=0`, `width>=innerWidth-1`, `height>=innerHeight-1`)
   - `.nav` is visually covered (overlay `z-index` 300 > 100)
   - `.table-wrap` `clientHeight` grew vs the pre-click value
   - `document.body.style.overflow === 'hidden'`
   - a month input is still editable (`focus()` + type + assert value)
3. `page.screenshot(path=…)` into the scratchpad, **do not Read it**, print the path, then **STOP and wait for jakkaritw to confirm** the look (padding, the `260px` table height, button position/size at 18px).
4. Delete the temp script + image after sign-off.

---

## 8. Out of scope / deliberately NOT done

- **Native `requestFullscreen` (F11-style, hides browser chrome)** — rejected: jsdom has no such API (every test would need a mock) and browser/enterprise policy can block it. CSS overlay gives the same usable area minus the browser toolbar, and is fully testable.
- **Per-side maximize** (COST alone / SG&A alone) — the answer was whole-grid.
- **Persisting the state** (localStorage / URL param) — deliberately not persisted, same policy as compact mode.
- **Mobile/tablet-specific layout** inside fullscreen — desktop-only tool.
- **Print stylesheet**, keyboard shortcut other than Esc, and animation on enter/exit — not requested.

---

## 9. Close-out checklist for Kimi

**STATUS 2026-07-31: DONE (Kimi).** Implementation §4 shipped; 14 tests §6 green (`vitest run src/grid` 204/204); `tsc --noEmit` + `oxlint` clean; Playwright §7 PASS (overlay rect = 1280×720 viewport exactly, z 300 > nav 100, table-wrap 340→384px, body locked, month input editable); screenshot visually approved by jakkaritw ("pass"), temp spec + PNG deleted per §7.4; combined gate agent (06+07+08) verdict **Approve** with 0 blockers (2 non-blocking suggestions noted); `.claude/plan.md` synced in the same commit. **Deploy NOT done — needs explicit jakkaritw approval (staging first).**

1. `python tracker/task.py add --id grid-fullscreen-toggle --state doing --ai "..." --agent kimi` before the first edit.
2. Implement §4, tests §6 green, Playwright §7 run, screenshot path handed to jakkaritw, wait for confirm.
3. ONE combined gate agent (06 review + 07 security + 08 test checklists together). 07 here is thin (pure UI, no auth/input/secrets, no PDPA data) but still required before any deploy.
4. Commit (one commit, code + tests + CSS + this plan's tick-off), then
   `python tracker/task.py done --id grid-fullscreen-toggle --ai "<what changed, commit hash, leftovers>"`.
5. Sync [.claude/plan.md](../.claude/plan.md) in the SAME commit.
6. **Deploy only with explicit jakkaritw approval** — staging first, then verify-deploy-landed.
