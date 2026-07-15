export interface AdminModeToggleProps {
  enabled: boolean
  onChange: (next: boolean) => void
}

/** ADR-0014 "โหมด Admin" switch — shown only for a DUAL-ROLE admin (is_admin
 * AND some Fill/See scope); the caller decides when to render this at all.
 * OFF = base role (own ฝ่าย + รออนุมัติ queue + Approve/Reject). ON = admin
 * hat (sees every ฝ่าย, edit any CC, orphan/override Submit) — Approve/Reject
 * is hidden while this is on (administering ≠ approving). */
export function AdminModeToggle({ enabled, onChange }: AdminModeToggleProps) {
  return (
    <label
      className="admin-toggle"
      data-testid="admin-mode-toggle"
      title="สลับหมวก: ปกติ (ผู้กรอก/ผู้อนุมัติ) ↔ โหมด Admin (เห็นทุกฝ่าย, แก้ได้ทุก CC)"
    >
      <input
        type="checkbox"
        checked={enabled}
        onChange={(e) => onChange(e.target.checked)}
        data-testid="admin-mode-checkbox"
      />
      <span className="admin-toggle-sw" aria-hidden="true" />
      <span>โหมด Admin</span>
    </label>
  )
}
