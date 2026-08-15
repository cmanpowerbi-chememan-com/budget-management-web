import { useEffect, useState } from 'react'

type StorageKind = 'local' | 'session'

function resolveStorage(kind: StorageKind): Storage | undefined {
  if (typeof window === 'undefined') return undefined
  return kind === 'local' ? window.localStorage : window.sessionStorage
}

/** Shared persisted-state guard (ARCH-b): built for the "read once at mount,
 * persist on change" shape common to any sessionStorage/localStorage toggle
 * — a uniform `typeof window` + try/catch guard instead of an independently
 * drifting copy per caller. `decode`/`encode` keep each caller's exact
 * on-disk string representation (nothing here assumes booleans); pass
 * module-level named functions (not inline arrows) so their identity stays
 * stable across renders.
 * Sole consumer since the 2026-08-15 dark-mode removal:
 * `admin/useAdminViewToggle.ts`. (Originally shared with the theme toggle,
 * localStorage `'light'|'dark'` — deleted along with `ThemeToggle` when the
 * app moved to one theme only; kept as a generic hook rather than inlined
 * back into useAdminViewToggle since the seam costs nothing and a future
 * persisted toggle can reuse it.) */
export function usePersistedState<T>(
  key: string,
  kind: StorageKind,
  fallback: T,
  decode: (raw: string | null) => T,
  encode: (value: T) => string,
): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => {
    const storage = resolveStorage(kind)
    if (!storage) return fallback
    try {
      return decode(storage.getItem(key))
    } catch {
      return fallback
    }
  })

  useEffect(() => {
    const storage = resolveStorage(kind)
    if (!storage) return
    try {
      storage.setItem(key, encode(value))
    } catch {
      // storage unavailable (private mode / quota) — value still works for this render
    }
  }, [key, kind, value, encode])

  return [value, setValue]
}
