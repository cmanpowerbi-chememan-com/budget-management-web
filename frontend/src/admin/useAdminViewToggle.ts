import { usePersistedState } from '../platform/usePersistedToggle'

const STORAGE_KEY = 'budget-admin-view-enabled'

function decodeEnabled(raw: string | null): boolean {
  return raw === 'true'
}

/** ADR-0014 admin mode toggle, persisted in sessionStorage (survives a
 * reload within the same tab session, resets on a fresh session — matching
 * the ADR's "deliberate switch, not a permanent identity change"). Only
 * meaningful for a DUAL-ROLE admin (is_admin AND some Fill/See scope) — a
 * pure admin is always on with no toggle (A8, unchanged), a non-admin is
 * always off. The caller decides which case applies; this hook just owns
 * the on/off bit + its persistence (guard shared with the theme toggle via
 * platform/usePersistedToggle, ARCH-b). */
export function useAdminViewToggle(): [boolean, (next: boolean) => void] {
  return usePersistedState<boolean>(STORAGE_KEY, 'session', false, decodeEnabled, String)
}
