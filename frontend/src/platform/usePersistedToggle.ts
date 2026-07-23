import { useEffect, useState } from 'react'

type StorageKind = 'local' | 'session'

function resolveStorage(kind: StorageKind): Storage | undefined {
  if (typeof window === 'undefined') return undefined
  return kind === 'local' ? window.localStorage : window.sessionStorage
}

/** Shared persisted-state guard (ARCH-b): the theme toggle (localStorage,
 * `'light'|'dark'`) and the admin-view toggle (sessionStorage, boolean) are
 * the same "read once at mount, persist on change" shape — this hook gives
 * both one uniform `typeof window` + try/catch guard instead of two
 * independently drifting copies. `decode`/`encode` keep each caller's exact
 * on-disk string representation (nothing here assumes booleans); pass
 * module-level named functions (not inline arrows) so their identity stays
 * stable across renders. */
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
