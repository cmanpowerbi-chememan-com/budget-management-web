import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api/client'
import { fetchBudgetGrid, fetchDepartments, fetchGlAccounts, saveRow } from '../api/budget'
import type { BudgetRow, DepartmentRow, GlAccount } from '../api/types'
import type { ScopeState } from '../auth/useScope'
import type { DeepLinkFilter } from '../filters/deepLink'
import { AddTransactionForm, type AddResult } from './AddTransactionForm'
import { GridTable, type RowMessage } from './GridTable'
import { buildNewRowPayload, buildSavePayload, mergeSavedRow, type MonthKey } from './model'
import { DeptPicker } from '../picker/DeptPicker'
import { buildDeptHierarchy, resolveInitialDept } from '../picker/model'
import { YearPicker } from './YearPicker'

export interface BudgetGridProps {
  scope: ScopeState
  initialFilter: DeepLinkFilter
}

function rowKey(cc: string, gl: string): string {
  return `${cc}|${gl}`
}

function defaultPlanningYear(): number {
  // Pending layer is the NEXT fiscal year relative to "now" (planning
  // year Y+1, per read_model.get_budget_grid's `year` param contract).
  return new Date().getFullYear() + 1
}

/** Main budget grid (A8) — ฝ่าย + year pickers, 3-layer grid, inline
 * Pending-cell editing with per-row save/conflict handling, and
 * "+ เพิ่ม transaction". Owns all API calls for this page; `GridTable`/
 * `DeptPicker`/`AddTransactionForm` are pure presentational children. */
export function BudgetGrid({ scope, initialFilter }: BudgetGridProps) {
  const [year, setYear] = useState<number>(initialFilter.year ?? defaultPlanningYear())
  const [department, setDepartment] = useState<string | null>(null)
  const [deptResolved, setDeptResolved] = useState(false)

  const [departments, setDepartments] = useState<DepartmentRow[]>([])
  const [glRef, setGlRef] = useState<GlAccount[]>([])
  const [rows, setRows] = useState<BudgetRow[]>([])
  const [rowMessages, setRowMessages] = useState<Record<string, RowMessage>>({})

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Pure admins (ADR-0014: no base actor role, so no toggle — always
  // admin-wide) vs dual-role overlay admins (toggle deferred to A10, so
  // they stay scoped like a normal user in A8). See final report for the
  // full rationale.
  const isPureAdmin = scope.isAdmin && scope.fillCostCenters.length === 0 && scope.seeCostCenters.length === 0

  // Reference data (GL master + department hierarchy) loads once. The
  // deep-link ฝ่าย (ADR-0016) is only applied once, the first time the
  // real hierarchy arrives — it must be validated against the caller's
  // ACTUAL scope, never taken on faith (convenience-only, never a bearer
  // of access).
  useEffect(() => {
    fetchGlAccounts().then(setGlRef).catch(() => setGlRef([]))
    fetchDepartments(isPureAdmin)
      .then((data) => {
        setDepartments(data)
        if (!deptResolved) {
          setDepartment(resolveInitialDept(buildDeptHierarchy(data), initialFilter.dept))
          setDeptResolved(true)
        }
      })
      .catch(() => setDepartments([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function loadGrid() {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchBudgetGrid({ year, department: department ?? undefined, adminViewEnabled: isPureAdmin })
      setRows(data)
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'โหลดข้อมูลไม่สำเร็จ กรุณาลองใหม่อีกครั้ง'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadGrid()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, department])

  const fillCostCenters = useMemo(
    () => (isPureAdmin ? [...new Set(departments.map((d) => d.cost_center))] : scope.fillCostCenters),
    [isPureAdmin, departments, scope.fillCostCenters],
  )

  async function handleCommitMonth(row: BudgetRow, month: MonthKey, value: number) {
    const key = rowKey(row.cost_center, row.gl_account)
    const optimistic = { ...row, pending: { ...row.pending, [month]: value } }
    optimistic.pending.total_year = Object.keys(optimistic.pending)
      .filter((k) => /^m\d\d$/.test(k))
      .reduce((sum, k) => sum + (optimistic.pending as unknown as Record<string, number>)[k], 0)
    setRows((prev) => prev.map((r) => (rowKey(r.cost_center, r.gl_account) === key ? optimistic : r)))
    setRowMessages((prev) => ({ ...prev, [key]: { kind: 'saving', text: 'กำลังบันทึก…' } }))

    try {
      const payload = buildSavePayload(optimistic, year)
      const saved = await saveRow(payload)
      setRows((prev) => prev.map((r) => (rowKey(r.cost_center, r.gl_account) === key ? mergeSavedRow(r, saved) : r)))
      setRowMessages((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setRowMessages((prev) => ({
          ...prev,
          [key]: { kind: 'error', text: 'ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น กรุณาโหลดข้อมูลใหม่แล้วลองอีกครั้ง' },
        }))
        await loadGrid()
        return
      }
      const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'บันทึกไม่สำเร็จ'
      setRowMessages((prev) => ({ ...prev, [key]: { kind: 'error', text: message } }))
    }
  }

  async function handleAddTransaction(costCenter: string, glAccount: string): Promise<AddResult> {
    try {
      const saved = await saveRow(buildNewRowPayload(costCenter, glAccount, year))
      const months = Object.fromEntries(
        (['m01', 'm02', 'm03', 'm04', 'm05', 'm06', 'm07', 'm08', 'm09', 'm10', 'm11', 'm12'] as MonthKey[]).map((m) => [
          m,
          saved[m],
        ]),
      )
      const blankLayer = { ...months, total_year: 0 }
      const newRow: BudgetRow = {
        cost_center: costCenter,
        gl_account: glAccount,
        sap: blankLayer as BudgetRow['sap'],
        board: { ...blankLayer, gl_name: null, gl_group: null, c_level: null, division: null, department: null } as BudgetRow['board'],
        pending: {
          ...months,
          total_year: saved.total_year,
          template: saved.template,
          remark: saved.remark,
          gl_name: saved.gl_name,
          gl_group: saved.gl_group,
          c_level: saved.c_level,
          division: saved.division,
          department: saved.department,
          updated_at: saved.updated_at,
        } as BudgetRow['pending'],
        editable: true,
      }
      setRows((prev) => [...prev, newRow])
      return { ok: true }
    } catch (err) {
      const message = err instanceof ApiError ? `${err.message}${err.detail ? ` (${err.detail})` : ''}` : 'สร้างรายการไม่สำเร็จ'
      return { ok: false, errorTh: message }
    }
  }

  return (
    <div className="budget-grid">
      <div className="grid-toolbar">
        <YearPicker year={year} onChange={setYear} />
        <DeptPicker rows={departments} selected={department} onSelect={setDepartment} />
        <AddTransactionForm
          fillCostCenters={fillCostCenters}
          glRef={glRef}
          existingRows={rows}
          onAdd={handleAddTransaction}
        />
      </div>

      {error && (
        <div className="grid-error" role="alert">
          <span>{error}</span>
          <button type="button" className="btn" onClick={loadGrid}>
            ลองใหม่
          </button>
        </div>
      )}

      {loading && !error && <div className="grid-loading">กำลังโหลดข้อมูลงบประมาณ…</div>}

      {!loading && !error && (
        <GridTable rows={rows} glRef={glRef} onCommitMonth={handleCommitMonth} rowMessages={rowMessages} />
      )}
    </div>
  )
}
