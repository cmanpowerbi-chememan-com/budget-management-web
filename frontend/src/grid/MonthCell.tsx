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

/** Sanitize free-typed month input: digits + at most one decimal point +
 * at most 2 decimal places. Letters and minus signs are dropped (no
 * negatives per business rule); extra dots beyond the first are dropped
 * rather than resetting the field, so "1.2.3" becomes "1.23" not "1.2". */
function sanitizeMonthInput(raw: string): string {
  const digitsAndDot = raw.replace(/[^0-9.]/g, '')
  const dotIndex = digitsAndDot.indexOf('.')
  if (dotIndex === -1) return digitsAndDot
  const intPart = digitsAndDot.slice(0, dotIndex)
  const fracPart = digitsAndDot.slice(dotIndex + 1).replace(/\./g, '').slice(0, 2)
  return `${intPart}.${fracPart}`
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
    const className = `month-value pending-readonly${value === 0 ? ' zero' : ''}`
    return (
      <span className={className} title={disabledReason} aria-label={label} data-testid={testId}>
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
      onChange={(e) => setDraft(sanitizeMonthInput(e.target.value))}
      onBlur={() => {
        const n = Number(draft)
        // A bad partial input (e.g. a lone "." left after sanitizing) must
        // never reach onCommit as NaN — NaN !== value is always true, which
        // would fire an invalid commit regardless of the current value.
        const parsed = draft === '' || Number.isNaN(n) ? 0 : n
        if (parsed !== value) onCommit(parsed)
      }}
    />
  )
}
