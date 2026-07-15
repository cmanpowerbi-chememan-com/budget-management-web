/** Shared test-only fixture builders for the grid module's test suite
 * (model/GridTable/BudgetGrid/AddTransactionForm — 4+ call sites). Not
 * imported by any production code. */
import type { BudgetRow, LayerAmounts } from '../api/types'
import { MONTH_KEYS, type MonthKey } from './model'

export function blankLayer(overrides: Partial<Record<MonthKey | 'total_year', number>> = {}): LayerAmounts {
  const base = { total_year: 0 } as LayerAmounts
  MONTH_KEYS.forEach((m) => {
    ;(base as unknown as Record<MonthKey, number>)[m] = 0
  })
  return { ...base, ...overrides }
}

export function makeRow(overrides: Partial<BudgetRow> & { cost_center: string; gl_account: string }): BudgetRow {
  return {
    sap: blankLayer(),
    board: { ...blankLayer(), gl_name: null, gl_group: null, c_level: null, division: null, department: null },
    pending: {
      ...blankLayer(),
      template: null,
      remark: null,
      gl_name: null,
      gl_group: null,
      c_level: null,
      division: null,
      department: null,
      updated_at: null,
    },
    editable: false,
    ...overrides,
  }
}
