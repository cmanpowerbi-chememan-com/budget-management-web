/** Shared test-only fixture builders for the grid module's test suite
 * (model/GridTable/BudgetGrid/AddTransactionForm — 4+ call sites). Not
 * imported by any production code. */
import type { BudgetRow, LayerAmounts, SapLayer } from '../api/types'
import { MONTH_KEYS, type MonthKey } from './model'

export function blankLayer(overrides: Partial<Record<MonthKey | 'total_year', number>> = {}): LayerAmounts {
  const base = { total_year: 0 } as LayerAmounts
  MONTH_KEYS.forEach((m) => {
    ;(base as unknown as Record<MonthKey, number>)[m] = 0
  })
  return { ...base, ...overrides }
}

/** SAP-layer fixture (ADR-0026): months may be `null` (a month the backend
 * hides), `total_year` defaults to the sum of the VISIBLE months and
 * `has_actuals` to "any month carries a value" — exactly how the backend
 * derives them, so fixtures can't drift from the real payload. */
export function sapLayer(
  overrides: Partial<Record<MonthKey, number | null>> & { total_year?: number; has_actuals?: boolean } = {},
): SapLayer {
  const valueOf = (m: MonthKey): number | null => (m in overrides ? (overrides[m] as number | null) : 0)
  const months = Object.fromEntries(MONTH_KEYS.map((m) => [m, valueOf(m)])) as Record<MonthKey, number | null>
  const values = MONTH_KEYS.map(valueOf)
  return {
    ...months,
    total_year: overrides.total_year ?? values.reduce((sum, v) => sum + (v ?? 0), 0),
    has_actuals: overrides.has_actuals ?? values.some((v) => v !== null && v !== 0),
  } as SapLayer
}

export function makeRow(overrides: Partial<BudgetRow> & { cost_center: string; gl_account: string }): BudgetRow {
  return {
    sap: sapLayer(),
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
