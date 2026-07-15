import { useEffect, useState } from 'react'

const STORAGE_KEY = 'budget-admin-view-enabled'

function readStored(): boolean {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

/** ADR-0014 admin mode toggle, persisted in sessionStorage (survives a
 * reload within the same tab session, resets on a fresh session — matching
 * the ADR's "deliberate switch, not a permanent identity change"). Only
 * meaningful for a DUAL-ROLE admin (is_admin AND some Fill/See scope) — a
 * pure admin is always on with no toggle (A8, unchanged), a non-admin is
 * always off. The caller decides which case applies; this hook just owns
 * the on/off bit + its persistence. */
export function useAdminViewToggle(): [boolean, (next: boolean) => void] {
  const [enabled, setEnabledState] = useState<boolean>(readStored)

  useEffect(() => {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, String(enabled))
    } catch {
      // sessionStorage unavailable (private mode, etc.) — the toggle still
      // works for the current render, it just won't persist.
    }
  }, [enabled])

  return [enabled, setEnabledState]
}
