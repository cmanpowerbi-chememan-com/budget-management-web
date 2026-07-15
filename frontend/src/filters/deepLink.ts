/** Parses the ADR-0016 email deep-link query string
 * (`?dept=<url-encoded ฝ่าย>&year=<yyyy>`) into an initial filter state
 * for the main page. Convenience-only (ADR-0016): this never grants
 * access — it only pre-fills what the ฝ่าย/year picker (A8) would
 * otherwise ask the user to choose. The server always re-checks scope on
 * every request regardless of what this parses. Missing or invalid
 * params are ignored individually — never a crash, never a garbage
 * value. */

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

  const year = Number(trimmed)
  const currentYear = new Date().getFullYear()
  if (year < currentYear - YEAR_WINDOW_YEARS || year > currentYear + YEAR_WINDOW_YEARS) {
    return null
  }

  return year
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
