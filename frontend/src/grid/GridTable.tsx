import { Fragment } from 'react'
import type { BudgetRow, GlAccount } from '../api/types'
import { MonthCell } from './MonthCell'
import { formatThb, glMetaFor, groupAndSortBySide, isEditableCell, MONTH_KEYS, sectionTotals, type MonthKey } from './model'

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
}: {
  values: Record<MonthKey, number>
  layerTestId: 'sap-value' | 'board-value'
  /** Data-layer pill color (mockup 0002.3budget-export.html) — SAP = green,
   * Approved (board, read-only) = blue. A zero value always mutes the pill
   * regardless of layer. */
  variant: 'sap' | 'approved-ro'
  cc: string
  gl: string
}) {
  return (
    <>
      {MONTH_KEYS.map((m) => {
        const value = values[m]
        const className = `month-value ${variant}${value === 0 ? ' zero' : ''}`
        return (
          <td key={m} className="month-cell" data-testid={`${layerTestId}-${cc}-${gl}-${m}`}>
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
}: {
  row: BudgetRow
  editable: boolean
  disabledReason?: string
  onCommitMonth: GridTableProps['onCommitMonth']
}) {
  const { cost_center: cc, gl_account: gl } = row
  return (
    <>
      {MONTH_KEYS.map((m) => (
        <td key={m} className="month-cell" data-testid={`pending-cell-${cc}-${gl}-${m}`}>
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
}: {
  row: BudgetRow
  glRef: GlAccount[]
  onCommitMonth: GridTableProps['onCommitMonth']
  message?: RowMessage
  onOpenSpecial?: GridTableProps['onOpenSpecial']
}) {
  const meta = glMetaFor(row.gl_account, glRef)
  const editable = isEditableCell(row.editable, meta.is_special, meta.in_master)
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
          {gl}
          <div className="gl-name">{meta.gl_name ?? '—'}</div>
        </td>
        <td className="gl-group-cell frz frz-3">{meta.gl_group}</td>
        <td className="status-cell sap">SAP · ใช้จริง</td>
        <MonthCells values={row.sap} layerTestId="sap-value" variant="sap" cc={cc} gl={gl} />
      </tr>
      <tr className="txn-row" data-status="approved">
        <td colSpan={3} className="frz frz-1 frz-edge" />
        <td className="status-cell approved">Approved · งบ</td>
        <MonthCells values={row.board} layerTestId="board-value" variant="approved-ro" cc={cc} gl={gl} />
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
  if (rows.length === 0) {
    return <div className="grid-empty">ไม่มีรายการที่ตรงกับตัวกรองนี้</div>
  }

  const sections = groupAndSortBySide(rows, glRef)

  return (
    <div className="grid-sides">
      {(['COST', 'SGA'] as const).map((side) => {
        const groups = sections[side]
        if (groups.length === 0) return null
        return (
          <div key={side} className="side-section" data-testid={`side-section-${side}`}>
            <h2 className="side-heading">{SIDE_LABEL[side]}</h2>
            {/* .table-panel = bordered frame (border/radius live here, not on
               .data-table, so the sticky header isn't clipped); .table-wrap =
               the actual vertical+horizontal scroll container. */}
            <div className="table-panel">
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="frz frz-1">Cost Center</th>
                      <th className="frz frz-2">GL Code</th>
                      <th className="frz frz-3">GL Group</th>
                      <th>Status</th>
                      {MONTH_KEYS.map((m) => (
                        <th key={m} className="month-col">
                          {m}
                        </th>
                      ))}
                    </tr>
                  </thead>
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
                        />
                      ))}
                      <SubtotalRow label={`รวม ${group.glGroup}`} totals={group.subtotal} />
                    </Fragment>
                  ))}
                  <SubtotalRow
                    label={`รวมทั้งหมด · ${SIDE_LABEL[side]}`}
                    totals={sectionTotals(groups.flatMap((g) => g.rows))}
                  />
                </table>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
