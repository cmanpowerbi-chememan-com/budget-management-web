import { useRef, type MouseEventHandler } from 'react'

export interface BackdropDismissHandlers {
  onMouseDown: MouseEventHandler<HTMLElement>
  onMouseUp: MouseEventHandler<HTMLElement>
  onClick: MouseEventHandler<HTMLElement>
}

/** Guards a `.modal-backdrop`'s dismiss-on-click against a drag that crosses
 * the modal/backdrop boundary (jakkaritw, prd report 2026-09-24): a naive
 * `onClick={(e) => e.target === e.currentTarget && onDismiss()}` also fires
 * when the user presses the mouse on one side of that boundary and releases
 * on the other (e.g. drag-selecting text in an input and overshooting past
 * the modal edge, or pressing in the dim margin and dragging onto a field) —
 * the browser dispatches `click` on the nearest common ancestor of the
 * mousedown/mouseup targets, which is the backdrop itself, so
 * `target === currentTarget` passes even though the user never intended to
 * dismiss anything. BOTH drag directions trigger this the same way.
 * TripManager and DetailSubform callers used to lose typed data this way;
 * ConfirmDialog silently resolved `false` instead of leaving the question
 * open, and AttachmentsModal (no text fields to lose) just closed early.
 *
 * Fix: dismiss only when the PRESS, the RELEASE, and the resulting `click`
 * ALL land on the backdrop itself — `mousedown` seeds the flag, `mouseup`
 * can only narrow it (never re-set it), so a release on the other side of
 * the boundary — in EITHER direction — clears it before `click` ever runs.
 * An ordinary click (press and release on the same spot, no drag) always
 * satisfies this, so normal backdrop-dismiss is unchanged. Accepted
 * limitation: only the press and release POINTS are checked, not the path
 * between them, so a drag that starts on the backdrop, crosses into the
 * modal, and comes back out to the backdrop before releasing still
 * dismisses. The flag resets after every click so a stale press left by an
 * earlier click can't make a later, unrelated bare click (no new mousedown)
 * dismiss on its own. */
export function useBackdropDismiss(onDismiss: () => void): BackdropDismissHandlers {
  const pressedBackdrop = useRef(false)

  return {
    onMouseDown: (e) => {
      pressedBackdrop.current = e.target === e.currentTarget
    },
    onMouseUp: (e) => {
      pressedBackdrop.current = pressedBackdrop.current && e.target === e.currentTarget
    },
    onClick: (e) => {
      const pressAndReleaseOnBackdrop = pressedBackdrop.current
      pressedBackdrop.current = false
      if (pressAndReleaseOnBackdrop && e.target === e.currentTarget) onDismiss()
    },
  }
}
