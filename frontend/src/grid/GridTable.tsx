import {
  Fragment,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type RefObject,
  type TouchEvent as ReactTouchEvent,
} from 'react'
import type { BudgetRow, GlAccount } from '../api/types'
import { MonthCell } from './MonthCell'
import {
  BLANK_COLUMN_FILTERS,
  clampColumnWidth,
  clearStoredColumnWidths,
  DEFAULT_COLUMN_WIDTHS,
  filterRows,
  fitColumnWidth,
  formatSapMonth,
  formatThb,
  freezeOffsets,
  fullRowColSpan,
  glMetaFor,
  groupAndSortBySide,
  groupChipClass,
  hasStoredColumnWidthsOverride,
  HIDDEN_SAP_MONTH_TOOLTIP,
  identityColSpan,
  isDeletableRow,
  isEditableCell,
  loadStoredColumnWidths,
  MONTH_KEYS,
  MONTH_LABELS,
  nowMonthKey,
  persistColumnWidths,
  sapCoverageLabel,
  sectionTotals,
  selectMeasureCandidates,
  subtotalLabelColSpan,
  type ColumnFilters,
  type ColumnWidthKey,
  type ColumnWidths,
  type MonthKey,
  type SapTotals,
} from './model'

export interface RowMessage {
  kind: 'error' | 'saving' | 'saved'
  text: string
}

export interface GridTableProps {
  rows: BudgetRow[]
  glRef: GlAccount[]
  onCommitMonth: (row: BudgetRow, month: MonthKey, value: number) => void
  /** Commits a Remark edit (same `PUT /budget/rows` write path as a month
   * commit — the backend already round-trips `pending.remark`). Optional so
   * presentational test renders can omit it; an absent handler renders the
   * remark read-only. */
  onCommitRemark?: (row: BudgetRow, remark: string) => void
  /** Keyed by `${cost_center}|${gl_account}` — per-row save status (never a
   * single global banner, since the write endpoint is one row per call and
   * one row's failure must never block another, mirroring the backend's
   * batch-shaped-but-independent contract). */
  rowMessages?: Record<string, RowMessage>
  /** Opens the A9 special-GL detail subform (or Trip Manager, for
   * `glGroup === 'Travelling Expense'`) for one row — only offered when the
   * row is in the caller's Fill scope (`row.editable`); a See-only special
   * row just shows the static tooltip (viewing the detail breakdown for
   * read-only users is out of this task's scope, flagged as a fast-follow). */
  onOpenSpecial?: (row: BudgetRow, glGroup: string) => void
  /** Trailing "ลบ" column — deletes one manually-added Pending row (see
   * `isDeletableRow` for the eligibility gate). Optional so presentational
   * test renders can omit it; the delete button only renders when both this
   * handler is provided AND the row passes `isDeletableRow`. */
  onDeleteRow?: (row: BudgetRow) => void
  /** Fullscreen presentation state — owned by BudgetGrid (the overlay must
   * also contain the toolbar/legend/Submit, which live outside this
   * component, so the state cannot stay local here like columnsCollapsed). */
  isFullscreen?: boolean
  /** Flip fullscreen. Undefined in isolated/unit renders → button is a no-op. */
  onToggleFullscreen?: () => void
}

const SIDE_LABEL: Record<'COST' | 'SGA', string> = {
  COST: 'ฝั่งผลิต / ต้นทุน (5xxx)',
  SGA: 'ฝั่งบริหาร / ขาย · SG&A (6xxx)',
}

const SPECIAL_GL_TOOLTIP = 'แก้ไขผ่านฟอร์มย่อย'
const COLLAPSE_COLUMNS_LABEL = 'ซ่อนคอลัมน์ GL Group / Remark / Status'
const EXPAND_COLUMNS_LABEL = 'แสดงคอลัมน์ GL Group / Remark / Status'
const ENTER_FULLSCREEN_LABEL = 'ขยายตารางเต็มหน้าจอ'
const EXIT_FULLSCREEN_LABEL = 'ย่อกลับขนาดปกติ (Esc)'

function rowKey(cc: string, gl: string): string {
  return `${cc}|${gl}`
}

/** Compact-mode toggle icons (UI-parity with the existing Reset-columns
 * button, mockup 0002.3): quiet double-chevron, stroke-only, no fill. */
function ChevronsLeftIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="11 17 6 12 11 7" />
      <polyline points="18 17 13 12 18 7" />
    </svg>
  )
}

function ChevronsRightIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 17 11 12 6 7" />
      <polyline points="13 17 18 12 13 7" />
    </svg>
  )
}

/** Fullscreen toggle icons (⤢/⤡) — same stroke-only, fill-none language as
 * the chevrons above and the Reset-columns button. */
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

/** Reads the hidden measurement pass (see `<ColumnWidthMeasurer>` below) and
 * derives fit-to-content widths: max natural content width per identity
 * column (header label candidates included), converted via `fitColumnWidth`
 * (padding allowance + clamp). Pure DOM read, no side effects — safe to call
 * both from the auto-fit layout effect and synchronously from the
 * Reset-columns click handler. Falls back to `DEFAULT_COLUMN_WIDTHS` only
 * when the container ref isn't mounted yet (defensive, not expected in
 * practice since the measurer renders unconditionally alongside the grid). */
function measureColumnWidths(container: HTMLElement | null): ColumnWidths {
  if (!container) return DEFAULT_COLUMN_WIDTHS
  const maxWidth = (key: ColumnWidthKey): number => {
    const nodes = container.querySelectorAll<HTMLElement>(`[data-measure-col="${key}"]`)
    let max = 0
    nodes.forEach((node) => {
      max = Math.max(max, node.getBoundingClientRect().width)
    })
    return max
  }
  return {
    cc: fitColumnWidth(maxWidth('cc')),
    gl: fitColumnWidth(maxWidth('gl')),
    glGroup: fitColumnWidth(maxWidth('glGroup')),
    remark: fitColumnWidth(maxWidth('remark')),
  }
}

/** Reads a numeric CSS length off a live computed style (margin/gap) so the
 * reserve calc below never drifts out of sync with global.css the way a
 * hand-copied constant would — a later CSS tweak is picked up automatically.
 * Missing element / unset property folds to 0 rather than NaN. */
function computedLength(
  el: Element | null,
  property: 'marginBottom' | 'marginTop' | 'rowGap' | 'paddingBottom',
): number {
  if (!el) return 0
  const parsed = parseFloat(getComputedStyle(el)[property])
  return Number.isFinite(parsed) ? parsed : 0
}

/**
 * Computes the vertical space to reserve OUTSIDE the LAST side-table's
 * `.table-wrap` so its scrolled bottom edge lands just above the approval
 * bar, replacing the flat `calc(100vh - 380px)` / `calc(100vh - 260px)`
 * guesses in global.css (the 260px comment there literally called it "a
 * first estimate ... tune against the verification screenshot" — this is
 * that tuning, done live from the real DOM instead of by hand).
 *
 * Measured, not hardcoded: the sticky `.nav`'s real height (0 in
 * fullscreen — `.budget-grid.is-fullscreen` is `position:fixed;inset:0`,
 * painting OVER nav at the same top edge, so nav consumes none of the
 * overlay's OWN vertical budget there), THIS section's own
 * `.side-heading-row` height (it sits directly above the table-wrap being
 * sized), the approval bar's height, and the real CSS margins/gaps between
 * them (`.side-heading-row`'s margin-bottom, its parent `.side-section`'s
 * own margin-bottom — the space down to the next section or, for the last
 * one, to the approval bar — `.approval-bar`'s margin-top, `.budget-grid`'s
 * flex `gap`) — read live via `computedLength` above rather than copied as
 * numbers.
 *
 * Measurement lives HERE, inside GridTable (`document.querySelector` for
 * the nav/approval-bar/`.budget-grid` — all page-level singletons this
 * component doesn't own), rather than as a reserve prop threaded down from
 * BudgetGrid: GridTable already computes "which side is last" internally
 * (`sidesWithData`), and it owns `.side-heading-row`; splitting the
 * measurement across both components would need BudgetGrid to know about a
 * GridTable-internal element for no real benefit.
 *
 * Returns `undefined` — "measurement unavailable" — whenever the approval
 * bar isn't in the DOM yet (isolated GridTable renders, or no ฝ่าย
 * selected), or the computed reserve/available height comes out to 0 or
 * less; callers must fall back to the existing CSS `max-height` cap rather
 * than apply a meaningless number.
 */
/** `.approval-bar` (the real, stable class ApprovalActionBar.tsx renders on
 * every branch) is tried before `[data-testid="approval-bar"]` — a testid is
 * a test hook, not a contract; if one gets renamed this measurement must not
 * silently fall back to the CSS cap. The testid stays only as a fallback. */
function queryApprovalBar(): HTMLElement | null {
  return (
    document.querySelector<HTMLElement>('.approval-bar') ??
    document.querySelector<HTMLElement>('[data-testid="approval-bar"]')
  )
}

function measureLastTableMaxHeight(headingEl: HTMLElement | null, isFullscreen: boolean): number | undefined {
  if (typeof window === 'undefined') return undefined
  const approvalEl = queryApprovalBar()
  if (!approvalEl) return undefined

  const navEl = document.querySelector<HTMLElement>('.nav')
  const navHeight = isFullscreen ? 0 : (navEl?.getBoundingClientRect().height ?? 0)
  const headingHeight = headingEl?.getBoundingClientRect().height ?? 0
  const headingMargin = computedLength(headingEl, 'marginBottom')
  // `.side-heading-row`'s own parent is the `.side-section` wrapper — ITS
  // margin-bottom (28px normal / 20px fullscreen, global.css) is the space
  // between this section and whatever follows (the next side-section, or —
  // for the LAST one — `.budget-grid`'s flex gap down to the approval bar).
  // Missing this term left the measured reserve ~28px short (verified
  // empirically: table-wrap grew that far past where the approval bar
  // actually starts).
  const sideSectionMargin = computedLength(headingEl?.parentElement ?? null, 'marginBottom')
  const approvalHeight = approvalEl.getBoundingClientRect().height
  const approvalMargin = computedLength(approvalEl, 'marginTop')
  const budgetGridEl = document.querySelector('.budget-grid')
  const budgetGridGap = computedLength(budgetGridEl, 'rowGap')
  // `.budget-grid` reserves space AFTER its last child (the approval bar)
  // too: a `margin-bottom` in normal mode (60px, global.css:471) that swaps
  // to `padding-bottom` in fullscreen mode (28px, global.css:488 — the
  // overlay resets margin to 0). Missing this term left the reserve short
  // by exactly that amount, so the last `.table-wrap` could stretch ~60px
  // (normal) / ~28px (fullscreen) past where the approval bar's own box
  // already ends, tucking its heading under the sticky nav once scrolled.
  const budgetGridBottomSpacing = isFullscreen
    ? computedLength(budgetGridEl, 'paddingBottom')
    : computedLength(budgetGridEl, 'marginBottom')

  const reserved =
    navHeight +
    headingHeight +
    headingMargin +
    sideSectionMargin +
    approvalHeight +
    approvalMargin +
    budgetGridGap +
    budgetGridBottomSpacing
  if (reserved <= 0) return undefined

  const available = window.innerHeight - reserved
  return available > 0 ? available : undefined
}

/** Hidden (visually, not `display:none` — that would report 0 widths in a
 * real browser too) DOM measurement pass for the 4 identity columns
 * (UI-parity point 8d — fit-to-content default). Renders each header label +
 * bounded candidate list with the SAME classNames as the real cells
 * (`idx-cell` / `gl-code-text` / the GL-group chip) so font/weight match;
 * `getBoundingClientRect().width` per node then reflects real content
 * width — `measureColumnWidths` above takes the max per column. Absolutely
 * positioned off-screen + `visibility:hidden` so it never paints or affects
 * layout/scroll of the real grid, while still participating in real layout
 * (unlike `display:none`, which every browser reports as 0×0). */
function ColumnWidthMeasurer({
  containerRef,
  candidates,
}: {
  containerRef: RefObject<HTMLDivElement | null>
  candidates: ReturnType<typeof selectMeasureCandidates>
}) {
  const headerLabelStyle: CSSProperties = {
    display: 'inline-block',
    whiteSpace: 'nowrap',
    fontSize: 10.5,
    fontWeight: 600,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
  }
  return (
    <div
      ref={containerRef}
      aria-hidden="true"
      data-testid="col-width-measurer"
      className="data-table"
      style={{ position: 'absolute', top: -9999, left: -9999, visibility: 'hidden', width: 'auto', minWidth: 0 }}
    >
      <span data-measure-col="cc" style={headerLabelStyle}>Cost Center</span>
      {candidates.cc.map((v) => (
        <span key={`cc-${v}`} className="idx-cell" data-measure-col="cc" style={{ display: 'inline-block' }}>
          {v}
        </span>
      ))}
      <span data-measure-col="gl" style={headerLabelStyle}>GL Code</span>
      {candidates.gl.map((v) => (
        <span key={`gl-${v}`} className="gl-code-text" data-measure-col="gl" style={{ display: 'inline-block' }}>
          {v}
        </span>
      ))}
      {/* GL names share the gl column — measured with the real .gl-name font so
          the column fits max(widest code, widest name). */}
      {candidates.glName.map((v) => (
        <span key={`glName-${v}`} className="gl-name" data-measure-col="gl" style={{ display: 'inline-block' }}>
          {v}
        </span>
      ))}
      <span data-measure-col="glGroup" style={headerLabelStyle}>GL Group</span>
      {candidates.glGroup.map((g) => {
        const chipClass = groupChipClass(g)
        return (
          <span key={`glGroup-${g}`} data-measure-col="glGroup" style={{ display: 'inline-block' }}>
            {chipClass ? <span className={`gl-chip special-gl-group ${chipClass}`}>{g}</span> : g}
          </span>
        )
      })}
      <span data-measure-col="remark" style={headerLabelStyle}>Remark</span>
      {/* Remarks are measured with the real .remark-text font — both the
          read-only text and the editable input share that font size. */}
      {candidates.remark.map((v) => (
        <span key={`remark-${v}`} className="remark-text" data-measure-col="remark" style={{ display: 'inline-block' }}>
          {v}
        </span>
      ))}
    </div>
  )
}

function MonthCells({
  values,
  layerTestId,
  variant,
  cc,
  gl,
  nowMonth,
  totalYearTitle,
}: {
  /** SAP months may be `null` (a month hidden by ADR-0026); Approved months
   * never are, and `number` is assignable here, so both layers share this
   * one renderer. */
  values: { [K in MonthKey]: number | null } & { total_year: number }
  layerTestId: 'sap-value' | 'board-value'
  /** Data-layer pill color (mockup 0002.3budget-export.html) — SAP = green,
   * Approved (board, read-only) = blue. A zero value always mutes the pill
   * regardless of layer. */
  variant: 'sap' | 'approved-ro'
  cc: string
  gl: string
  /** Current-month key (UI-parity point 8a) — matching cell gets `.now` so
   * the whole column reads as "today" alongside the header highlight. */
  nowMonth: MonthKey
  /** Coverage note for the year-total cell — set on the SAP layer only, and
   * only while some months are hidden (ADR-0026), so the total is never read
   * as a full year. */
  totalYearTitle?: string
}) {
  return (
    <>
      {/* Year-total column sits BEFORE Jan (user requirement 2026-07-30):
          sum of m01..m12 for this row+layer, read straight off the stored
          total_year. */}
      <td className="month-cell total-year-cell" data-testid={`${layerTestId}-${cc}-${gl}-year`}>
        <span
          className={`month-value ${variant}${values.total_year === 0 ? ' zero' : ''}`}
          title={totalYearTitle}
        >
          {formatThb(values.total_year)}
        </span>
      </td>
      {MONTH_KEYS.map((m) => {
        const value = values[m]
        const hidden = value === null
        const className = `month-value ${variant}${hidden ? ' month-hidden' : value === 0 ? ' zero' : ''}`
        const tdClassName = `month-cell${m === nowMonth ? ' now' : ''}`
        return (
          <td key={m} className={tdClassName} data-testid={`${layerTestId}-${cc}-${gl}-${m}`}>
            <span className={className} title={hidden ? HIDDEN_SAP_MONTH_TOOLTIP : undefined}>
              {formatSapMonth(value)}
            </span>
          </td>
        )
      })}
    </>
  )
}

function PendingCells({
  row,
  editable,
  disabledReason,
  onCommitMonth,
  nowMonth,
}: {
  row: BudgetRow
  editable: boolean
  disabledReason?: string
  onCommitMonth: GridTableProps['onCommitMonth']
  /** Current-month key (UI-parity point 8a). */
  nowMonth: MonthKey
}) {
  const { cost_center: cc, gl_account: gl } = row
  return (
    <>
      {/* Year-total column (before Jan) — read-only even when the row is
          editable; it is the derived sum, not an input. */}
      <td className="month-cell total-year-cell" data-testid={`pending-cell-${cc}-${gl}-year`}>
        <span className={`month-value pending-readonly${row.pending.total_year === 0 ? ' zero' : ''}`}>
          {formatThb(row.pending.total_year)}
        </span>
      </td>
      {MONTH_KEYS.map((m) => (
        <td
          key={m}
          className={`month-cell${m === nowMonth ? ' now' : ''}`}
          data-testid={`pending-cell-${cc}-${gl}-${m}`}
        >
          <MonthCell
            value={row.pending[m]}
            editable={editable}
            label={`Pending ${m} ${cc} ${gl}`}
            disabledReason={disabledReason}
            testId={editable ? `pending-input-${cc}-${gl}-${m}` : undefined}
            onCommit={(value) => onCommitMonth(row, m, value)}
          />
        </td>
      ))}
    </>
  )
}

/** The Remark cell (mockup 0002.3budget-export.html lines 2246-2249) — one
 * shared cell per txn block (rowSpan=3 on the SAP row, exactly like the
 * mockup's `<td rowspan="3" class="shared">`; safe here because the remark
 * column is NOT sticky/frozen, unlike the 3 identity columns which use the
 * colSpan-merged-cell trick instead). Editable for the same rows whose
 * month cells are editable: the backend's `/budget/rows` rejects special
 * GLs outright (`SpecialGlDirectEditError`), so a remark input there would
 * be a write-trap. Local draft + blur-commit mirrors `MonthCell`. */
function RemarkCell({
  row,
  editable,
  onCommitRemark,
}: {
  row: BudgetRow
  editable: boolean
  onCommitRemark?: GridTableProps['onCommitRemark']
}) {
  const { cost_center: cc, gl_account: gl } = row
  const remark = row.pending.remark ?? ''
  const [draft, setDraft] = useState(remark)

  // Re-sync from the SERVER-derived remark (post-save merge / 409 refetch),
  // same reasoning as MonthCell's draft sync.
  useEffect(() => {
    setDraft(remark)
  }, [remark])

  if (!editable || !onCommitRemark) {
    return (
      <span className="remark-text" data-testid={`remark-text-${cc}-${gl}`}>
        {remark || '—'}
      </span>
    )
  }

  return (
    <input
      type="text"
      className="remark-input"
      maxLength={500}
      aria-label={`Remark ${cc} ${gl}`}
      data-testid={`remark-input-${cc}-${gl}`}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        const next = draft.trim()
        if (next !== remark) onCommitRemark(row, next)
      }}
    />
  )
}

function TxnBlock({
  row,
  glRef,
  onCommitMonth,
  onCommitRemark,
  message,
  onOpenSpecial,
  onDeleteRow,
  nowMonth,
  columnsCollapsed,
  sapTotalTitle,
}: {
  row: BudgetRow
  glRef: GlAccount[]
  onCommitMonth: GridTableProps['onCommitMonth']
  onCommitRemark?: GridTableProps['onCommitRemark']
  message?: RowMessage
  onOpenSpecial?: GridTableProps['onOpenSpecial']
  onDeleteRow?: GridTableProps['onDeleteRow']
  /** Current-month key (UI-parity point 8a). */
  nowMonth: MonthKey
  /** Compact mode ("ซ่อนคอลัมน์" toggle) — hides GL Group/Remark/Status,
   * leaving Cost Center + GL Code as the frozen identity band. */
  columnsCollapsed: boolean
  /** ADR-0026 coverage note for the SAP year-total cell (undefined when the
   * whole year is shown). */
  sapTotalTitle?: string
}) {
  const meta = glMetaFor(row.gl_account, glRef)
  const editable = isEditableCell(row.editable, meta.is_special, meta.in_master)
  const deletable = isDeletableRow(row, meta)
  // Chip is gated on the GROUP NAME (one of the 6 special-GL groups), never
  // on meta.is_special — a fixture/live GL can be is_special:false while
  // still belonging to a chipped group, which would leave some rows in the
  // same group un-chipped. See model.ts groupChipClass for the rationale.
  const chipClass = groupChipClass(meta.gl_group)
  const cc = row.cost_center
  const gl = row.gl_account
  // Same condition the EXPANDED open-subform button already uses (in the
  // Pending status cell) — in compact mode that cell doesn't render at all,
  // so the button moves into the GL cell instead. Never both at once.
  const canOpenSpecial = meta.is_special && row.editable && onOpenSpecial

  return (
    <tbody className="txn-block" data-testid={`txn-${cc}-${gl}`}>
      <tr className="txn-row first" data-status="sap">
        <td className="idx-cell frz frz-1">{cc}</td>
        <td className={`gl-cell frz frz-2${columnsCollapsed ? ' frz-edge' : ''}`}>
          <span className="gl-code-text">{gl}</span>
          <div className="gl-name">{meta.gl_name ?? '—'}</div>
          {columnsCollapsed && canOpenSpecial && (
            <button
              type="button"
              className="special-open-btn compact"
              title={SPECIAL_GL_TOOLTIP}
              aria-label={SPECIAL_GL_TOOLTIP}
              data-testid={`open-subform-${cc}-${gl}`}
              onClick={() => onOpenSpecial(row, meta.gl_group)}
            >
              ↗
            </button>
          )}
        </td>
        {!columnsCollapsed && (
          <>
            <td className="gl-group-cell frz frz-3">
              {chipClass ? <span className={`gl-chip special-gl-group ${chipClass}`}>{meta.gl_group}</span> : meta.gl_group}
            </td>
            {/* Remark = the 4th frozen identity column (same part as CC/GL/GL
               Group): a plain per-row frz cell, NOT a rowSpan like the mockup —
               sticky + rowSpan is the combination the colSpan-merged cells below
               exist to avoid. */}
            <td className="remark-cell frz frz-4">
              <RemarkCell row={row} editable={editable} onCommitRemark={onCommitRemark} />
            </td>
            <td className="status-cell sap frz frz-5">
              <span className="status-cell-content">SAP · ใช้จริง</span>
            </td>
          </>
        )}
        <MonthCells
          values={row.sap}
          layerTestId="sap-value"
          variant="sap"
          cc={cc}
          gl={gl}
          nowMonth={nowMonth}
          totalYearTitle={sapTotalTitle}
        />
        {/* Trailing "ลบ" column — one shared cell per txn block (rowSpan=3,
           same pattern as the mockup's rowspan=3 action-cell) since the
           delete op targets the whole row, not one layer. Rendered ONLY on
           this first (SAP) <tr> — rows 2/3 add no <td> here, the rowSpan
           already covers them. */}
        <td rowSpan={3} className="action-cell">
          {deletable && onDeleteRow && (
            <button
              type="button"
              className="action-btn"
              title="ลบรายการนี้"
              data-testid={`delete-row-${cc}-${gl}`}
              onClick={() => onDeleteRow(row)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
          )}
        </td>
      </tr>
      <tr className="txn-row" data-status="approved">
        <td colSpan={identityColSpan(columnsCollapsed)} className={`frz frz-1${columnsCollapsed ? ' frz-edge' : ''}`} />
        {!columnsCollapsed && (
          <td className="status-cell approved frz frz-5">
            <span className="status-cell-content">Approved · งบ</span>
          </td>
        )}
        <MonthCells values={row.board} layerTestId="board-value" variant="approved-ro" cc={cc} gl={gl} nowMonth={nowMonth} />
      </tr>
      <tr className="txn-row last" data-status="pending">
        <td colSpan={identityColSpan(columnsCollapsed)} className={`frz frz-1${columnsCollapsed ? ' frz-edge' : ''}`} />
        {!columnsCollapsed && (
          <td className="status-cell pending frz frz-5">
            <span className="status-cell-content">
              Pending · รออนุมัติ
              {canOpenSpecial && (
                <button
                  type="button"
                  className="special-open-btn"
                  title={SPECIAL_GL_TOOLTIP}
                  data-testid={`open-subform-${cc}-${gl}`}
                  onClick={() => onOpenSpecial(row, meta.gl_group)}
                >
                  {SPECIAL_GL_TOOLTIP} ↗
                </button>
              )}
              {meta.is_special && !canOpenSpecial && (
                <span className="special-hint"> {SPECIAL_GL_TOOLTIP}</span>
              )}
            </span>
          </td>
        )}
        <PendingCells
          row={row}
          editable={editable}
          disabledReason={meta.is_special ? SPECIAL_GL_TOOLTIP : undefined}
          onCommitMonth={onCommitMonth}
          nowMonth={nowMonth}
        />
      </tr>
      {message && (
        <tr className="txn-row-message">
          <td colSpan={fullRowColSpan(columnsCollapsed)} className={`row-message row-message-${message.kind}`}>
            {message.text}
          </td>
        </tr>
      )}
    </tbody>
  )
}

function SubtotalRow({
  label,
  totals,
  layer,
  columnsCollapsed,
}: {
  label: string
  totals: ReturnType<typeof sectionTotals>
  /** Which layer this subtotal line displays. Group subtotals stay
   * pending-only; the side grand total renders one row per layer. */
  layer: 'sap' | 'board' | 'pending'
  columnsCollapsed: boolean
}) {
  const amounts: SapTotals = totals[layer]
  return (
    <tbody>
      <tr className="subtotal-row" data-layer={layer}>
        {/* colSpan covers the frozen identity band (+ Status when expanded) —
           frozen at left:0 (not left-unfrozen) so the label never scrolls
           out of view under the horizontally-scrolled month columns
           (verified point 1). */}
        <td colSpan={subtotalLabelColSpan(columnsCollapsed)} className="frz frz-1 frz-edge">
          {label}
        </td>
        <td className="month-cell total-year-cell">
          {formatThb(amounts.total_year)}
        </td>
        {MONTH_KEYS.map((m) => (
          <td key={m} className={`month-cell${amounts[m] === null ? ' month-hidden' : ''}`}>
            {formatSapMonth(amounts[m])}
          </td>
        ))}
        <td className="action-cell" />
      </tr>
    </tbody>
  )
}

/** Renders the main budget grid: two structurally-separate sections (COST
 * 5xxx / SG&A 6xxx — NEVER-CUT, their totals never combine), each grouped
 * by gl_group with a subtotal row, 3 layers per transaction. Pure
 * presentational component — all state/API calls live in `BudgetGrid`. */
export function GridTable({
  rows,
  glRef,
  onCommitMonth,
  onCommitRemark,
  rowMessages = {},
  onOpenSpecial,
  onDeleteRow,
  isFullscreen = false,
  onToggleFullscreen,
}: GridTableProps) {
  // Shared per-column filter state (UI-parity point 8b) — held LOCALLY here
  // (not lifted to BudgetGrid) since both side-tables live inside this one
  // component; one filter string per column applies to both tables at once,
  // so typing in either table's input keeps them in sync by construction.
  const [colFilters, setColFilters] = useState<ColumnFilters>(BLANK_COLUMN_FILTERS)

  // Compact mode ("ซ่อนคอลัมน์" toggle, jakkaritw-approved 2026-07-21) — hides
  // GL Group/Remark/Status in BOTH side-tables at once (single shared state,
  // same reasoning as colFilters/colWidths above). Plain useState, always
  // expanded on load — deliberately NOT persisted (no localStorage), per the
  // approved policy decision.
  const [columnsCollapsed, setColumnsCollapsed] = useState(false)

  // Identity-column widths (UI-parity point 8c) — held LOCALLY, same
  // reasoning as colFilters: both side-tables live inside this one
  // component and must share ONE set of widths so they stay pixel-aligned.
  // Initial value is read from localStorage once (lazy initializer), never
  // re-read after mount.
  const [colWidths, setColWidths] = useState<ColumnWidths>(() => loadStoredColumnWidths())

  // Fit-to-content default (UI-parity point 8d) — `hasOverrideRef` decides
  // whether the measurement effect below is even allowed to touch
  // `colWidths`: a saved localStorage width (checked once at mount, same
  // timing as the lazy initializer above) or a manual drag THIS session both
  // set it permanently true, so the user's explicit choice always wins over
  // re-measuring. Reset-columns clears it back to false.
  const hasOverrideRef = useRef<boolean>(hasStoredColumnWidthsOverride())
  // Hidden measurement-pass container (see `<ColumnWidthMeasurer>`) — a DOM
  // read target for `measureColumnWidths`, shared by the auto-fit effect AND
  // the Reset-columns click handler.
  const measureContainerRef = useRef<HTMLDivElement | null>(null)
  // Bounded candidate strings per column, recomputed only when the
  // underlying DATA identity changes (`rows`/`glRef`) — never depends on
  // `colWidths` itself, which is what keeps the measurement effect below
  // from ever re-triggering itself (no loop).
  const measureCandidates = useMemo(() => selectMeasureCandidates(rows, glRef), [rows, glRef])

  // Which sides exist AT ALL (ignoring the column filters) — decides both
  // whether a side renders its table+header (below, after the empty-state
  // return) AND which one is "last" (for the measured max-height effect
  // right below) — hoisted into a memo so BOTH consumers share one
  // computation and, critically, so "last side" is known BEFORE the
  // rows.length===0 early return further down (React hooks must run
  // unconditionally on every render, so this can't wait until after it).
  const sidesWithData = useMemo(() => groupAndSortBySide(rows, glRef), [rows, glRef])
  // The side actually rendered LAST (COST/SGA render in that fixed order,
  // but either can be absent when a side has no rows) — only ITS
  // `.table-wrap` gets the measured stretch; the earlier one keeps the
  // content-driven CSS-cap height it always had.
  const lastRenderedSide = useMemo(
    () => (['COST', 'SGA'] as const).filter((side) => sidesWithData[side].length > 0).pop() ?? null,
    [sidesWithData],
  )

  // Measured max-height for the LAST side's `.table-wrap` (see
  // `measureLastTableMaxHeight` above) — `undefined` means "fall back to
  // the CSS cap", never a stretched/collapsed height.
  const [lastTableMaxHeight, setLastTableMaxHeight] = useState<number | undefined>(undefined)
  // One ref per side (not just "the last one") so whichever side turns out
  // to be last always has an attached `.side-heading-row` node to measure —
  // simpler than conditionally attaching/detaching a single ref as
  // `lastRenderedSide` changes across renders.
  const headingRowRefs = useRef<Partial<Record<'COST' | 'SGA', HTMLDivElement | null>>>({})
  // Which approval-bar DOM node the ResizeObserver below is CURRENTLY
  // attached to — lets a MutationObserver-triggered recompute tell "same
  // element, just resized" (already covered by the RO) apart from "a
  // different element replaced/removed it" (re-observe needed) without
  // tearing the RO down on every single recompute call.
  const observedApprovalElRef = useRef<Element | null>(null)
  const approvalResizeObserverRef = useRef<ResizeObserver | null>(null)

  // useLayoutEffect (not useEffect) — matching the column-fit effect
  // further below: runs synchronously after the DOM updates but BEFORE the
  // browser paints, so the first paint and every fullscreen toggle already
  // show the measured max-height instead of flashing the CSS-cap height
  // for one frame.
  useLayoutEffect(() => {
    // SSR/static-export guard (`output: export`) — window/document are
    // only ever touched from inside this effect (post-render, client-only),
    // never during render itself; this early return is a cheap extra
    // safety net on top of that. The app is client-only (`dynamic(ssr:
    // false)`), so this component tree never actually server-renders —
    // useLayoutEffect's SSR warning path never applies here.
    if (typeof window === 'undefined') return
    if (!lastRenderedSide) {
      setLastTableMaxHeight(undefined)
      return
    }

    function syncApprovalResizeObserver() {
      const approvalEl = queryApprovalBar()
      if (approvalEl === observedApprovalElRef.current) return
      approvalResizeObserverRef.current?.disconnect()
      approvalResizeObserverRef.current = null
      observedApprovalElRef.current = approvalEl
      // Guard for jsdom/older browsers without ResizeObserver — degrades to
      // "no live resize tracking", the other triggers (resize/rows/
      // fullscreen/mutation) still recompute.
      if (approvalEl && typeof ResizeObserver !== 'undefined') {
        const ro = new ResizeObserver(recompute)
        ro.observe(approvalEl)
        approvalResizeObserverRef.current = ro
      }
    }

    function recompute() {
      const headingEl = headingRowRefs.current[lastRenderedSide as 'COST' | 'SGA'] ?? null
      setLastTableMaxHeight(measureLastTableMaxHeight(headingEl, isFullscreen))
      syncApprovalResizeObserver()
    }

    recompute()
    window.addEventListener('resize', recompute)

    // The approval bar mounts/unmounts from OUTSIDE this component
    // (BudgetGrid's `{department && <ApprovalActionBar .../>}` guard) and
    // can also grow (the reject panel opening, an error hint wrapping) —
    // resize is covered by the ResizeObserver above; appear/disappear is
    // covered here by a MutationObserver on the shared `.budget-grid`
    // ancestor (both this table and the approval bar live inside it), the
    // honest tool for "did a node get added/removed" the same way
    // ResizeObserver is the honest tool for "did a node change size".
    // `subtree: false` (the default — no `subtree` key at all) is
    // deliberate: the approval bar is a DIRECT child of `.budget-grid`, so
    // watching only direct-child add/remove already catches mount/unmount.
    // `subtree: true` was over-broad — it also fired `recompute` (3
    // `getBoundingClientRect` + 4 `getComputedStyle` reads, a forced
    // reflow) on every mutation ANYWHERE inside the grid, including typing
    // in a column filter or a per-row save message appearing.
    const budgetGridEl = document.querySelector('.budget-grid')
    let mutationObserver: MutationObserver | undefined
    if (budgetGridEl && typeof MutationObserver !== 'undefined') {
      mutationObserver = new MutationObserver(recompute)
      mutationObserver.observe(budgetGridEl, { childList: true })
    }

    return () => {
      window.removeEventListener('resize', recompute)
      mutationObserver?.disconnect()
      approvalResizeObserverRef.current?.disconnect()
      approvalResizeObserverRef.current = null
      observedApprovalElRef.current = null
    }
    // Recompute triggers (per spec): window resize (listener above),
    // fullscreen toggle (isFullscreen), rows changing (rows — also covers
    // most department/ฝ่าย switches, since those refetch the grid), and
    // "which side is last" changing. Approval-bar appear/resize are their
    // own observers, not deps, by design (see comments above).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, isFullscreen, lastRenderedSide])

  useLayoutEffect(() => {
    // Guard: no rows means nothing rendered to measure (this component
    // itself short-circuits to the plain empty state below when
    // `rows.length === 0`) — keep whatever `colWidths` already holds rather
    // than collapsing every column to the padding-only minimum.
    if (rows.length === 0) return
    // A user/localStorage override always wins — never clobber an explicit
    // choice with a re-measured fit just because the data changed.
    if (hasOverrideRef.current) return
    setColWidths(measureColumnWidths(measureContainerRef.current))
    // Deliberately NOT depending on colWidths/hasOverrideRef — this effect
    // reacts to DATA changes only, before paint (useLayoutEffect), so the
    // first real paint already shows the fitted widths, no flash of the
    // pre-measurement placeholder.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, glRef])

  // Which handle is CURRENTLY being dragged, purely for the accent-hairline
  // visual state (mockup `.col-resize.is-dragging::after`) — `null` when no
  // drag is active. Separate from `dragStateRef` below (that ref drives the
  // actual math and must never trigger a re-render on every drag frame).
  const [draggingKey, setDraggingKey] = useState<ColumnWidthKey | null>(null)

  // In-flight drag bookkeeping. `dragStateRef` is the single source of truth
  // for "is a drag active, and which column" — read inside the window-level
  // listeners via closure-free ref access (never stale). `dragListenersRef`
  // holds the exact function references passed to addEventListener so they
  // can be removed with a matching removeEventListener call, both on a
  // normal mouseup/touchend AND on unmount (a component can unmount mid-drag
  // — e.g. navigating away — and must never leave a window-level listener
  // running against an unmounted component).
  const dragStateRef = useRef<{ key: ColumnWidthKey; startX: number; startWidth: number } | null>(null)
  const dragListenersRef = useRef<{ move: (e: MouseEvent | TouchEvent) => void; up: () => void } | null>(null)

  function detachDragListeners() {
    const listeners = dragListenersRef.current
    if (!listeners) return
    window.removeEventListener('mousemove', listeners.move)
    window.removeEventListener('mouseup', listeners.up)
    window.removeEventListener('touchmove', listeners.move)
    window.removeEventListener('touchend', listeners.up)
    dragListenersRef.current = null
  }

  useEffect(() => {
    // Unmount safety net — if a drag is in flight when this component
    // unmounts, clear the body-wide dragging cursor/no-select state and
    // detach the window listeners so nothing lingers against a dead
    // component.
    return () => {
      if (dragStateRef.current) {
        document.body.classList.remove('col-dragging')
      }
      detachDragListeners()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function startColumnResize(key: ColumnWidthKey) {
    return (e: ReactMouseEvent | ReactTouchEvent) => {
      e.preventDefault()
      e.stopPropagation() // never let the drag reach/blur the 8b filter input sharing this th
      // A manual resize is an explicit user choice — from now on the
      // fit-to-content effect must never overwrite it on a later data change.
      hasOverrideRef.current = true
      const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
      dragStateRef.current = { key, startX: clientX, startWidth: colWidths[key] }
      document.body.classList.add('col-dragging')
      setDraggingKey(key)

      const onMove = (ev: MouseEvent | TouchEvent) => {
        const drag = dragStateRef.current
        if (!drag) return
        const x = 'touches' in ev ? ev.touches[0].clientX : ev.clientX
        const next = clampColumnWidth(drag.startWidth + (x - drag.startX))
        setColWidths((prev) => ({ ...prev, [drag.key]: next }))
      }
      const onUp = () => {
        if (!dragStateRef.current) return
        dragStateRef.current = null
        document.body.classList.remove('col-dragging')
        setDraggingKey(null)
        detachDragListeners()
        // Persist the FINAL width only (not every intermediate frame).
        setColWidths((prev) => {
          persistColumnWidths(prev)
          return prev
        })
      }
      dragListenersRef.current = { move: onMove, up: onUp }
      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
      window.addEventListener('touchmove', onMove, { passive: false })
      window.addEventListener('touchend', onUp)
    }
  }

  function handleResetColumns() {
    // "Reset" means "go back to fit-to-content", not "go back to a fixed
    // 130/150/150" — clear BOTH the in-session override flag and the
    // persisted localStorage entry so a later data change keeps auto-fitting
    // too, then re-measure immediately from the (already-mounted) hidden
    // measurement pass so the click has no visible delay.
    hasOverrideRef.current = false
    clearStoredColumnWidths()
    setColWidths(measureColumnWidths(measureContainerRef.current))
  }

  // Unfiltered emptiness is unrelated to the filter feature (no data at all
  // for this scope/year) — keep the original plain empty state, no headers,
  // nothing to filter.
  if (rows.length === 0) {
    return <div className="grid-empty">ไม่มีรายการที่ตรงกับตัวกรองนี้</div>
  }

  // Filter BEFORE grouping so both side-tables and their subtotals reflect
  // only the matching rows (sectionTotals runs on the filtered set).
  const filteredRows = filterRows(rows, glRef, colFilters)
  const sections = groupAndSortBySide(filteredRows, glRef)
  // sidesWithData/lastRenderedSide are computed above (useMemo, before this
  // early return) — reused here unchanged: which sides exist AT ALL
  // (ignoring the filter) decides whether a side renders its table+header.
  // A side that legitimately has zero groups pre-filter (e.g. no SG&A rows
  // in this scope) still renders nothing, unchanged.
  const nowMonth = nowMonthKey()

  // ADR-0026: months whose SAP actuals are incomplete arrive as null, so the
  // rows themselves say what the SAP totals cover. `null` = all 12 months
  // shown, and then nothing extra is rendered at all.
  const sapCoverage = sapCoverageLabel(rows)
  const sapTotalTitle = sapCoverage ? `รวมเฉพาะเดือนที่ข้อมูลครบ: ${sapCoverage}` : undefined

  // Frozen-column left offsets derived from the CURRENT widths (UI-parity
  // point 8c) — no DOM measurement, both side-tables read this SAME object
  // so they stay pixel-aligned by construction. Applied as inline CSS custom
  // properties; the existing `.frz-1/2/3/4/5 { left: var(--frzN) }` rules in
  // global.css then just work, same as the old static values did.
  const { frz1, frz2, frz3, frz4, frz5 } = freezeOffsets(colWidths)
  const freezeStyle = {
    '--frz1': `${frz1}px`,
    '--frz2': `${frz2}px`,
    '--frz3': `${frz3}px`,
    '--frz4': `${frz4}px`,
    '--frz5': `${frz5}px`,
  } as CSSProperties

  const updateFilter =
    (key: keyof ColumnFilters) =>
    (e: ChangeEvent<HTMLInputElement>) =>
      setColFilters((f) => ({ ...f, [key]: e.target.value }))

  // Fullscreen toggle (⤢) — ONE shared node rendered into the group-head
  // row's first frozen <th> of EACH side-table (same convention as
  // collapse-columns-btn): either copy flips the ONE shared state, which
  // lives in BudgetGrid because the overlay must also contain the toolbar /
  // legend / Submit bar. The button is a CHILD of the existing <th> — never
  // a new cell — so the frozen-column colSpan math (model.ts) is untouched.
  // The <th> is already position:sticky, so no wrapper is needed for the
  // absolutely-positioned button; no z-index on the button (it inherits the
  // th's stacking context, same as .col-toggle-btn).
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

  return (
    <>
      <ColumnWidthMeasurer containerRef={measureContainerRef} candidates={measureCandidates} />
      <div className="grid-sides">
        {(['COST', 'SGA'] as const).map((side) => {
        if (sidesWithData[side].length === 0) return null
        const groups = sections[side]
        return (
          <div key={side} className="side-section" data-testid={`side-section-${side}`}>
            {/* Heading + "Reset columns" share one row (jakkaritw feedback —
               the button used to float in its own right-aligned row above
               both tables and read as detached). colWidths is still ONE
               state shared by both side-tables, so both buttons call the
               same handler; each side needs its own data-testid since the
               button now renders twice. */}
            <div
              className="side-heading-row"
              ref={(el) => {
                headingRowRefs.current[side] = el
              }}
            >
              <h2 className="side-heading">{SIDE_LABEL[side]}</h2>
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={handleResetColumns}
                title="รีเซ็ตความกว้างคอลัมน์ให้พอดีเนื้อหา"
                /* Both buttons carry the same visible label, so a screen-reader
                   button list would otherwise show two identical entries — the
                   section name (free for sighted users from the adjacent h2)
                   goes into the accessible name instead. */
                aria-label={`Reset columns · ${SIDE_LABEL[side]}`}
                data-testid={`reset-columns-btn-${side}`}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
                  <path d="M3 3v5h5" />
                </svg>
                Reset columns
              </button>
            </div>
            {/* .table-panel = bordered frame (border/radius live here, not on
               .data-table, so the sticky header isn't clipped); .table-wrap =
               the actual vertical+horizontal scroll container. Only the
               LAST rendered side gets a measured inline max-height (see
               `measureLastTableMaxHeight` above) — an earlier side (or the
               last one whenever the measurement is unavailable) keeps the
               plain CSS cap, no inline style at all. */}
            <div className="table-panel">
              <div
                className="table-wrap"
                style={
                  side === lastRenderedSide && lastTableMaxHeight !== undefined
                    ? { maxHeight: lastTableMaxHeight }
                    : undefined
                }
              >
                <table className="data-table" style={freezeStyle}>
                  {/* Column widths live on the <colgroup> (fixed layout) —
                     the 4 identity cols (incl. Remark) come from the SAME
                     shared `colWidths` state, Status + the 12 month cols from
                     fixed CSS classes (.status-col/.m-col in global.css), so
                     BOTH side-tables render an identical colgroup and every
                     column stays pixel-aligned across COST/SGA. Auto
                     table-layout could never promise that: its widths are
                     content-driven, so a long reference-hint in one table
                     widened its Status column and shifted all its month
                     columns vs the other table (measured: Jan off by ~147px). */}
                  <colgroup>
                    <col style={{ width: colWidths.cc }} />
                    <col style={{ width: colWidths.gl }} />
                    {/* GL Group / Remark / Status columns vanish entirely in
                       compact mode ("ซ่อนคอลัมน์" toggle) — CC + GL Code
                       become the whole frozen identity band. */}
                    {!columnsCollapsed && (
                      <>
                        <col style={{ width: colWidths.glGroup }} />
                        <col style={{ width: colWidths.remark }} />
                        <col className="status-col" />
                      </>
                    )}
                    <col className="m-col total-year-col" />
                    {MONTH_KEYS.map((m) => (
                      <col key={m} className="m-col" />
                    ))}
                    <col className="action-col" />
                  </colgroup>
                  <thead>
                    {/* Group-head row (UI-parity point 8a): identity+Status
                       merge into one blank band, the 12 month columns get a
                       neutral serif label. Deliberately NOT a bare year —
                       the month columns mix SAP/Approved (year-1) and
                       Pending (year), a single year label here would
                       reintroduce that exact year confusion (see the
                       legend, point 6, for the per-layer years). */}
                    <tr className="group-head-row">
                      {columnsCollapsed ? (
                        <th colSpan={2} className="frz frz-1 frz-edge">{fullscreenToggle}</th>
                      ) : (
                        <>
                          <th colSpan={4} className="frz frz-1">{fullscreenToggle}</th>
                          {/* Status is the 5th FROZEN column (frz-5) — without it,
                           * scrolling slid Status under the Remark pane and the
                           * colSpan=5 subtotal label covered the Jan/Feb cells. */}
                          <th className="frz frz-5 frz-edge" />
                        </>
                      )}
                      <th className="month-group-label total-year-head">
                        <span className="th-label">รวมทั้งปี</span>
                      </th>
                      <th colSpan={12} className="month-group-label">
                        <span className="th-label">งบประมาณรายเดือน (บาท)</span>
                      </th>
                      <th className="action-col-head" aria-hidden="true" />
                    </tr>
                    {/* Column-filter row (UI-parity point 8b, mockup
                       col-filter-row): every `.th-label` keeps its spot, a
                       `.col-filter` input sits below the 3 filterable
                       identity columns, a same-height `.col-filter-spacer`
                       below Status + each month so every header cell in the
                       row stays the same height. State is shared with the
                       OTHER side-table (`colFilters` lives in this
                       component, not per-table), so typing here also
                       filters the other side. */}
                    <tr className="col-row">
                      {/* Identity widths are NOT set here — they live on the
                         <colgroup> above (fixed layout sizes columns from
                         <col> elements + the first row only; a width on this
                         second-row th would be ignored). */}
                      <th className="frz frz-1">
                        <span className="th-label">Cost Center</span>
                        <input
                          type="text"
                          className="col-filter"
                          placeholder="กรอง…"
                          data-testid="filter-cc"
                          value={colFilters.cc}
                          onChange={updateFilter('cc')}
                        />
                        <div
                          className={`col-resize${draggingKey === 'cc' ? ' is-dragging' : ''}`}
                          role="separator"
                          aria-orientation="vertical"
                          aria-label="ปรับความกว้างคอลัมน์ Cost Center"
                          title="ลากเพื่อปรับความกว้าง"
                          data-testid="col-resize-cc"
                          onMouseDown={startColumnResize('cc')}
                          onTouchStart={startColumnResize('cc')}
                        />
                      </th>
                      <th className={`frz frz-2${columnsCollapsed ? ' frz-edge' : ''}`}>
                        <span className="th-label">GL Code</span>
                        {/* Expand button — restores GL Group/Remark/Status.
                           Rendered ONLY while collapsed; the mirror collapse
                           button below lives on the Status th, which itself
                           only exists in the expanded state. */}
                        {columnsCollapsed && (
                          <button
                            type="button"
                            className="col-toggle-btn"
                            title={EXPAND_COLUMNS_LABEL}
                            aria-label={EXPAND_COLUMNS_LABEL}
                            data-testid="expand-columns-btn"
                            onClick={() => setColumnsCollapsed(false)}
                          >
                            <ChevronsRightIcon />
                          </button>
                        )}
                        <input
                          type="text"
                          className="col-filter"
                          placeholder="กรอง…"
                          data-testid="filter-gl"
                          value={colFilters.gl}
                          onChange={updateFilter('gl')}
                        />
                        <div
                          className={`col-resize${draggingKey === 'gl' ? ' is-dragging' : ''}`}
                          role="separator"
                          aria-orientation="vertical"
                          aria-label="ปรับความกว้างคอลัมน์ GL Code"
                          title="ลากเพื่อปรับความกว้าง"
                          data-testid="col-resize-gl"
                          onMouseDown={startColumnResize('gl')}
                          onTouchStart={startColumnResize('gl')}
                        />
                      </th>
                      {!columnsCollapsed && (
                        <>
                          <th className="frz frz-3">
                            <span className="th-label">GL Group</span>
                            <input
                              type="text"
                              className="col-filter"
                              placeholder="กรอง…"
                              data-testid="filter-glgroup"
                              value={colFilters.glGroup}
                              onChange={updateFilter('glGroup')}
                            />
                            <div
                              className={`col-resize${draggingKey === 'glGroup' ? ' is-dragging' : ''}`}
                              role="separator"
                              aria-orientation="vertical"
                              aria-label="ปรับความกว้างคอลัมน์ GL Group"
                              title="ลากเพื่อปรับความกว้าง"
                              data-testid="col-resize-glgroup"
                              onMouseDown={startColumnResize('glGroup')}
                              onTouchStart={startColumnResize('glGroup')}
                            />
                          </th>
                          <th className="frz frz-4">
                            <span className="th-label">Remark</span>
                            <input
                              type="text"
                              className="col-filter"
                              placeholder="กรอง…"
                              data-testid="filter-remark"
                              value={colFilters.remark}
                              onChange={updateFilter('remark')}
                            />
                            <div
                              className={`col-resize${draggingKey === 'remark' ? ' is-dragging' : ''}`}
                              role="separator"
                              aria-orientation="vertical"
                              aria-label="ปรับความกว้างคอลัมน์ Remark"
                              title="ลากเพื่อปรับความกว้าง"
                              data-testid="col-resize-remark"
                              onMouseDown={startColumnResize('remark')}
                              onTouchStart={startColumnResize('remark')}
                            />
                          </th>
                          <th className="frz frz-5">
                            <span className="th-label">Status</span>
                            {/* Collapse button — hides GL Group/Remark/Status. */}
                            <button
                              type="button"
                              className="col-toggle-btn"
                              title={COLLAPSE_COLUMNS_LABEL}
                              aria-label={COLLAPSE_COLUMNS_LABEL}
                              data-testid="collapse-columns-btn"
                              onClick={() => setColumnsCollapsed(true)}
                            >
                              <ChevronsLeftIcon />
                            </button>
                            <input
                              type="text"
                              className="col-filter"
                              placeholder="กรอง…"
                              data-testid="filter-status"
                              value={colFilters.status}
                              onChange={updateFilter('status')}
                            />
                          </th>
                        </>
                      )}
                      {/* Year-total column header — class `total-year-col`
                          (NOT `month-col`) on purpose: tests + the `.now`
                          highlight logic count exactly the 12 month th's. */}
                      <th className="total-year-col">
                        <span className="th-label">Jan–Dec</span>
                        <div className="col-filter-spacer" />
                      </th>
                      {MONTH_KEYS.map((m) => (
                        <th key={m} className={`month-col${m === nowMonth ? ' now' : ''}`}>
                          <span className="th-label">{MONTH_LABELS[m]}</span>
                          <div className="col-filter-spacer" />
                        </th>
                      ))}
                      <th className="action-col-head">
                        <div className="col-filter-spacer" />
                      </th>
                    </tr>
                  </thead>
                  {groups.length === 0 ? (
                    <tbody>
                      <tr>
                        <td colSpan={fullRowColSpan(columnsCollapsed)} className="grid-empty-row" data-testid={`grid-empty-filtered-${side}`}>
                          ไม่มีรายการที่ตรงกับตัวกรอง
                        </td>
                      </tr>
                    </tbody>
                  ) : (
                    <>
                      {groups.map((group) => (
                        <Fragment key={group.glGroup}>
                          {group.rows.map((row) => (
                            <TxnBlock
                              key={rowKey(row.cost_center, row.gl_account)}
                              row={row}
                              glRef={glRef}
                              onCommitMonth={onCommitMonth}
                              onCommitRemark={onCommitRemark}
                              message={rowMessages[rowKey(row.cost_center, row.gl_account)]}
                              onOpenSpecial={onOpenSpecial}
                              onDeleteRow={onDeleteRow}
                              nowMonth={nowMonth}
                              columnsCollapsed={columnsCollapsed}
                              sapTotalTitle={sapTotalTitle}
                            />
                          ))}
                          {/* Group subtotal stays pending-only (it mirrors the
                              editable cells above it) — the label says so. */}
                          <SubtotalRow label={`รวม ${group.glGroup} · Pending`} totals={group.subtotal} layer="pending" columnsCollapsed={columnsCollapsed} />
                        </Fragment>
                      ))}
                      {/* Side grand total: one row per layer (SAP actual /
                          Approved budget / Pending draft), each summing every
                          cc+gl row currently shown in this side (filteredRows),
                          month by month. Applies to BOTH sides — COST (5xxx)
                          and SGA (6xxx) — via the shared render below. */}
                      {(
                        [
                          // ADR-0026: the SAP grand total sums the complete
                          // months only, so it says which ones (e.g.
                          // "(Jan–Mar)") — a total that cannot be added up
                          // from the cells on screen would look like a bug.
                          ['sap', `รวมทั้งหมด · SAP · ใช้จริง${sapCoverage ? ` (${sapCoverage})` : ''}`],
                          ['board', 'รวมทั้งหมด · Approved · งบ'],
                          ['pending', 'รวมทั้งหมด · Pending · รออนุมัติ'],
                        ] as const
                      ).map(([layer, label]) => (
                        <SubtotalRow
                          key={layer}
                          label={label}
                          totals={sectionTotals(groups.flatMap((g) => g.rows))}
                          layer={layer}
                          columnsCollapsed={columnsCollapsed}
                        />
                      ))}
                    </>
                  )}
                </table>
              </div>
            </div>
          </div>
        )
        })}
      </div>
    </>
  )
}
