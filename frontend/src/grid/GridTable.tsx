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
import type { BudgetRow, GlAccount, LayerAmounts } from '../api/types'
import { MonthCell } from './MonthCell'
import {
  BLANK_COLUMN_FILTERS,
  clampColumnWidth,
  clearStoredColumnWidths,
  DEFAULT_COLUMN_WIDTHS,
  filterRows,
  fitColumnWidth,
  formatThb,
  freezeOffsets,
  fullRowColSpan,
  glMetaFor,
  groupAndSortBySide,
  groupChipClass,
  hasStoredColumnWidthsOverride,
  identityColSpan,
  isDeletableRow,
  isEditableCell,
  loadStoredColumnWidths,
  MONTH_KEYS,
  MONTH_LABELS,
  nowMonthKey,
  persistColumnWidths,
  sectionTotals,
  selectMeasureCandidates,
  subtotalLabelColSpan,
  type ColumnFilters,
  type ColumnWidthKey,
  type ColumnWidths,
  type MonthKey,
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
}: {
  values: LayerAmounts
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
}) {
  return (
    <>
      {/* Year-total column sits BEFORE Jan (user requirement 2026-07-30):
          sum of m01..m12 for this row+layer, read straight off the stored
          total_year. */}
      <td className="month-cell total-year-cell" data-testid={`${layerTestId}-${cc}-${gl}-year`}>
        <span className={`month-value ${variant}${values.total_year === 0 ? ' zero' : ''}`}>
          {formatThb(values.total_year)}
        </span>
      </td>
      {MONTH_KEYS.map((m) => {
        const value = values[m]
        const className = `month-value ${variant}${value === 0 ? ' zero' : ''}`
        const tdClassName = `month-cell${m === nowMonth ? ' now' : ''}`
        return (
          <td key={m} className={tdClassName} data-testid={`${layerTestId}-${cc}-${gl}-${m}`}>
            <span className={className}>{formatThb(value)}</span>
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
        <MonthCells values={row.sap} layerTestId="sap-value" variant="sap" cc={cc} gl={gl} nowMonth={nowMonth} />
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
          {formatThb(totals[layer].total_year)}
        </td>
        {MONTH_KEYS.map((m) => (
          <td key={m} className="month-cell">
            {formatThb(totals[layer][m])}
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
  // Which sides exist AT ALL (ignoring the filter) — decides whether a side
  // renders its table+header, same as before this feature existed. A side
  // that legitimately has zero groups pre-filter (e.g. no SG&A rows in this
  // scope) still renders nothing, unchanged.
  const sidesWithData = groupAndSortBySide(rows, glRef)
  const nowMonth = nowMonthKey()

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
      {/* Small right-aligned control row (UI-parity point 8c) — kept OUTSIDE
         .grid-sides since it applies to both side-tables at once; state
         (colWidths) is local to this component, so the button lives here
         rather than in BudgetGrid's toolbar. */}
      <div className="grid-column-controls">
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          onClick={handleResetColumns}
          title="รีเซ็ตความกว้างคอลัมน์ให้พอดีเนื้อหา"
          data-testid="reset-columns-btn"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
            <path d="M3 3v5h5" />
          </svg>
          Reset columns
        </button>
      </div>
      <div className="grid-sides">
        {(['COST', 'SGA'] as const).map((side) => {
        if (sidesWithData[side].length === 0) return null
        const groups = sections[side]
        return (
          <div key={side} className="side-section" data-testid={`side-section-${side}`}>
            <h2 className="side-heading">{SIDE_LABEL[side]}</h2>
            {/* .table-panel = bordered frame (border/radius live here, not on
               .data-table, so the sticky header isn't clipped); .table-wrap =
               the actual vertical+horizontal scroll container. */}
            <div className="table-panel">
              <div className="table-wrap">
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
                          ['sap', 'รวมทั้งหมด · SAP · ใช้จริง'],
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
