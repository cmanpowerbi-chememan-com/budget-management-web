"""One-off read-only: find fillers whose Fill-scope CCs collectively cover all
6 special GL groups (for spot-testing every subform). Sources mirror the app:
board_budget + pending_budget (Fabric) + gold.fact_gl_trans (SAP read-through).
Run: venv/Scripts/python.exe setup/find_filler_all_special_groups.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.db import get_fabric_conn, get_gold_conn  # noqa: E402

SPECIAL = {
    "Entertainment",
    "Lease & Rental",
    "Professional & Legal Fee",
    "Public Relation & Donation",
    "Training & Seminar",
    "Travelling Expense",
}
BOARD_FY, SAP_FY = 2026, 2026  # same standing-year view the app shows

with get_fabric_conn() as conn:
    cur = conn.cursor()
    cur.execute("SELECT gl_code, gl_group FROM dbo.gl_group WHERE gl_group IN ({})".format(
        ",".join("?" * len(SPECIAL))), *SPECIAL)
    group_by_gl = {r[0]: r[1] for r in cur.fetchall()}
    print(f"special GL codes in master: {len(group_by_gl)}")

    cur.execute("SELECT DISTINCT filler_email, cost_center FROM dbo.cc_filler_map WHERE filler_email IS NOT NULL")
    filler_rows = cur.fetchall()

    cur.execute("SELECT DISTINCT cost_center, gl_account FROM dbo.board_budget WHERE fiscal_year = ?", BOARD_FY)
    board_rows = cur.fetchall()

    cur.execute("SELECT DISTINCT cost_center, gl_account FROM budget.pending_budget")
    pending_rows = cur.fetchall()

with get_gold_conn() as conn:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT cost_center, gl_account_number FROM gold.fact_gl_trans WHERE fiscal_year = ?", SAP_FY)
    sap_rows = cur.fetchall()

# CC -> set of special groups with ANY data
coverage: dict[str, set] = {}
for cc, gl in list(board_rows) + list(pending_rows) + list(sap_rows):
    g = group_by_gl.get(gl)
    if g:
        coverage.setdefault(cc, set()).add(g)

# filler -> union of groups across their CCs
by_filler: dict[str, set] = {}
ccs_by_filler: dict[str, set] = {}
for email, cc in filler_rows:
    ccs_by_filler.setdefault(email.lower(), set()).add(cc)
    by_filler.setdefault(email.lower(), set()).update(coverage.get(cc, set()))

ranked = sorted(by_filler.items(), key=lambda kv: (-len(kv[1]), kv[0]))
print(f"\nfillers: {len(ranked)} | CCs with any special-group data: {len(coverage)}\n")
for email, groups in ranked[:10]:
    mark = "  <-- ALL 6" if len(groups) == len(SPECIAL) else ""
    print(f"{len(groups)}/6  {email}  CCs={sorted(ccs_by_filler[email])}{mark}")
    if len(groups) < len(SPECIAL):
        print(f"      missing: {sorted(SPECIAL - groups)}")

for target in ("passakornh@chememan.com",):
    groups = by_filler.get(target, set())
    print(f"\n{target}: {len(groups)}/6 -> {sorted(groups)}")
    print(f"  missing: {sorted(SPECIAL - groups)}  CCs={sorted(ccs_by_filler.get(target, []))}")
