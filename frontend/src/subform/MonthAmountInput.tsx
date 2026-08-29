import { useEffect, useRef, useState } from 'react'
import { pendingAmountNoticeTh, roundPendingAmount, sanitizeMonthInput } from '../grid/model'
import { publishNotice } from '../platform/notice'

export interface MonthAmountInputProps {
  value: number
  onCommit: (value: number) => void
  ariaLabel: string
  className?: string
  disabled?: boolean
  testId?: string
}

/** Draft-string-then-commit money input — same shape as `grid/MonthCell.tsx`'s
 * editable input (bug-subform-no-decimals, 2026-08-19): local string state
 * while typing (sanitized via the shared `sanitizeMonthInput`), parsed to a
 * number and committed on blur, and re-synced whenever the SERVER-derived
 * `value` genuinely changes underneath a save or a 409-conflict refetch (the
 * same row/card key across a re-render means the SAME component instance —
 * an uncontrolled `draft` would otherwise never notice the external update).
 *
 * `lastSyncedValue` (2026-08-19 race fix): the resync effect only calls
 * `setDraft` when `value` differs from the value it last synced FROM — never
 * on the redundant first run. A plain `useEffect(() => setDraft(String(value)),
 * [value])` (no guard) also fires once on mount, even though `useState`'s
 * initializer already set `draft` correctly — that mount-time call is a
 * silent no-op MOST of the time, but it is still a pending passive effect,
 * and this component mounts as a side effect of an ASYNC fetch (a row only
 * exists once the parent's `fetchDetailLines`/`fetchTrips` promise resolves
 * and calls `setRows`/`setCards`). React can defer flushing that pending
 * mount effect past a `waitFor` resolving in a test (or, in principle, past
 * a very fast real keystroke) — if it then flushes in the SAME batch as a
 * user's `onChange`, the two `setDraft` calls race, and the effect's stale
 * `setDraft(String(value))` can win, silently reverting what the user just
 * typed. Reproduced directly (bug-subform-no-decimals gate feedback,
 * 2026-08-19): instrumented logs showed, on a failing run, `onChange fired
 * -> effect fired, setting draft to <the OLD value>` — the deferred mount
 * effect firing AFTER the keystroke inside the same act() flush. Guarding on
 * "did value actually change" makes the mount run a true no-op (skips
 * `setDraft` entirely — nothing to race), while a genuine later external
 * change (save/refetch) still resyncs correctly, deterministically. */
export function MonthAmountInput({ value, onCommit, ariaLabel, className, disabled, testId }: MonthAmountInputProps) {
  const [draft, setDraft] = useState(String(value))
  const lastSyncedValue = useRef(value)

  useEffect(() => {
    if (value !== lastSyncedValue.current) {
      lastSyncedValue.current = value
      setDraft(String(value))
    }
  }, [value])

  return (
    <input
      type="text"
      inputMode="numeric"
      aria-label={ariaLabel}
      className={className}
      data-testid={testId}
      value={draft}
      disabled={disabled}
      onChange={(e) => setDraft(sanitizeMonthInput(e.target.value))}
      onBlur={() => {
        const n = Number(draft)
        // A bad partial input (e.g. a lone "." left after sanitizing) must
        // never reach onCommit as NaN — NaN !== value is always true, which
        // would fire an invalid commit regardless of the current value.
        const typed = draft === '' || Number.isNaN(n) ? 0 : n
        // jakkaritw 2026-08-19: round to the nearest 100 (half-up) and clamp
        // to the 100,000,000 cap ON COMMIT — same rule/placement as
        // `grid/MonthCell.tsx`'s editable input (this component IS the
        // shared implementation for the special-GL subform and Trip
        // Manager's manual travel-line months; per-diem never reaches this
        // component at all — it renders via a read-only `<span>`). The
        // field always redraws to the CORRECTED number, and since 2026-08-29
        // a toast says what was corrected too (see `MonthCell`'s copy of this
        // block for why it is keyed on typed-vs-parsed).
        const parsed = roundPendingAmount(typed)
        setDraft(String(parsed))
        const notice = pendingAmountNoticeTh(typed, parsed)
        if (notice) publishNotice(notice)
        if (parsed !== value) onCommit(parsed)
      }}
    />
  )
}
