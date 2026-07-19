import { describe, expect, it } from 'vitest'
import type { DepartmentRow } from '../api/types'
import { buildDeptHierarchy, flattenDepartments, matchesQuery, resolveInitialDept } from './model'

const ROWS: DepartmentRow[] = [
  { cost_center: '10IT012000', department: 'Solution Delivery', division: 'Digital Technology Division', c_level: 'CTO' },
  { cost_center: '10IT012001', department: 'Solution Delivery', division: 'Digital Technology Division', c_level: 'CTO' },
  { cost_center: '10AC020000', department: 'Budgeting and Management Accounting', division: 'Budgeting and Cost Accounting Division', c_level: 'CFO' },
]

describe('buildDeptHierarchy', () => {
  it('groups Cost Centers under their ฝ่าย (department), deduped', () => {
    const tree = buildDeptHierarchy(ROWS)
    const solutionDelivery = flattenDepartments(tree).find((d) => d.department === 'Solution Delivery')
    expect(solutionDelivery?.costCenters).toEqual(['10IT012000', '10IT012001'])
  })

  it('groups ฝ่าย under their สายงาน (division)', () => {
    const tree = buildDeptHierarchy(ROWS)
    expect(tree.map((d) => d.division)).toEqual(
      ['Budgeting and Cost Accounting Division', 'Digital Technology Division'].sort((a, b) => a.localeCompare(b, 'th')),
    )
  })

  it('sorts divisions and departments alphabetically', () => {
    const tree = buildDeptHierarchy(ROWS)
    const divisionNames = tree.map((d) => d.division)
    expect(divisionNames).toEqual([...divisionNames].sort((a, b) => a.localeCompare(b, 'th')))
  })

  it('never crashes on a blank department/division — buckets under a visible placeholder', () => {
    const tree = buildDeptHierarchy([{ cost_center: 'CCX', department: null, division: null, c_level: null }])
    expect(tree).toHaveLength(1)
    expect(tree[0].departments[0].costCenters).toEqual(['CCX'])
  })

  it('returns an empty hierarchy for an empty scope (no crash, no placeholder division)', () => {
    expect(buildDeptHierarchy([])).toEqual([])
  })
})

describe('flattenDepartments', () => {
  it('gives a CC count via costCenters.length for the ฝ่าย picker badge', () => {
    const tree = buildDeptHierarchy(ROWS)
    const flat = flattenDepartments(tree)
    const solutionDelivery = flat.find((d) => d.department === 'Solution Delivery')
    expect(solutionDelivery?.costCenters.length).toBe(2)
  })
})

describe('matchesQuery', () => {
  const node = { department: 'Solution Delivery', division: 'Digital Technology Division', costCenters: ['CC1'] }

  it('matches on department name, case-insensitive', () => {
    expect(matchesQuery(node, 'solution')).toBe(true)
  })
  it('matches on division name too', () => {
    expect(matchesQuery(node, 'digital')).toBe(true)
  })
  it('does not match an unrelated query', () => {
    expect(matchesQuery(node, 'zzz')).toBe(false)
  })
  it('matches everything for an empty query', () => {
    expect(matchesQuery(node, '')).toBe(true)
  })
})

describe('resolveInitialDept — ADR-0016 deep-link + single-ฝ่าย auto-select', () => {
  const multiDeptTree = buildDeptHierarchy(ROWS) // 2 ฝ่าย across 2 สายงาน
  const singleDeptTree = buildDeptHierarchy(ROWS.filter((r) => r.department === 'Solution Delivery')) // 1 ฝ่าย

  it('returns the deep-link department when it exists in scope, even with >1 ฝ่าย present', () => {
    expect(resolveInitialDept(multiDeptTree, 'Solution Delivery')).toBe('Solution Delivery')
  })

  it('returns null for a department outside the caller\'s scope when >1 ฝ่าย remain (never grants access, never guesses)', () => {
    expect(resolveInitialDept(multiDeptTree, 'Some Other Department')).toBeNull()
  })

  it('returns null when there is no deep-link and >1 ฝ่าย in scope — user must consciously choose', () => {
    expect(resolveInitialDept(multiDeptTree, null)).toBeNull()
  })

  it('auto-selects the single ฝ่าย when there is no deep-link and exactly 1 ฝ่าย in scope', () => {
    expect(resolveInitialDept(singleDeptTree, null)).toBe('Solution Delivery')
  })

  it('auto-selects the single ฝ่าย even when the deep-link is invalid/out-of-scope', () => {
    expect(resolveInitialDept(singleDeptTree, 'Some Other Department')).toBe('Solution Delivery')
  })

  it('returns null for an empty scope (0 ฝ่าย), regardless of deep-link', () => {
    expect(resolveInitialDept([], null)).toBeNull()
    expect(resolveInitialDept([], 'Solution Delivery')).toBeNull()
  })
})
