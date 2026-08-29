import { useEffect, useState } from 'react'
import { subscribeNotices, type Notice } from './notice'

/** How long a toast stays up. Long enough to read a two-line Thai sentence
 * without hunting for it, short enough that a filler correcting several cells
 * in a row is not left with a wall of stale messages. */
export const NOTICE_TTL_MS = 6000

/** Oldest toasts drop off past this — a fast typist blurring cell after cell
 * would otherwise stack a dozen. */
const MAX_VISIBLE = 3

/** Renders the transient notices published via `publishNotice`. Mounted ONCE,
 * at the App root — the fixed-position stack must sit above the fullscreen
 * grid overlay (z300) and above an open subform modal (z500), so it cannot
 * live inside either of them.
 *
 * `role="status"` + `aria-live="polite"` (not `alert`): the message reports a
 * correction the app already applied and re-displayed in the field itself, so
 * it should be announced at the next natural pause, never interrupt. */
export function NoticeToasts() {
  const [notices, setNotices] = useState<Notice[]>([])

  useEffect(() => subscribeNotices((notice) => {
    setNotices((current) => [...current, notice].slice(-MAX_VISIBLE))
  }), [])

  // One timer per notice, cleared on unmount. Keyed on `notices` rather than
  // set inside the subscription so a notice dropped by the MAX_VISIBLE slice
  // never leaves an orphan timer behind that would later filter an id that is
  // already gone (harmless, but it would keep the component re-rendering after
  // the stack emptied).
  useEffect(() => {
    if (notices.length === 0) return
    const timers = notices.map((notice) =>
      setTimeout(() => setNotices((current) => current.filter((n) => n.id !== notice.id)), NOTICE_TTL_MS),
    )
    return () => timers.forEach(clearTimeout)
  }, [notices])

  if (notices.length === 0) return null

  return (
    <div className="notice-stack" data-testid="notice-stack">
      {notices.map((notice) => (
        <div key={notice.id} className="notice-toast" role="status" aria-live="polite">
          <span className="notice-toast-text">{notice.text}</span>
          <button
            type="button"
            className="notice-toast-close"
            aria-label="ปิดข้อความ"
            onClick={() => setNotices((current) => current.filter((n) => n.id !== notice.id))}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
