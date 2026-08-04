import { useEffect, useRef, useSyncExternalStore } from 'react'
import { buildLoginRedirectUrl } from '../api/client'
import { isSessionExpired, SESSION_EXPIRED_MESSAGE, subscribeSessionExpired } from '../api/sessionExpiry'
import { currentHref, navigate } from '../platform/location'

const TITLE_ID = 'session-expired-title'
const BODY_ID = 'session-expired-body'

/** Locked-copy, ONE-exit modal shown once the Easy Auth session dies
 * mid-use (ADR-0004; design brief 2026-08-04). Reuses the app's existing
 * hand-rolled `.modal-backdrop`/`.modal` skeleton (closest/smallest match:
 * `attachments/AttachmentsModal.tsx`) — deliberately has NO close
 * affordance (no ✕, no backdrop-click, no Escape): every request keeps
 * failing once the session is dead, so dismissing would strand the user on
 * a page where nothing works. The only way out is the login button.
 *
 * Mounted once, unconditionally, high in `App.tsx` (outside the `ready`
 * gate) — it must still render even if the very first boot call (`GET
 * /me`) is what raised the latch, before `BudgetGrid` ever mounts. */
export function SessionExpiredDialog() {
  const expired = useSyncExternalStore(subscribeSessionExpired, isSessionExpired, isSessionExpired)
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Focus the CONTAINER, not the button — a keystroke queued from the
    // grid (e.g. a stray Enter) must not land on the button and trigger
    // navigation by accident.
    if (expired) dialogRef.current?.focus()
  }, [expired])

  if (!expired) return null

  return (
    <div className="modal-backdrop open session-expired-backdrop">
      <div
        ref={dialogRef}
        className="modal session-expired-modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={TITLE_ID}
        aria-describedby={BODY_ID}
        tabIndex={-1}
        data-testid="session-expired-dialog"
      >
        <div className="modal-head">
          <div>
            <h2 className="modal-title" id={TITLE_ID}>
              หมดเวลาการเข้าใช้งาน
            </h2>
          </div>
        </div>

        <div className="modal-body">
          <p id={BODY_ID}>{SESSION_EXPIRED_MESSAGE}</p>
        </div>

        <div className="modal-foot" style={{ justifyContent: 'flex-end' }}>
          <div className="modal-actions">
            <button
              type="button"
              className="btn-submit"
              data-testid="session-expired-login-btn"
              onClick={() => navigate(buildLoginRedirectUrl(currentHref()))}
            >
              เข้าสู่ระบบใหม่
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
