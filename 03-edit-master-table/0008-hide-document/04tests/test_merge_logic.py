"""SQL pattern tests for 3-column composite PK with range CHECKs.

This is the most stringent SQL verification:
  - PRIMARY KEY must list ALL 3 columns
  - ON clause of MERGE must have ALL 3 columns + 2 ANDs
  - WHERE clause of DELETE must have ALL 3 columns + 2 ANDs
  - CHECK constraints for year and month ranges
"""
import re
from pathlib import Path

SQL_DIR = Path(__file__).parent.parent / "sql"


def _read(filename: str) -> str:
    return (SQL_DIR / filename).read_text(encoding="utf-8")


# ───────────────────────────────────────────────────────────
# 03_merge_upsert.sql — 3-column composite MERGE
# ───────────────────────────────────────────────────────────
class TestCompositeMerge3Cols:

    @classmethod
    def setup_class(cls):
        cls.sql = _read("03_merge_upsert.sql")

    def test_uses_select_distinct(self):
        assert "SELECT DISTINCT" in self.sql.upper()

    def test_on_clause_has_all_three_pk_columns(self):
        """⚠️ CRITICAL: ON must include doc_num AND fiscal_year AND fiscal_month."""
        match = re.search(
            r"ON\s+(.+?)WHEN",
            self.sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match, "Could not find ON clause"
        on_clause = match.group(1).lower()

        assert "doc_num"      in on_clause
        assert "fiscal_year"  in on_clause
        assert "fiscal_month" in on_clause

        and_count = len(re.findall(r"\band\b", on_clause))
        assert and_count >= 2, (
            f"3-column composite ON must have at least 2 ANDs, got {and_count}"
        )

    def test_no_when_matched_clause(self):
        """All 3 columns are PK — nothing to UPDATE."""
        assert not re.search(
            r"WHEN\s+MATCHED\s+THEN\s+UPDATE",
            self.sql,
            re.IGNORECASE,
        )

    def test_insert_lists_all_three_columns(self):
        match = re.search(
            r"INSERT\s*\(([^)]+)\)",
            self.sql,
            re.IGNORECASE,
        )
        assert match
        cols = match.group(1).lower()
        assert "doc_num" in cols
        assert "fiscal_year" in cols
        assert "fiscal_month" in cols


# ───────────────────────────────────────────────────────────
# 01_create_tables.sql — composite PK + CHECK constraints
# ───────────────────────────────────────────────────────────
class TestCreateTables3Cols:

    @classmethod
    def setup_class(cls):
        cls.sql = _read("01_create_tables.sql")

    def test_has_audit_disabled_warning(self):
        assert "AUDIT DISABLED BY DESIGN" in self.sql

    def test_no_audit_columns(self):
        forbidden = ["created_at", "created_by", "updated_at", "updated_by"]
        for col in forbidden:
            assert col not in self.sql.lower()

    def test_primary_key_is_three_columns(self):
        """⚠️ CRITICAL: PK must reference ALL 3 columns."""
        match = re.search(
            r"PRIMARY\s+KEY\s*\(([^)]+)\)",
            self.sql,
            re.IGNORECASE,
        )
        assert match, "PRIMARY KEY clause not found"
        pk_cols = match.group(1).lower()
        assert "doc_num"      in pk_cols
        assert "fiscal_year"  in pk_cols
        assert "fiscal_month" in pk_cols
        # Two commas → three columns
        assert pk_cols.count(",") >= 2, (
            "3-column composite PK must have 2 commas separating columns"
        )

    def test_fiscal_year_range_check(self):
        """CHECK constraint must enforce 2020-2099."""
        match = re.search(
            r"CHECK\s*\(\s*fiscal_year\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)\s*\)",
            self.sql,
            re.IGNORECASE,
        )
        assert match, "fiscal_year CHECK constraint missing"
        assert int(match.group(1)) == 2020
        assert int(match.group(2)) == 2099

    def test_fiscal_month_range_check(self):
        """CHECK constraint must enforce 1-12."""
        match = re.search(
            r"CHECK\s*\(\s*fiscal_month\s+BETWEEN\s+(\d+)\s+AND\s+(\d+)\s*\)",
            self.sql,
            re.IGNORECASE,
        )
        assert match, "fiscal_month CHECK constraint missing"
        assert int(match.group(1)) == 1
        assert int(match.group(2)) == 12

    def test_fiscal_year_is_int_not_string(self):
        """Year stored as INT for filterability, not STRING."""
        match = re.search(
            r"fiscal_year\s+(\w+)",
            self.sql,
            re.IGNORECASE,
        )
        assert match
        assert match.group(1).upper() == "INT"


# ───────────────────────────────────────────────────────────
# 04_hard_delete.sql — 3-column WHERE
# ───────────────────────────────────────────────────────────
class TestHardDelete3Cols:

    @classmethod
    def setup_class(cls):
        cls.sql = _read("04_hard_delete.sql")

    def test_uses_delete_not_update(self):
        assert re.search(r"\bDELETE\s+FROM\b", self.sql, re.IGNORECASE)
        assert not re.search(r"UPDATE.*SET", self.sql, re.IGNORECASE)

    def test_where_includes_all_three_pk_columns(self):
        """⚠️ Missing any column = catastrophic data loss."""
        match = re.search(
            r"WHERE\s+(.+?)$",
            self.sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert match
        where_clause = match.group(1).lower()
        assert "doc_num"      in where_clause
        assert "fiscal_year"  in where_clause
        assert "fiscal_month" in where_clause
        and_count = len(re.findall(r"\band\b", where_clause))
        assert and_count >= 2, (
            f"3-column delete must have at least 2 ANDs, got {and_count}"
        )
