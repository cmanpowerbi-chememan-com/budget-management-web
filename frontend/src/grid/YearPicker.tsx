export interface YearPickerProps {
  year: number
  onChange: (year: number) => void
}

const WINDOW_BEFORE = 1
const WINDOW_AFTER = 2

/** Planning-year picker — `year` is the Pending layer's year (Y+1); SAP and
 * Approved both show the standing year (Y = year-1), per the backend's
 * `year` param contract (`read_model.get_budget_grid`). A small window
 * around "now" covers the realistic range; the currently selected year is
 * always included even if a deep-link or stale state points outside it. */
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
      aria-label="ปีงบประมาณ (Pending)"
    >
      {[...years]
        .sort((a, b) => a - b)
        .map((y) => (
          <option key={y} value={y}>
            Year {y}
          </option>
        ))}
    </select>
  )
}
