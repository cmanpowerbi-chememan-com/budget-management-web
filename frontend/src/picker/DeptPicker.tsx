import { useMemo, useState } from 'react'
import type { DepartmentRow } from '../api/types'
import { buildDeptHierarchy, matchesQuery } from './model'

export interface DeptPickerProps {
  rows: DepartmentRow[]
  selected: string | null
  onSelect: (department: string) => void
}

/** ฝ่าย picker — สายงาน › ฝ่าย (count) › Cost Center (count) hierarchy,
 * locking the main grid to one (ฝ่าย, year) = the approval unit
 * (ADR-0008/0019). Mirrors the mockup's `.faip` component: a trigger
 * button opens a searchable panel grouped by division, each department row
 * showing its CC count. */
export function DeptPicker({ rows, selected, onSelect }: DeptPickerProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const divisions = useMemo(() => buildDeptHierarchy(rows), [rows])

  function pick(department: string) {
    onSelect(department)
    setOpen(false)
    setQuery('')
  }

  return (
    <div className="dept-picker">
      <button
        type="button"
        className="dept-picker-trigger"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {selected ?? '— เลือกฝ่าย —'}
      </button>
      {open && (
        <div className="dept-picker-panel">
          <input
            className="dept-picker-search"
            placeholder="ค้นหาฝ่าย…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <div className="dept-picker-list">
            {divisions.map((division) => {
              const visible = division.departments.filter((d) => matchesQuery(d, query))
              if (visible.length === 0) return null
              return (
                <div key={division.division} className="dept-picker-group">
                  <div className="dept-picker-group-head">
                    {division.division}
                    <span className="dept-picker-badge">{division.departments.length}</span>
                  </div>
                  {visible.map((dept) => (
                    <button
                      type="button"
                      key={dept.department}
                      className={`dept-picker-row${dept.department === selected ? ' selected' : ''}`}
                      onClick={() => pick(dept.department)}
                    >
                      <span className="dept-picker-name">{dept.department}</span>
                      <span className="dept-picker-cc-count">{dept.costCenters.length} CC</span>
                    </button>
                  ))}
                </div>
              )
            })}
            {divisions.every((d) => d.departments.filter((x) => matchesQuery(x, query)).length === 0) && (
              <div className="dept-picker-empty">ไม่พบฝ่ายในสิทธิ์ของคุณ</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
