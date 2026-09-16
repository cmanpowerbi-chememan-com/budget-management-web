/** App-wide confirm dialog — replaces `window.confirm` everywhere (2026-09-16,
 * jakkaritw: the native dialog shows the container hostname above our Thai
 * text and that line cannot be removed). Same module-level pub/sub shape as
 * `notice.ts`: the callers (approval actions, delete buttons, cancel-unsaved)
 * live in unrelated trees, so a plain function call beats threading a
 * callback down from `App` or adding a provider every test would need to
 * wrap.
 *
 * Deliberately tiny: one dialog on screen at a time, no queue. A second
 * `confirmDialog()` call while one is still open resolves the FIRST as
 * `false` and shows the newer question — nothing in this app opens two
 * confirms back to back, so the simplest policy (newer wins, older reads as
 * cancelled) beats a real queue nobody needs yet. */
export interface ConfirmDialogOptions {
  /** Defaults to "ตกลง". */
  confirmLabel?: string
  /** Defaults to "ยกเลิก". */
  cancelLabel?: string
  /** Styles the confirm button as destructive (red fill) — pass for any
   * delete / discard-unsaved-changes action. */
  danger?: boolean
}

export interface ConfirmRequest {
  /** Guards `answerConfirm` against resolving a stale request (see the
   * pre-emption note above). */
  id: number
  message: string
  confirmLabel: string
  cancelLabel: string
  danger: boolean
}

type Listener = (request: ConfirmRequest | null) => void

const DEFAULT_CONFIRM_LABEL = 'ตกลง'
const DEFAULT_CANCEL_LABEL = 'ยกเลิก'

const listeners = new Set<Listener>()
let nextId = 0
let pending: { id: number; resolve: (value: boolean) => void } | null = null

/** Asks the user to confirm `message`. Resolves `true`/`false`. Falls back
 * to the native `window.confirm` when no `<ConfirmDialog />` host is
 * mounted — this is what keeps every existing component test (rendering,
 * say, `AttachmentsModal` alone and spying on `window.confirm`) passing
 * unchanged; only a full app render (with the host mounted at `App` root)
 * sees the in-app dialog. */
export function confirmDialog(message: string, opts: ConfirmDialogOptions = {}): Promise<boolean> {
  if (listeners.size === 0) {
    return Promise.resolve(window.confirm(message))
  }

  return new Promise<boolean>((resolve) => {
    if (pending) pending.resolve(false)

    const id = ++nextId
    pending = { id, resolve }
    const request: ConfirmRequest = {
      id,
      message,
      confirmLabel: opts.confirmLabel ?? DEFAULT_CONFIRM_LABEL,
      cancelLabel: opts.cancelLabel ?? DEFAULT_CANCEL_LABEL,
      danger: opts.danger ?? false,
    }
    for (const listener of listeners) listener(request)
  })
}

/** Subscribed by the mounted `<ConfirmDialog />` host; returns the
 * unsubscribe function (the shape `useEffect` wants back). */
export function subscribeConfirmRequests(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Called by the host once the user answers (OK / Cancel / Escape / backdrop
 * click). Guarded by `id` so a delayed answer for a request that was already
 * pre-empted by a newer one can never resolve the wrong promise. */
export function answerConfirm(id: number, value: boolean): void {
  if (!pending || pending.id !== id) return
  const { resolve } = pending
  pending = null
  resolve(value)
  for (const listener of listeners) listener(null)
}
