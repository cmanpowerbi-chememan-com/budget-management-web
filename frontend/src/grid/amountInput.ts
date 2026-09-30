import { formatAmountDraft } from './model'

/** The onChange half of a Pending money input, shared by `MonthCell` and
 * `MonthAmountInput` (jakkaritw, 2026-09-30, issue #37: commas while typing).
 * Returns the grouped text the caller stores as its draft, and — the reason
 * this is not just `formatAmountDraft` — puts the caret where the user expects
 * it, which the pure formatter cannot do.
 *
 * Why the DOM is written HERE instead of after React re-renders: the input is
 * controlled, so when its text changes ("25000" -> "25,000") React writes
 * `input.value` and the browser moves the caret to the end. Restoring the caret
 * from an effect works for that case, but breaks when the formatted text equals
 * the draft state already held (a rejected letter, a deleted comma that is
 * regrouped straight back): no state change means no re-render, and React's
 * controlled-input restore then rewrites the DOM value AFTER any caret we set
 * -> caret jumps to the end anyway. Writing the formatted value and the caret
 * into the element first makes DOM === state before React looks, so its
 * restore/commit is a no-op and the caret is never touched again.
 *
 * The caret is only written when the input is the focused element — never move
 * the caret (or, in some browsers, steal focus) for a change that did not come
 * from the user typing in it. Resync and blur redraws never go through here. */
export function applyAmountKeystroke(input: HTMLInputElement): string {
  const { text, caret } = formatAmountDraft(input.value, input.selectionStart ?? input.value.length)
  if (input.value !== text) input.value = text
  if (input.ownerDocument.activeElement === input) input.setSelectionRange(caret, caret)
  return text
}
