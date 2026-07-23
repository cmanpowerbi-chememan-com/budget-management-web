/** Parses the ADR-0016 email deep-link query string
 * (`?dept=<url-encoded ฝ่าย>&year=<yyyy>`) into an initial filter state
 * for the main page. Convenience-only (ADR-0016): this never grants
 * access — it only pre-fills what the ฝ่าย/year picker (A8) would
 * otherwise ask the user to choose. The server always re-checks scope on
 * every request regardless of what this parses. Missing or invalid
 * params are ignored individually — never a crash, never a garbage
 * value.
 *
 * Year convention: the URL's `year` is the LABEL (standing) year — the
 * same year `YearPicker` DISPLAYS (`YearPicker.tsx`: label = value - 1).
 * `DeepLinkFilter.year` is the PLANNING year (label + 1), matching what
 * `BudgetGrid` feeds straight into `initialFilter.year`/the `GET /budget`
 * `year` param (already the planning year, no downstream change needed).
 * This keeps a hand-typed/hand-shared `?year=<label>` landing on the
 * SAME grid view as picking the dropdown option labelled "Year <label>".
 * Inverse of `backend/app/notifications.py` `build_deep_link`, which
 * emits `year=<planning - 1>` for the same reason. */

export interface DeepLinkFilter {
  dept: string | null
  year: number | null
}

const YEAR_PATTERN = /^\d{4}$/
// Fiscal years realistically referenced by a deep-link cluster around
// "now" (current + next planning year, or a recent past year still
// under approval) — 5 years either side is generous without accepting
// obvious garbage like year=9999.
const YEAR_WINDOW_YEARS = 5

function parseYear(raw: string | null): number | null {
  if (raw === null) return null

  const trimmed = raw.trim()
  if (!YEAR_PATTERN.test(trimmed)) return null

  // `labelYear` is what the URL carries (matches the YearPicker's
  // displayed label). The sane window is validated against this raw
  // label value, unchanged from before this fix — only the RETURN value
  // below changes (label -> planning).
  const labelYear = Number(trimmed)
  const currentYear = new Date().getFullYear()
  if (labelYear < currentYear - YEAR_WINDOW_YEARS || labelYear > currentYear + YEAR_WINDOW_YEARS) {
    return null
  }

  return labelYear + 1
}

function parseDept(raw: string | null): string | null {
  if (raw === null) return null

  const trimmed = raw.trim()
  return trimmed.length > 0 ? trimmed : null
}

export function parseDeepLink(search: string): DeepLinkFilter {
  const params = new URLSearchParams(search)

  return {
    dept: parseDept(params.get('dept')),
    year: parseYear(params.get('year')),
  }
}
