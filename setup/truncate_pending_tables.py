"""One-off: TRUNCATE the 3 transactional budget tables (user-confirmed 2026-07-20).
Reuses the backend's own connection (token auth via backend/.env) — no credential
handling here. Order: detail lines + trips first, then pending_budget (no FKs).
Run from repo root: python setup/truncate_pending_tables.py
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.db import get_fabric_conn  # noqa: E402

TABLES = ["budget.pending_budget_detail", "budget.budget_trip", "budget.pending_budget"]

parser = argparse.ArgumentParser()
parser.add_argument("--yes", action="store_true", help="actually TRUNCATE (default is dry run)")
args = parser.parse_args()

with get_fabric_conn() as conn:
    cur = conn.cursor()
    for t in TABLES:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"before  {t}: {cur.fetchone()[0]} rows")
    if not args.yes:
        print("DRY RUN — pass --yes to actually TRUNCATE")
        sys.exit(0)
    for t in TABLES:
        cur.execute(f"TRUNCATE TABLE {t}")
        print(f"truncated {t}")
    conn.commit()
    for t in TABLES:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"after   {t}: {cur.fetchone()[0]} rows")
print("done")
