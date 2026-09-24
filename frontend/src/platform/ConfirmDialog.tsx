import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useBackdropDismiss } from './backdropDismiss'
import { answerConfirm, subscribeConfirmRequests, type ConfirmRequest } from './confirm'

const MESSAGE_ID = 'confirm-dialog-message'

/** Host for `confirmDialog()` (see `confirm.ts`) — mounted ONCE at the App
 * root, next to `<NoticeToasts />`. Reuses the app's existing hand-rolled
 * `.modal-backdrop`/`.modal` shell (same skeleton as `AttachmentsModal` /
 * `SessionExpiredDialog`), just without a header — a confirm question has no
 * title to distinguish from its own message.
 *
 * z-index sits ABOVE the ordinary modal/subform layer (z500) and the toast
 * stack (z550) — a confirm can be triggered from inside an already-open
 * AttachmentsModal/DetailSubform/TripManager. It stays BELOW the session-
 * expiry dialog (z600) on purpose: if the session dies while a confirm is
 * open, the session dialog is the terminal, un-dismissable state and must
 * win — see `.confirm-dialog-backdrop` in global.css. */
export function ConfirmDialog() {
  const [request, setRequest] = useState<ConfirmRequest | null>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)

  useEffect(() => subscribeConfirmRequests(setRequest), [])

  useEffect(() => {
    if (request) {
      previouslyFocused.current = document.activeElement as HTMLElement | null
      // Focus lands on Cancel, not OK — the safer default for a destructive
      // confirm (delete file/row/trip/detail line): a stray Tab+Space cannot
      // fire the destructive action by accident.
      cancelRef.current?.focus()
    } else {
      previouslyFocused.current?.focus()
      previouslyFocused.current = null
    }
  }, [request])

  // 2026-09-24 bug fix: a plain `e.target === e.currentTarget` backdrop check
  // also fired on a drag that started inside the dialog and released over
  // the backdrop (see backdropDismiss.ts) — that used to resolve the confirm
  // as `false` from a stray drag, not a real dismiss.
  const backdropHandlers = useBackdropDismiss(() => answer(false))

  if (!request) return null

  function answer(value: boolean) {
    answerConfirm(request!.id, value)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    // preventDefault on both branches: without it, Enter's own browser
    // default (clicking whichever button currently has focus — Cancel, per
    // the effect above) would fire alongside this handler's explicit
    // answer(true) and resolve the promise twice.
    if (e.key === 'Escape') {
      e.preventDefault()
      answer(false)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      answer(true)
    }
  }

  return (
    <div className="modal-backdrop open confirm-dialog-backdrop" {...backdropHandlers}>
      <div
        className="modal confirm-dialog-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={MESSAGE_ID}
        tabIndex={-1}
        data-testid="confirm-dialog"
        onKeyDown={handleKeyDown}
      >
        <div className="modal-body">
          <p id={MESSAGE_ID} className="confirm-dialog-message" data-testid="confirm-message">
            {request.message}
          </p>
        </div>
        <div className="modal-foot" style={{ justifyContent: 'flex-end' }}>
          <div className="modal-actions">
            <button ref={cancelRef} type="button" className="btn" data-testid="confirm-cancel" onClick={() => answer(false)}>
              {request.cancelLabel}
            </button>
            <button
              type="button"
              className={request.danger ? 'btn-danger' : 'btn-submit'}
              data-testid="confirm-ok"
              onClick={() => answer(true)}
            >
              {request.confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
