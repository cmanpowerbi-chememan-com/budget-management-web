import { describe, expect, it } from 'vitest'
import { parseDeepLink } from './deepLink'

describe('parseDeepLink (ADR-0016 email deep-link)', () => {
  it('parses a valid dept + year pair (URL carries the LABEL year, returns planning = label + 1)', () => {
    const currentYear = new Date().getFullYear()
    expect(parseDeepLink(`?dept=ฝ่ายบัญชี&year=${currentYear}`)).toEqual({
      dept: 'ฝ่ายบัญชี',
      year: currentYear + 1,
    })
  })

  it('decodes a URL-encoded Thai dept name, including an encoded slash', () => {
    const encoded = encodeURIComponent('ฝ่ายบัญชี/การเงิน')
    expect(parseDeepLink(`?dept=${encoded}&year=2026`).dept).toBe('ฝ่ายบัญชี/การเงิน')
  })

  it('ignores a missing year but keeps a valid dept', () => {
    expect(parseDeepLink('?dept=ฝ่ายขาย')).toEqual({ dept: 'ฝ่ายขาย', year: null })
  })

  it('ignores a missing dept but keeps a valid year (returns planning = label + 1)', () => {
    const currentYear = new Date().getFullYear()
    expect(parseDeepLink(`?year=${currentYear}`)).toEqual({ dept: null, year: currentYear + 1 })
  })

  it('ignores a non-4-digit year without crashing', () => {
    expect(parseDeepLink('?year=202').year).toBeNull()
    expect(parseDeepLink('?year=20266').year).toBeNull()
  })

  it('ignores a non-numeric year without crashing', () => {
    expect(parseDeepLink('?year=abcd').year).toBeNull()
  })

  it('ignores a 4-digit year outside the sane window', () => {
    const farFuture = new Date().getFullYear() + 50
    expect(parseDeepLink(`?year=${farFuture}`).year).toBeNull()
  })

  it('accepts the label year exactly at the lower boundary of the ±5-year window (returns label + 1)', () => {
    const lowerBoundary = new Date().getFullYear() - 5
    expect(parseDeepLink(`?year=${lowerBoundary}`).year).toBe(lowerBoundary + 1)
  })

  it('accepts the label year exactly at the upper boundary of the ±5-year window (returns label + 1)', () => {
    const upperBoundary = new Date().getFullYear() + 5
    expect(parseDeepLink(`?year=${upperBoundary}`).year).toBe(upperBoundary + 1)
  })

  it('rejects the year one below the ±5-year window', () => {
    const belowWindow = new Date().getFullYear() - 6
    expect(parseDeepLink(`?year=${belowWindow}`).year).toBeNull()
  })

  it('rejects the year one above the ±5-year window', () => {
    const aboveWindow = new Date().getFullYear() + 6
    expect(parseDeepLink(`?year=${aboveWindow}`).year).toBeNull()
  })

  it('ignores a blank/whitespace-only dept', () => {
    expect(parseDeepLink('?dept=%20%20&year=2026').dept).toBeNull()
  })

  it('returns both null with no query string at all', () => {
    expect(parseDeepLink('')).toEqual({ dept: null, year: null })
  })

  it('round-trips with the YearPicker label convention: URL label 2026 -> planning 2027', () => {
    expect(parseDeepLink('?year=2026').year).toBe(2027)
  })
})
