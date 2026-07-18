import {
  Fragment,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type TouchEvent as ReactTouchEvent,
} from 'react'
import type { BudgetRow, GlAccount } from '../api/types'
import { MonthCell } from './MonthCell'
import {
  BLANK_COLUMN_FILTERS,
  clampColumnWidth,
  DEFAULT_COLUMN_WIDTHS,
  filterRows,
  formatThb,
  freezeOffsets,
  glMetaFor,
  groupAndSortBySide,
  groupChipClass,
  isEditableCell,
  loadStoredColumnWidths,
  MONTH_KEYS,
  MONTH_LABELS,
  nowMonthKey,
  persistColumnWidths,
  sectionTotals,
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
}

const SIDE_LABEL: Record<'COST' | 'SGA', string> = {
  COST: 'ฝั่งผลิต / ต้นทุน (5xxx)',
  SGA: 'ฝั่งบริหาร / ขาย · SG&A (6xxx)',
}

const SPECIAL_GL_TOOLTIP = 'แก้ไขผ่านฟอร์มย่อย'

/** Fill-scope row whose GL is outside the GL master (add-later policy):
 * shown as read-only reference until an admin adds the GL via Edit GL
 * Group — never an input the server would 400. */
const NOT_IN_MASTER_HINT = 'อ้างอิง — ยังไม่เปิดให้ตั้งงบ'

function rowKey(cc: string, gl: string): string {
  return `${cc}|${gl}`
}

function MonthCells({
  values,
  layerTestId,
  variant,
  cc,
  gl,
  nowMonth,
}: {
  values: Record<MonthKey, number>
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

function TxnBlock({
  row,
  glRef,
  onCommitMonth,
  message,
  onOpenSpecial,
  nowMonth,
}: {
  row: BudgetRow
  glRef: GlAccount[]
  onCommitMonth: GridTableProps['onCommitMonth']
  message?: RowMessage
  onOpenSpecial?: GridTableProps['onOpenSpecial']
  /** Current-month key (UI-parity point 8a). */
  nowMonth: MonthKey
}) {
  const meta = glMetaFor(row.gl_account, glRef)
  const editable = isEditableCell(row.editable, meta.is_special, meta.in_master)
  // Chip is gated on the GROUP NAME (one of the 6 special-GL groups), never
  // on meta.is_special — a fixture/live GL can be is_special:false while
  // still belonging to a chipped group, which would leave some rows in the
  // same group un-chipped. See model.ts groupChipClass for the rationale.
  const chipClass = groupChipClass(meta.gl_group)
  // Marker only when NOT-in-master is the reason the cells are read-only
  // (Fill-scope row) — a See-only row stays unmarked, read-only as before.
  const showReferenceHint = row.editable && !meta.in_master
  const cc = row.cost_center
  const gl = row.gl_account

  return (
    <tbody className="txn-block" data-testid={`txn-${cc}-${gl}`}>
      <tr className="txn-row first" data-status="sap">
        <td className="idx-cell frz frz-1">{cc}</td>
        <td className="gl-cell frz frz-2">
          <span className="gl-code-text">{gl}</span>
          <div className="gl-name">{meta.gl_name ?? '—'}</div>
        </td>
        <td className="gl-group-cell frz frz-3">
          {chipClass ? <span className={`gl-chip special-gl-group ${chipClass}`}>{meta.gl_group}</span> : meta.gl_group}
        </td>
        <td className="status-cell sap">SAP · ใช้จริง</td>
        <MonthCells values={row.sap} layerTestId="sap-value" variant="sap" cc={cc} gl={gl} nowMonth={nowMonth} />
      </tr>
      <tr className="txn-row" data-status="approved">
        <td colSpan={3} className="frz frz-1 frz-edge" />
        <td className="status-cell approved">Approved · งบ</td>
        <MonthCells values={row.board} layerTestId="board-value" variant="approved-ro" cc={cc} gl={gl} nowMonth={nowMonth} />
      </tr>
      <tr className="txn-row last" data-status="pending">
        <td colSpan={3} className="frz frz-1 frz-edge" />
        <td className="status-cell pending">
          Pending · รออนุมัติ
          {meta.is_special && row.editable && onOpenSpecial && (
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
          {meta.is_special && !(row.editable && onOpenSpecial) && (
            <span className="special-hint"> {SPECIAL_GL_TOOLTIP}</span>
          )}
          {showReferenceHint && (
            <span className="reference-hint" data-testid={`reference-hint-${cc}-${gl}`}>
              {NOT_IN_MASTER_HINT}
            </span>
          )}
        </td>
        <PendingCells
          row={row}
          editable={editable}
          disabledReason={meta.is_special ? SPECIAL_GL_TOOLTIP : showReferenceHint ? NOT_IN_MASTER_HINT : undefined}
          onCommitMonth={onCommitMonth}
          nowMonth={nowMonth}
        />
      </tr>
      {message && (
        <tr className="txn-row-message">
          <td colSpan={16} className={`row-message row-message-${message.kind}`}>
            {message.text}
          </td>
        </tr>
      )}
    </tbody>
  )
}

function SubtotalRow({ label, totals }: { label: string; totals: ReturnType<typeof sectionTotals> }) {
  return (
    <tbody>
      <tr className="subtotal-row">
        {/* colSpan=4 covers the 3 frozen identity cols + Status — frozen at
           left:0 (not left-unfrozen) so the label never scrolls out of view
           under the horizontally-scrolled month columns (verified point 1). */}
        <td colSpan={4} className="frz frz-1 frz-edge">
          {label}
        </td>
        {MONTH_KEYS.map((m) => (
          <td key={m} className="month-cell">
            {formatThb(totals.pending[m])}
          </td>
        ))}
      </tr>
    </tbody>
  )
}

/** Renders the main budget grid: two structurally-separate sections (COST
 * 5xxx / SG&A 6xxx — NEVER-CUT, their totals never combine), each grouped
 * by gl_group with a subtotal row, 3 layers per transaction. Pure
 * presentational component — all state/API calls live in `BudgetGrid`. */
export function GridTable({ rows, glRef, onCommitMonth, rowMessages = {}, onOpenSpecial }: GridTableProps) {
  // Shared per-column filter state (UI-parity point 8b) — held LOCALLY here
  // (not lifted to BudgetGrid) since both side-tables live inside this one
  // component; one filter string per column applies to both tables at once,
  // so typing in either table's input keeps them in sync by construction.
  const [colFilters, setColFilters] = useState<ColumnFilters>(BLANK_COLUMN_FILTERS)

  // Identity-column widths (UI-parity point 8c) — held LOCALLY, same
  // reasoning as colFilters: both side-tables live inside this one
  // component and must share ONE set of widths so they stay pixel-aligned.
  // Initial value is read from localStorage once (lazy initializer), never
  // re-read after mount.
  const [colWidths, setColWidths] = useState<ColumnWidths>(() => loadStoredColumnWidths())
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
    setColWidths(DEFAULT_COLUMN_WIDTHS)
    persistColumnWidths(DEFAULT_COLUMN_WIDTHS)
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
  // properties; the existing `.frz-1/2/3 { left: var(--frzN) }` rules in
  // global.css then just work, same as the old static values did.
  const { frz1, frz2, frz3 } = freezeOffsets(colWidths)
  const freezeStyle = { '--frz1': `${frz1}px`, '--frz2': `${frz2}px`, '--frz3': `${frz3}px` } as CSSProperties

  const updateFilter =
    (key: keyof ColumnFilters) =>
    (e: ChangeEvent<HTMLInputElement>) =>
      setColFilters((f) => ({ ...f, [key]: e.target.value }))

  return (
    <>
      {/* Small right-aligned control row (UI-parity point 8c) — kept OUTSIDE
         .grid-sides since it applies to both side-tables at once; state
         (colWidths) is local to this component, so the button lives here
         rather than in BudgetGrid's toolbar. */}
      <div className="grid-column-controls">
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          onClick={handleResetColumns}
          title="รีเซ็ตความกว้างคอลัมน์ทั้งหมด"
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
                  <thead>
                    {/* Group-head row (UI-parity point 8a): identity+Status
                       merge into one blank band, the 12 month columns get a
                       neutral serif label. Deliberately NOT a bare year —
                       the month columns mix SAP/Approved (year-1) and
                       Pending (year), a single year label here would
                       reintroduce that exact year confusion (see the
                       legend, point 6, for the per-layer years). */}
                    <tr className="group-head-row">
                      <th colSpan={3} className="frz frz-1 frz-edge" />
                      <th />
                      <th colSpan={12} className="month-group-label">
                        <span className="th-label">งบประมาณรายเดือน (บาท)</span>
                      </th>
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
                      {/* Explicit width+minWidth (UI-parity point 8c) — header-row-only,
                         auto table-layout propagates it to the whole column (incl. the
                         colSpan=3/4 merged cells above/below). Both side-tables read the
                         SAME `colWidths` state, so they stay aligned. */}
                      <th className="frz frz-1" style={{ width: colWidths.cc, minWidth: colWidths.cc }}>
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
                      <th className="frz frz-2" style={{ width: colWidths.gl, minWidth: colWidths.gl }}>
                        <span className="th-label">GL Code</span>
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
                      <th className="frz frz-3" style={{ width: colWidths.glGroup, minWidth: colWidths.glGroup }}>
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
                      <th>
                        <span className="th-label">Status</span>
                        <div className="col-filter-spacer" />
                      </th>
                      {MONTH_KEYS.map((m) => (
                        <th key={m} className={`month-col${m === nowMonth ? ' now' : ''}`}>
                          <span className="th-label">{MONTH_LABELS[m]}</span>
                          <div className="col-filter-spacer" />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  {groups.length === 0 ? (
                    <tbody>
                      <tr>
                        <td colSpan={16} className="grid-empty-row" data-testid={`grid-empty-filtered-${side}`}>
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
                              message={rowMessages[rowKey(row.cost_center, row.gl_account)]}
                              onOpenSpecial={onOpenSpecial}
                              nowMonth={nowMonth}
                            />
                          ))}
                          <SubtotalRow label={`รวม ${group.glGroup}`} totals={group.subtotal} />
                        </Fragment>
                      ))}
                      <SubtotalRow
                        label={`รวมทั้งหมด · ${SIDE_LABEL[side]}`}
                        totals={sectionTotals(groups.flatMap((g) => g.rows))}
                      />
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
