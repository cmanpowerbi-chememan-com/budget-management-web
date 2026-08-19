import { useEffect, useRef, useState } from 'react'
import { formatThb, roundPendingAmount, sanitizeMonthInput } from './model'

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
  const lastSyncedValue = useRef(value)

  // Re-sync the displayed draft whenever the SERVER-derived value GENUINELY
  // changes (a successful save's authoritative total, or a 409-conflict
  // revert to the freshly-refetched row) — an editable cell is otherwise an
  // uncontrolled input whose local `draft` would never notice an external
  // update on the same component instance (same row key -> same instance
  // across re-renders).
  //
  // The `lastSyncedValue` guard (2026-08-19, race fix): without it, this
  // effect also fires once on mount even though `useState`'s initializer
  // already set `draft` correctly — a redundant `setDraft` call that is
  // usually a harmless no-op, but is still a pending passive effect. A row
  // that mounts as the result of an ASYNC fetch (the normal case — a row
  // only exists once the parent's own load promise resolves) can have that
  // pending mount effect flush LATE, and if it lands in the same commit as
  // a fast `onChange`, the two `setDraft` calls race — the stale mount
  // effect can win and silently revert what the user just typed
  // (reproduced via `subform/MonthAmountInput.tsx`, the same pattern,
  // bug-subform-no-decimals gate feedback). Comparing against the value
  // last synced FROM makes the mount run a true no-op (skips `setDraft`
  // entirely — nothing left to race) while a real external change still
  // resyncs deterministically.
  useEffect(() => {
    if (value !== lastSyncedValue.current) {
      lastSyncedValue.current = value
      setDraft(String(value))
    }
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
        const typed = draft === '' || Number.isNaN(n) ? 0 : n
        // jakkaritw 2026-08-19: round to the nearest 100 (half-up) and clamp
        // to the 100,000,000 cap ON COMMIT, never per keystroke (typing 1234
        // must stay reachable, not collapse to 100 after the 3rd digit). The
        // field always redraws to the CORRECTED number — that is the user
        // feedback for both the round and the clamp, no separate toast.
        const parsed = roundPendingAmount(typed)
        setDraft(String(parsed))
        if (parsed !== value) onCommit(parsed)
      }}
    />
  )
}
