/** Parity check: this file's Entertainment/Lease & Rental constants MUST
 * match `docs/reference/special-gl-dropdown-fixture.json` exactly — the SAME
 * fixture `backend/tests/test_special_gl_fixture_parity.py` checks against
 * `app.special_gl`'s hardcoded sets. A drift on either side fails here. */
import { describe, expect, it } from 'vitest'
import fixture from '../../../docs/reference/special-gl-dropdown-fixture.json'
import {
  ENTERTAINMENT_EXTERNAL_GLS,
  ENTERTAINMENT_EXTERNAL_VALUES,
  ENTERTAINMENT_INTERNAL_GLS,
  ENTERTAINMENT_INTERNAL_VALUES,
  LEASE_MACHINERY_SUFFIX,
  LEASE_MACHINERY_TYPES,
  LEASE_NONVEHICLE_SUFFIXES,
  LEASE_PLANTS,
  LEASE_PLATES,
  LEASE_VEHICLE_SUFFIX,
  LEASE_VEHICLE_TYPES,
  TRAVEL_GL_BY_TYPE_SIDE,
} from './glDropdownConstants'

function sortedSet(a: readonly string[]): string[] {
  return [...a].sort()
}

describe('glDropdownConstants parity with the shared fixture', () => {
  it('Entertainment GL sets + dropdown values match', () => {
    expect(sortedSet(ENTERTAINMENT_EXTERNAL_GLS)).toEqual(sortedSet(fixture.entertainment.external_gls))
    expect(sortedSet(ENTERTAINMENT_INTERNAL_GLS)).toEqual(sortedSet(fixture.entertainment.internal_gls))
    expect(sortedSet(ENTERTAINMENT_EXTERNAL_VALUES)).toEqual(sortedSet(fixture.entertainment.external_values))
    expect(sortedSet(ENTERTAINMENT_INTERNAL_VALUES)).toEqual(sortedSet(fixture.entertainment.internal_values))
  })

  it('Lease & Rental suffixes + dropdown values match', () => {
    expect(LEASE_VEHICLE_SUFFIX).toBe(fixture.lease_rental.vehicle_suffix)
    expect(LEASE_MACHINERY_SUFFIX).toBe(fixture.lease_rental.machinery_suffix)
    expect(sortedSet(LEASE_NONVEHICLE_SUFFIXES)).toEqual(sortedSet(fixture.lease_rental.nonvehicle_suffixes))
    expect(sortedSet(LEASE_VEHICLE_TYPES)).toEqual(sortedSet(fixture.lease_rental.vehicle_types))
    expect(sortedSet(LEASE_MACHINERY_TYPES)).toEqual(sortedSet(fixture.lease_rental.machinery_types))
    expect(sortedSet(LEASE_PLANTS)).toEqual(sortedSet(fixture.lease_rental.plants))
    expect(sortedSet(LEASE_PLATES)).toEqual(sortedSet(fixture.lease_rental.plates))
  })

  it('Travelling Expense GL-by-type-side map matches (never-cut: COST/SGA never cross)', () => {
    expect(TRAVEL_GL_BY_TYPE_SIDE).toEqual(fixture.travelling.gl_by_type_side)
  })
})
