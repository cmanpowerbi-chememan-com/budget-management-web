"""SAP actuals read-through (ADR-0020, A4) — the DW `gold.fact_gl_trans`
warehouse is queried live on every request; nothing is copied into the app's
own store. The query below is a **never-cut financial contract** — do not
edit its filters/columns without a matching ADR-0020 update:

- `company_code='1000'` is TRIPLY load-bearing (THB-only + no cross-company
  double-count + one consistent sign convention) — never remove/loosen.
- `doc_type<>'CO'` drops CO postings that double-count the FI side.
- The excluded cost-center list intentionally does NOT include `10SC012000`
  (removed from the exclusion list 2026-07-14 — it is a valid CC).
- `assignment_number<>'TFRS16'` and `fiscal_year=?` (the caller's year).
- No sign flip: `company_curr_amount` already carries the correct sign.
- No `doc_status` filter: verified 2026-07-14 that including/excluding the
  only other value ('U') never moves any SUM at any grain.

A missing/failed DW connection or query must surface as a loud error to the
caller (never a silently empty green actuals layer) — see `SapActualsFetchError`.
"""
import pyodbc

MONTH_COLUMNS: tuple[str, ...] = tuple(f"m{m:02d}" for m in range(1, 13))

# Verbatim per ADR-0020 / BUILD_PLAN A4 — do not reformat/reorder/edit.
SAP_ACTUALS_SQL = """
SELECT cost_center, gl_account_number, fiscal_year, period_month, SUM(company_curr_amount) AS actual_thb
FROM gold.fact_gl_trans
WHERE company_code='1000' AND doc_type<>'CO'
  AND cost_center NOT IN ('CMRY01','CMKK01','CMPB01','MNLB00','MNLB01','MNLB02','MNLB03','MNLB04')
  AND assignment_number<>'TFRS16' AND fiscal_year=?
GROUP BY cost_center, gl_account_number, fiscal_year, period_month
"""


class SapActualsFetchError(RuntimeError):
    """Raised when the SAP gold-warehouse read-through query fails (missing
    grant, connection drop, timeout, etc). Callers MUST turn this into a
    loud 5xx response — never swallow it into an empty actuals layer
    (ADR-0020 Consequences: a revoked grant must not look like "no actuals")."""


def fetch_sap_actuals(
    conn: pyodbc.Connection, fiscal_year: int
) -> dict[tuple[str, str], dict[str, float]]:
    """Fetch + pivot one fiscal year of SAP actuals.

    Returns `{(cost_center, gl_account): {"m01":.., ..., "m12":.., "total_year":..}}`.
    Different `gl_account` values for the same `cost_center` are always kept
    as separate keys — COST (5xxx) and SG&A (6xxx) totals never cross.
    """
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(SAP_ACTUALS_SQL, fiscal_year)
        rows = cursor.fetchall()
    except pyodbc.Error as exc:
        # `conn.cursor()` itself can raise (closed connection, dropped
        # session) -- must wrap that too, not just execute()/fetchall()
        # failures, or a connection-level drop bypasses SapActualsFetchError
        # entirely (live-DB finding, 2026-07-15).
        raise SapActualsFetchError(
            f"SAP actuals read-through failed for fiscal_year={fiscal_year}: {exc}"
        ) from exc
    finally:
        if cursor is not None:
            cursor.close()

    result: dict[tuple[str, str], dict[str, float]] = {}
    for cost_center, gl_account_number, _fiscal_year, period_month, actual_thb in rows:
        key = (cost_center, gl_account_number)
        months = result.setdefault(key, {col: 0.0 for col in MONTH_COLUMNS})
        months[f"m{int(period_month):02d}"] = float(actual_thb)

    for months in result.values():
        months["total_year"] = round(sum(months[col] for col in MONTH_COLUMNS), 2)

    return result
