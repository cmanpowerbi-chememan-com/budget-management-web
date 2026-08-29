/** App-wide transient notices (toasts). A module-level pub/sub rather than a
 * React context: the publishers are leaf inputs that live in three different
 * trees — the grid's `MonthCell`, and the special-GL subform / Trip Manager's
 * shared `MonthAmountInput`, both of which render inside a modal — and none of
 * them should have to thread a callback down from `App` (or grow a provider
 * that every future test would need to wrap). Publishing is a plain function
 * call from anywhere, including non-React code.
 *
 * Deliberately tiny: no severity levels, no actions, no queueing policy. The
 * one caller today is the Pending-amount correction message
 * (`pendingAmountNoticeTh`, grid/model.ts) — errors still use the existing
 * per-row `RowMessage` strip, which is anchored to the row it belongs to and
 * is a better surface for anything the user must act on. */
export interface Notice {
  /** Monotonic per-session id — the React list key. Not a timestamp: two
   * notices published in the same millisecond must still be distinct. */
  id: number
  text: string
}

type Listener = (notice: Notice) => void

const listeners = new Set<Listener>()
let nextId = 0

/** Broadcasts `text` to the mounted `<NoticeToasts />`. A no-op (not an
 * error) when nothing is listening — a notice is never load-bearing, so a
 * publisher must never have to care whether the host is mounted. */
export function publishNotice(text: string): void {
  const notice: Notice = { id: ++nextId, text }
  for (const listener of listeners) listener(notice)
}

/** Subscribes to notices; returns the unsubscribe function (the shape
 * `useEffect` wants back). */
export function subscribeNotices(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
