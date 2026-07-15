import { useEffect, useState } from 'react'
import { formatThb } from './model'

export interface MonthCellProps {
  value: number
  editable: boolean
  onCommit: (value: number) => void
  label: string
  /** Non-null = a special-GL cell blocked from direct edit (ADR-0005): the
   * cell shows read-only + this Thai tooltip instead of an input, even
   * when the parent row is otherwise editable. */
  disabledReason?: string
  /** Optional `data-testid` on the actual interactive element (input or
   * read-only span) — lets the parent grid target a specific cell. */
  testId?: string
}

/** One month's amount, editable or read-only. Pure display + one commit
 * callback — the parent (`GridTable`/`BudgetGrid`) owns save/conflict
 * handling; this component never calls the API. */
export function MonthCell({ value, editable, onCommit, label, disabledReason, testId }: MonthCellProps) {
  const [draft, setDraft] = useState(String(value))

  // Re-sync the displayed draft whenever the SERVER-derived value changes
  // (a successful save's authoritative total, or a 409-conflict revert to
  // the freshly-refetched row) — an editable cell is otherwise an
  // uncontrolled input whose local `draft` would never notice an external
  // update on the same component instance (same row key -> same instance
  // across re-renders).
  useEffect(() => {
    setDraft(String(value))
  }, [value])

  if (!editable) {
    return (
      <span className="month-value" title={disabledReason} aria-label={label} data-testid={testId}>
        {formatThb(value)}
      </span>
    )
  }

  return (
    <input
      type="text"
      inputMode="numeric"
      className="month-value month-input"
      aria-label={label}
      data-testid={testId}
      value={draft}
      onChange={(e) => setDraft(e.target.value.replace(/[^0-9]/g, ''))}
      onBlur={() => {
        const parsed = draft === '' ? 0 : Number(draft)
        if (parsed !== value) onCommit(parsed)
      }}
    />
  )
}
