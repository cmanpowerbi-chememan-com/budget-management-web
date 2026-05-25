"""MERGE logic tests for composite PK 2 cols.

This is the CRITICAL verification for skill v2: SQL must include
BOTH PK columns in:
  - ON clause of MERGE
  - WHERE clause of DELETE
  - Existence check before MERGE

Skill v1 (single primary_key) would fail these tests.
"""
import re
from pathlib import Path

SQL_DIR = Path(__file__).parent.parent / "sql"


def _read(filename: str) -> str:
    return (SQL_DIR / filename).read_text(encoding="utf-8")


# ───────────────────────────────────────────────────────────
# 03_merge_upsert.sql — composite PK MERGE
# ───────────────────────────────────────────────────────────
class TestCompositeMerge:

    @classmethod
    def setup_class(cls):
        cls.sql = _read("03_merge_upsert.sql")

    def test_uses_select_distinct(self):
        """Locked decision #3 — dedup source before MERGE."""
        assert "SELECT DISTINCT" in self.sql.upper()

    def test_on_clause_has_both_pk_columns(self):
        """⚠️ CRITICAL: ON must include BOTH cost_center AND orgcode.
        
        Single-column ON would throw DELTA_MULTIPLE_SOURCE_ROW_MATCHING
        when multiple rows share the same cost_center.
        """
        # Extract the ON clause text (between ON and WHEN)
        match = re.search(
            r"ON\s+(.+?)WHEN",
            self.sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match, "Could not find ON clause"
        on_clause = match.group(1)

        assert "cost_center" in on_clause, "ON clause missing cost_center"
        assert "orgcode"     in on_clause, "ON clause missing orgcode"
        assert re.search(r"\bAND\b", on_clause, re.IGNORECASE), (
            "ON clause must use AND between PK columns"
        )

    def test_no_when_matched_clause(self):
        """Junction table has no non-PK columns — no UPDATE branch needed."""
        assert not re.search(
            r"WHEN\s+MATCHED\s+THEN\s+UPDATE",
            self.sql,
            re.IGNORECASE,
        ), "Junction table should not have WHEN MATCHED UPDATE clause"

    def test_when_not_matched_inserts_both_columns(self):
        match = re.search(
            r"INSERT\s*\(([^)]+)\)",
            self.sql,
            re.IGNORECASE,
        )
        assert match
        cols = match.group(1).lower()
        assert "cost_center" in cols and "orgcode" in cols


# ───────────────────────────────────────────────────────────
# 01_create_tables.sql — composite PRIMARY KEY constraint
# ───────────────────────────────────────────────────────────
class TestCreateTables:

    @classmethod
    def setup_class(cls):
        cls.sql = _read("01_create_tables.sql")

    def test_has_audit_disabled_warning(self):
        assert "AUDIT DISABLED BY DESIGN" in self.sql

    def test_no_audit_columns(self):
        forbidden = ["created_at", "created_by", "updated_at", "updated_by"]
        for col in forbidden:
            assert col not in self.sql.lower()

    def test_no_is_active_flag(self):
        """Locked decision #6 — hard delete, no soft delete flag."""
        assert "is_active" not in self.sql.lower()

    def test_primary_key_is_composite(self):
        """⚠️ CRITICAL: PK must reference BOTH columns."""
        match = re.search(
            r"PRIMARY\s+KEY\s*\(([^)]+)\)",
            self.sql,
            re.IGNORECASE,
        )
        assert match, "PRIMARY KEY clause not found"
        pk_cols = match.group(1).lower()
        assert "cost_center" in pk_cols, "PK missing cost_center"
        assert "orgcode"     in pk_cols, "PK missing orgcode"
        # Must have comma (composite, not single)
        assert "," in pk_cols, (
            "Composite PK must list multiple columns separated by comma"
        )

    def test_cost_center_format_check(self):
        """Mirrors HTML regex /[^0-9A-Za-z]/g + uppercase."""
        assert re.search(
            r"CHECK\s*\(\s*cost_center\s+RLIKE",
            self.sql,
            re.IGNORECASE,
        )


# ───────────────────────────────────────────────────────────
# 04_hard_delete.sql — WHERE must use BOTH PK columns
# ───────────────────────────────────────────────────────────
class TestHardDelete:

    @classmethod
    def setup_class(cls):
        cls.sql = _read("04_hard_delete.sql")

    def test_uses_delete_not_update(self):
        """Locked decision #22 — hard delete."""
        assert re.search(r"\bDELETE\s+FROM\b", self.sql, re.IGNORECASE)
        assert not re.search(r"UPDATE.*SET", self.sql, re.IGNORECASE)

    def test_where_includes_both_pk_columns(self):
        """⚠️ CATASTROPHIC if missing: deleting by single PK column
        would wipe ALL Orgcodes of that Cost Center.
        """
        match = re.search(
            r"WHERE\s+(.+?)$",
            self.sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match
        where_clause = match.group(1).lower()
        assert "cost_center" in where_clause
        assert "orgcode" in where_clause
        assert re.search(r"\band\b", where_clause), (
            "WHERE for composite PK delete must use AND"
        )
