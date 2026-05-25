"""MERGE logic tests for single-PK pattern.

Verifies that:
  - ON clause uses the full PK
  - UPDATE branch sets non-PK columns
  - INSERT branch lists all columns

These are string-pattern tests on the SQL we generate. Real
end-to-end MERGE tests against Fabric would run in a separate
integration suite.

Run: pytest tests/test_merge_logic.py
"""
import re
from pathlib import Path

SQL_DIR = Path(__file__).parent.parent / "03sql"


def _read(filename: str) -> str:
    return (SQL_DIR / filename).read_text(encoding="utf-8")


# ───────────────────────────────────────────────────────────
# 03_merge_upsert.sql — single PK on gl_code
# ───────────────────────────────────────────────────────────
class TestMergeUpsert:

    @classmethod
    def setup_class(cls):
        cls.sql = _read("03_merge_upsert.sql")

    def test_mapping_merge_on_full_pk(self):
        """Locked decision #2 — ON clause includes every PK column"""
        pattern = r"ON\s+t\.gl_code\s*=\s*s\.gl_code"
        assert re.search(pattern, self.sql, re.IGNORECASE)

    def test_mapping_merge_has_when_matched_update(self):
        assert re.search(
            r"WHEN\s+MATCHED\s+THEN\s+UPDATE\s+SET\s+group_id",
            self.sql,
            re.IGNORECASE,
        )

    def test_mapping_merge_has_when_not_matched_insert(self):
        assert re.search(
            r"WHEN\s+NOT\s+MATCHED\s+THEN\s+INSERT\s*\(\s*gl_code\s*,\s*group_id\s*\)",
            self.sql,
            re.IGNORECASE,
        )

    def test_dim_merge_present(self):
        """Two MERGE statements expected: dim + mapping (skip comment lines)"""
        code_lines = [ln for ln in self.sql.splitlines() if not ln.strip().startswith("--")]
        code = "\n".join(code_lines)
        merges = re.findall(r"^\s*MERGE\b", code, re.IGNORECASE | re.MULTILINE)
        assert len(merges) == 2


# ───────────────────────────────────────────────────────────
# 01_create_tables.sql — schema constraints
# ───────────────────────────────────────────────────────────
class TestCreateTables:

    @classmethod
    def setup_class(cls):
        cls.sql = _read("01_create_tables.sql")

    def test_has_audit_disabled_warning(self):
        """Locked decision #16 — warning block must be present"""
        assert "AUDIT DISABLED BY DESIGN" in self.sql

    def test_no_audit_columns(self):
        """Locked decision #16 — no created_at/updated_at/by as column definitions"""
        forbidden = ["created_at", "created_by", "updated_at", "updated_by"]
        # Strip comment lines before checking — forbidden words may appear in
        # the "to enable audit later" comment block by design.
        code_lines = [ln for ln in self.sql.splitlines() if not ln.strip().startswith("--")]
        code = "\n".join(code_lines).lower()
        for col in forbidden:
            assert col not in code, f"Found forbidden audit column definition: {col}"

    def test_no_is_active_on_mapping(self):
        """Locked decision #6 — hard delete, no soft delete flag"""
        mapping_section = re.search(
            r"CREATE\s+TABLE.*gl_group_mapping.*?\)",
            self.sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert mapping_section
        assert "is_active" not in mapping_section.group(0).lower()

    def test_dim_table_has_pk_on_group_id(self):
        assert re.search(
            r"PRIMARY\s+KEY\s*\(\s*group_id\s*\)",
            self.sql,
            re.IGNORECASE,
        )

    def test_mapping_table_has_pk_on_gl_code(self):
        assert re.search(
            r"PRIMARY\s+KEY\s*\(\s*gl_code\s*\)",
            self.sql,
            re.IGNORECASE,
        )

    def test_gl_code_has_format_check(self):
        """T-SQL: NOT LIKE '%[^0-9]%' — digits only"""
        assert re.search(
            r"CHECK\s*\(.*gl_code\s+NOT\s+LIKE",
            self.sql,
            re.IGNORECASE,
        )


# ───────────────────────────────────────────────────────────
# 04_hard_delete.sql
# ───────────────────────────────────────────────────────────
class TestHardDelete:

    @classmethod
    def setup_class(cls):
        cls.sql = _read("04_hard_delete.sql")

    def test_uses_delete_not_update(self):
        """Locked decision #22 — hard delete"""
        assert re.search(r"\bDELETE\s+FROM\b", self.sql, re.IGNORECASE)
        assert not re.search(
            r"UPDATE.*SET\s+is_active",
            self.sql,
            re.IGNORECASE,
        )

    def test_where_includes_pk(self):
        """T-SQL named param: @gl_code"""
        assert re.search(
            r"WHERE\s+gl_code\s*=\s*@gl_code",
            self.sql,
            re.IGNORECASE,
        )
