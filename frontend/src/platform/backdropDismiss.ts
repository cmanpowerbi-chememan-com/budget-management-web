import { useRef, type MouseEventHandler } from 'react'

export interface BackdropDismissHandlers {
  onMouseDown: MouseEventHandler<HTMLElement>
  onClick: MouseEventHandler<HTMLElement>
}

/** Guards a `.modal-backdrop`'s dismiss-on-click against the drag-release
 * misclick (jakkaritw, prd report 2026-09-24): a naive
 * `onClick={(e) => e.target === e.currentTarget && onDismiss()}` also fires
 * when the user presses the mouse INSIDE the modal (e.g. drag-selecting text
 * in an input) and releases over the dim backdrop — the browser dispatches
 * `click` on the nearest common ancestor of the mousedown/mouseup targets,
 * which is the backdrop itself, so `target === currentTarget` passes even
 * though the user never intended to dismiss anything. Same bug in reverse
 * (press on the backdrop, release inside the modal) also satisfies that
 * check. Every caller of this hook used to lose typed data this way.
 *
 * Fix: remember on `mousedown` whether the PRESS itself started on the
 * backdrop; a `click` only dismisses when BOTH the press and the click
 * landed on the backdrop, with nothing in between. An ordinary click (press
 * and release on the same spot, no drag) always satisfies this, so normal
 * backdrop-dismiss is unchanged — only the drag-across-the-edge case is
 * blocked. The flag resets after every click so a later, genuine backdrop
 * click still works. */
export function useBackdropDismiss(onDismiss: () => void): BackdropDismissHandlers {
  const pressedBackdrop = useRef(false)

  return {
    onMouseDown: (e) => {
      pressedBackdrop.current = e.target === e.currentTarget
    },
    onClick: (e) => {
      const pressStartedOnBackdrop = pressedBackdrop.current
      pressedBackdrop.current = false
      if (pressStartedOnBackdrop && e.target === e.currentTarget) onDismiss()
    },
  }
}
