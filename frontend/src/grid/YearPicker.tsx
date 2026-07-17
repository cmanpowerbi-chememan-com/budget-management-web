export interface YearPickerProps {
  year: number
  onChange: (year: number) => void
}

const WINDOW_BEFORE = 1
const WINDOW_AFTER = 2

/** Planning-year picker — `year` prop/state/API param is the Pending layer's
 * year (Y+1), unchanged contract with the backend (`read_model.get_budget_grid`,
 * `board_year = planning_year - 1`). The DISPLAYED label shows the standing
 * year Y (= year-1) instead, matching mockup `0002.3budget-export.html`'s
 * semantic: SAP/Approved(Y) + Pending(Y+1) all read as "Year Y". Option
 * `value` stays the planning year so `onChange`/state/API calls never change.
 * A small window around "now" covers the realistic range; the currently
 * selected year is always included even if a deep-link or stale state points
 * outside it. */
export function YearPicker({ year, onChange }: YearPickerProps) {
  const currentYear = new Date().getFullYear()
  const years = new Set<number>()
  for (let y = currentYear - WINDOW_BEFORE; y <= currentYear + WINDOW_AFTER; y++) years.add(y)
  years.add(year)

  return (
    <select
      className="year-select"
      value={String(year)}
      onChange={(e) => onChange(Number(e.target.value))}
      aria-label="ปีฐาน (SAP/Approved · Pending = ปีถัดไป)"
    >
      {[...years]
        .sort((a, b) => a - b)
        .map((y) => (
          <option key={y} value={y}>
            Year {y - 1}
          </option>
        ))}
    </select>
  )
}
