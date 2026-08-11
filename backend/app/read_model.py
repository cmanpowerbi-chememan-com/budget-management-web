"""Main-table read path — 3-layer (SAP/Approved/Pending) budget grid, RLS
filtered (A4, ADR-0010/0020/0023).

Split by responsibility so the never-cut visibility/RLS rules are testable
without a DB at all:

- `fetch_board_pending_rows` — the ONE local cross-schema SQL: `dbo.board_budget`
  (fy=board_year) FULL OUTER JOIN `budget.pending_budget` (fy=pending_year) on
  `(cost_center, gl_account)`. Both schemas live in the SAME Fabric SQL Database
  (ADR-0023) so this is a single in-DB query, no cross-store merge.
- `merge_budget_rows` — pure function: takes the join rows + the SAP dict
  (already fetched cross-store via `app.sap.fetch_sap_actuals`) + the caller's
  RLS `Scope` (A3), and returns the final visible/editable row list. No I/O.
- `get_budget_grid` — thin orchestrator wiring the two fetches + the merge for
  the router.

Year mapping (confirmed against `docs/specs/budget-transactional-data-model.md`
§1c and ADR-0010): the endpoint's `planning_year` is the Pending year (Y+1);
board_budget and the SAP read-through both use the standing/current year
(Y = planning_year - 1). Approved-Y is a REFERENCE column beside the Pending
Y+1 the user is planning — comparing them is a Phase-2 dashboard concern, not
this table.

Row visibility (ADR-0010): the union key is `(cost_center, gl_account)` across
all three sources — SAP leads the initial set, but a row that exists ONLY in
board_budget (an Approved import with no actual yet) or ONLY in pending_budget
(added by hand via "+ เพิ่ม transaction") must persist too, so the local join
is FULL OUTER (not board-only-LEFT), and any SAP-only key not matched by the
join is appended as its own row with a blank (all-zero) Pending layer.
"""
from datetime import datetime

from pydantic import BaseModel
import pyodbc

from app.approval import LOCKED_APPROVAL_STATUSES
from app.config import Settings, get_settings
from app.deadline import YEAR_NOT_OPEN, fiscal_year_state
from app.gl_access import fetch_admin_gl_codes, fetch_master_gl_codes
from app.rls import Scope
from app.sap import MONTH_COLUMNS, fetch_sap_actuals_cached, resolve_sap_coverage_cached

_BOARD_COLUMNS = ("gl_name", "gl_group", "c_level", "division", "department")
# NOTE: no "status" here — `budget.pending_budget` has no status column
# (verified live 2026-07-15; status lives entirely on `budget.approval_status`,
# owned by A6). See app.write_model module docstring for the same finding.
_PENDING_META_COLUMNS = ("template", "remark", "gl_name", "gl_group", "c_level", "division", "department")

# Explicit column lists for the two join-side subqueries (SQL standard: no
# SELECT * — only the columns the outer SELECT / row model actually consume).
_BOARD_BUDGET_COLUMNS: tuple[str, ...] = ("cost_center", "gl_account", *MONTH_COLUMNS, "total_year", *_BOARD_COLUMNS)
_PENDING_BUDGET_COLUMNS: tuple[str, ...] = (
    "cost_center",
    "gl_account",
    *MONTH_COLUMNS,
    "total_year",
    "_updated_at",
    *_PENDING_META_COLUMNS,
)

JOIN_ROW_COLUMNS: tuple[str, ...] = (
    "cost_center",
    "gl_account",
    "board_cost_center",
    "pending_cost_center",
    *(f"board_{m}" for m in MONTH_COLUMNS),
    "board_total_year",
    *(f"board_{c}" for c in _BOARD_COLUMNS),
    *(f"pending_{m}" for m in MONTH_COLUMNS),
    "pending_total_year",
    "pending_updated_at",
    *(f"pending_{c}" for c in _PENDING_META_COLUMNS),
)


def _cc_filter_clause(cost_centers: list[str] | None) -> tuple[str, list[str]]:
    """Build the optional `AND cost_center IN (?, ?, ...)` RLS restriction,
    fully parameterized (never string-interpolated). `None` = no restriction
    (admin-wide bypass only, ADR-0012/0019). An empty list never reaches this
    helper — `fetch_board_pending_rows` short-circuits before calling it."""
    if cost_centers is None:
        return "", []
    placeholders = ", ".join(["?"] * len(cost_centers))
    return f" AND cost_center IN ({placeholders})", list(cost_centers)


def _board_pending_join_sql(cc_filter_clause: str) -> str:
    return f"""
        SELECT
            COALESCE(b.cost_center, p.cost_center) AS cost_center,
            COALESCE(b.gl_account, p.gl_account) AS gl_account,
            b.cost_center AS board_cost_center,
            p.cost_center AS pending_cost_center,
            {", ".join(f"b.{m} AS board_{m}" for m in MONTH_COLUMNS)},
            b.total_year AS board_total_year,
            {", ".join(f"b.{c} AS board_{c}" for c in _BOARD_COLUMNS)},
            {", ".join(f"p.{m} AS pending_{m}" for m in MONTH_COLUMNS)},
            p.total_year AS pending_total_year,
            p._updated_at AS pending_updated_at,
            {", ".join(f"p.{c} AS pending_{c}" for c in _PENDING_META_COLUMNS)}
        FROM (SELECT {", ".join(_BOARD_BUDGET_COLUMNS)} FROM dbo.board_budget WHERE fiscal_year = ?{cc_filter_clause}) b
        FULL OUTER JOIN (SELECT {", ".join(_PENDING_BUDGET_COLUMNS)} FROM budget.pending_budget WHERE fiscal_year = ?{cc_filter_clause}) p
            ON b.cost_center = p.cost_center AND b.gl_account = p.gl_account
    """


def fetch_cc_dims(conn: pyodbc.Connection, cost_centers: list[str]) -> dict[str, dict[str, str | None]]:
    """Batch (cost_center -> department/division/c_level) lookup used ONLY to
    backfill a SAP-led row's dimensions when the caller applies the
    department filter (D10): a pure-SAP (cost_center, gl_account) key has no
    board/pending snapshot yet, so it has no department of its own — without
    this fallback, the department filter silently dropped it (real loss
    observed live: a department lost 10 SAP-led rows / 302,560.17 THB).

    One deterministic row per cost_center (`ORDER BY filler_email` — same
    tie-break rule as `write_model._lookup_cc_dims`, D11): a cost_center can
    have more than one row in `dbo.cc_filler_map` (one per filler_email)."""
    if not cost_centers:
        return {}
    placeholders = ", ".join(["?"] * len(cost_centers))
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT cost_center, department, division, c_level FROM (
                SELECT cost_center, department, division, c_level,
                       ROW_NUMBER() OVER (PARTITION BY cost_center ORDER BY filler_email) AS rn
                FROM dbo.cc_filler_map
                WHERE cost_center IN ({placeholders})
            ) ranked
            WHERE rn = 1
            """,
            *cost_centers,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return {r[0]: {"department": r[1], "division": r[2], "c_level": r[3]} for r in rows}


def fetch_locked_departments(conn: pyodbc.Connection, fiscal_year: int) -> frozenset[str]:
    """Every department whose `(department, fiscal_year)` approval record is
    mid-chain or fully signed off (ADR-0013 read-only lock, UI parity port,
    2026-08-05) — the read-side counterpart of
    `write_model._ensure_department_not_locked`, sharing the SAME
    `app.approval.LOCKED_APPROVAL_STATUSES` set so the two paths can never
    disagree about WHICH STATUSES are locked. WHICH DEPARTMENT a given
    cost_center resolves to is now ALSO shared (gate finding D2, fixed
    2026-08-07): both paths resolve it live from `dbo.cc_filler_map` first —
    the read side via `merge_budget_rows`'s `_resolve_live_department`
    helper, only falling back to the row's own snapshot for a cost_center
    `cc_dims` has nothing to say about (see the longer note beside
    `app.approval.LOCKED_APPROVAL_STATUSES` for the one remaining
    theoretical edge). One query per grid request (not per row) —
    `get_budget_grid` calls this once and `merge_budget_rows` consults the
    returned set per row, in memory."""
    placeholders = ", ".join("?" for _ in LOCKED_APPROVAL_STATUSES)
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT DISTINCT department FROM budget.approval_status WHERE fiscal_year = ? AND status IN ({placeholders})",
            fiscal_year, *LOCKED_APPROVAL_STATUSES,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return frozenset(r[0] for r in rows)


def fetch_board_pending_rows(
    conn: pyodbc.Connection,
    board_year: int,
    pending_year: int,
    cost_centers: list[str] | None = None,
) -> list[dict]:
    """Run the local board+pending cross-schema join for one (board_year,
    pending_year) pair, RLS-restricted to the caller's See-scope `cost_centers`
    on BOTH sides of the join (spec §1c: SQL-side filtering, defense-in-depth
    on top of `merge_budget_rows`'s Python-side filter — both stay active).

    `cost_centers=None` = admin-wide, no restriction (ONLY valid when the
    caller is an admin with the admin-wide toggle on — enforced by
    `get_budget_grid`, never by this function). `cost_centers=[]` (an empty
    See scope) short-circuits to an empty result with NO query executed at
    all — an empty SQL `IN ()` is invalid syntax, and there is nothing to
    fetch anyway.

    Returns a list of dicts keyed by `JOIN_ROW_COLUMNS` (fixed positional
    mapping — no reliance on `cursor.description`)."""
    if cost_centers is not None and len(cost_centers) == 0:
        return []

    cc_filter_clause, cc_params = _cc_filter_clause(cost_centers)
    sql = _board_pending_join_sql(cc_filter_clause)
    params = [board_year, *cc_params, pending_year, *cc_params]

    cursor = conn.cursor()
    try:
        cursor.execute(sql, *params)
        raw_rows = cursor.fetchall()
    finally:
        cursor.close()
    return [dict(zip(JOIN_ROW_COLUMNS, row)) for row in raw_rows]


def _num(value) -> float:
    return 0.0 if value is None else float(value)


class LayerAmounts(BaseModel):
    """12 monthly cells + the stored yearly total, common to all 3 layers."""

    m01: float = 0.0
    m02: float = 0.0
    m03: float = 0.0
    m04: float = 0.0
    m05: float = 0.0
    m06: float = 0.0
    m07: float = 0.0
    m08: float = 0.0
    m09: float = 0.0
    m10: float = 0.0
    m11: float = 0.0
    m12: float = 0.0
    total_year: float = 0.0


class SapLayer(LayerAmounts):
    """🟢 SAP · ใช้จริง — read-only, auto from the DW, never entered.

    ADR-0026: a month whose postings are not complete yet is `None`, nulled
    SERVER-SIDE — the 12 months are re-declared here (and ONLY here, not on
    `LayerAmounts`) because Approved/Pending are budget figures a human typed
    and are never incomplete. `total_year` sums the VISIBLE months only, so it
    always reconciles against the cells on screen.

    `has_actuals` reports whether this (cost_center, gl_account) has ANY
    non-zero month in the full year, hidden months included — the only thing
    the client learns about a hidden month (never its amount). The grid needs
    it for delete-eligibility ("a row with SAP history was not added on the
    web"), which would otherwise silently flip the moment months are nulled."""

    m01: float | None = 0.0
    m02: float | None = 0.0
    m03: float | None = 0.0
    m04: float | None = 0.0
    m05: float | None = 0.0
    m06: float | None = 0.0
    m07: float | None = 0.0
    m08: float | None = 0.0
    m09: float | None = 0.0
    m10: float | None = 0.0
    m11: float | None = 0.0
    m12: float | None = 0.0
    has_actuals: bool = False


class BoardLayer(LayerAmounts):
    """🔵 Approved · งบอนุมัติ — read-only reference, current year."""

    gl_name: str | None = None
    gl_group: str | None = None
    c_level: str | None = None
    division: str | None = None
    department: str | None = None


class PendingLayer(LayerAmounts):
    """⚫ Pending · งบรออนุมัติ — the editable planning-year layer. Starts
    blank (all defaults) when no `pending_budget` row exists yet.

    No `status` field — `budget.pending_budget` has no status column
    (status lives on `budget.approval_status`, owned by A6).

    `updated_at` (added for A8): the row's `_updated_at` optimistic-lock
    token, `None` when no `pending_budget` row exists yet (the frontend
    then sends `expected_updated_at=None` on `PUT /budget/rows`, the
    create path). Without exposing this, an existing pending row could
    never be edited via the lock-token contract `write_model.py` requires —
    only ever created."""

    template: str | None = None
    remark: str | None = None
    gl_name: str | None = None
    gl_group: str | None = None
    c_level: str | None = None
    division: str | None = None
    department: str | None = None
    updated_at: datetime | None = None


class BudgetRow(BaseModel):
    """One visible `(cost_center, gl_account)` row of the main grid. All 3
    layers are always present (zero-filled when absent) so the frontend never
    has to null-check a layer object — only the amounts/metadata are blank."""

    cost_center: str
    gl_account: str
    sap: SapLayer = SapLayer()
    board: BoardLayer = BoardLayer()
    pending: PendingLayer = PendingLayer()
    editable: bool = False


def _sap_layer(months: dict[str, float] | None, visible_months: frozenset[int] | None = None) -> SapLayer:
    """Build the display-side SAP layer, applying the ADR-0026 month mask.

    `visible_months` = month numbers complete enough to show (`None` = show
    every month, the pre-ADR-0026 behavior kept for callers that don't pass
    it). Masking happens HERE rather than in `app.sap.fetch_sap_actuals` for
    two reasons: that fetch stays a complete mirror of gold (the DB->web
    parity harness reads it month by month), and `merge_budget_rows` still
    needs the FULL year to decide row visibility (ADR-0010, unchanged).

    The mask is applied uniformly, including to a key with no SAP row at all:
    "0.00" in an incomplete month is a claim about that month too."""
    raw = months or {}
    values: dict[str, float | None] = {}
    for month, col in enumerate(MONTH_COLUMNS, start=1):
        amount = raw.get(col, 0.0)
        values[col] = amount if visible_months is None or month in visible_months else None
    return SapLayer(
        **values,
        total_year=round(sum(v for v in values.values() if v is not None), 2),
        has_actuals=any(raw.get(col, 0.0) for col in MONTH_COLUMNS),
    )


def _board_layer(jr: dict) -> BoardLayer:
    if jr.get("board_cost_center") is None:
        return BoardLayer()
    return BoardLayer(
        **{m: _num(jr.get(f"board_{m}")) for m in MONTH_COLUMNS},
        total_year=_num(jr.get("board_total_year")),
        **{c: jr.get(f"board_{c}") for c in _BOARD_COLUMNS},
    )


def _pending_layer(jr: dict) -> PendingLayer:
    if jr.get("pending_cost_center") is None:
        return PendingLayer()
    return PendingLayer(
        **{m: _num(jr.get(f"pending_{m}")) for m in MONTH_COLUMNS},
        total_year=_num(jr.get("pending_total_year")),
        updated_at=jr.get("pending_updated_at"),
        **{c: jr.get(f"pending_{c}") for c in _PENDING_META_COLUMNS},
    )


def _resolve_live_department(
    cc: str, row: BudgetRow, cc_dims: dict[str, dict[str, str | None]] | None
) -> str | None:
    """ONE resolution order shared by BOTH `merge_budget_rows` consumers —
    the department-filter grouping and the editable-lock decision (D2 fix,
    2026-08-07) — so they can never disagree with each other, and so the
    read path can never disagree with the write path
    (`write_model._ensure_department_not_locked`, which resolves live from
    `dbo.cc_filler_map` and nothing else).

    Live `cc_dims` first (matches the write path), then the row's own
    `pending`/`board` snapshot as a fallback ONLY for a cost_center `cc_dims`
    has nothing to say about (absent entirely, or `cc_dims=None` because the
    caller never fetched it) — never the other way around, so a stale
    snapshot can no longer outrank the live master after a CC->ฝ่าย remap."""
    return (cc_dims and cc_dims.get(cc, {}).get("department")) or row.pending.department or row.board.department


def merge_budget_rows(
    join_rows: list[dict],
    sap_actuals: dict[tuple[str, str], dict[str, float]],
    scope: Scope,
    admin_view_enabled: bool = False,
    cost_center_filter: str | None = None,
    department_filter: str | None = None,
    cc_dims: dict[str, dict[str, str | None]] | None = None,
    admin_gl_codes: frozenset[str] | None = None,
    master_gl_codes: frozenset[str] | None = None,
    visible_sap_months: frozenset[int] | None = None,
    locked_departments: frozenset[str] | None = None,
    year_not_open: bool = False,
) -> list[BudgetRow]:
    """Pure merge: board+pending join rows + SAP dict + RLS scope -> the final
    visible/editable row list. No I/O (aside from the optional pre-fetched
    `cc_dims` dict, itself I/O-free here) — fully unit-testable.

    `cc_dims` (D10 fix, reordered D2 fix 2026-08-07 — see
    `_resolve_live_department`): the LIVE `cost_center -> department` lookup
    (from `dbo.cc_filler_map`, fetched by the caller via `fetch_cc_dims`),
    now consulted FIRST — ahead of the row's own `pending`/`board` snapshot —
    for both the `department_filter` grouping and the editable-lock decision
    below. Originally added only to stop a SAP-led row (no board/pending
    layer, so no department of its own) from being silently dropped by
    `department_filter`; still serves that role as the sole source for such
    a row. `None` (the default) preserves the old behavior for callers that
    don't need the department filter at all.

    RLS (ADR-0019, honoring A3's `admin_view_enabled` hook): a non-admin (or
    an admin with the toggle off) only sees rows whose cost_center is in their
    `see_cost_centers`; `admin_view_enabled=True` bypasses the CC restriction
    ONLY when `scope.is_admin` is also true (a non-admin can never widen —
    A3's own scope resolution already refuses to self-elevate, and this merge
    re-checks `scope.is_admin` again as defense-in-depth). `editable` is true
    for a Fill-scope cost_center, or for every row when the admin-wide bypass
    is active (admin edits any Pending freely, ADR-0012).

    `admin_gl_codes` (GL `edit_by` admin-only lock, design v2, flag-gated):
    when supplied (the caller — `get_budget_grid` — only does so when
    `Settings.gl_edit_by_enabled` is True AND `scope.is_admin` is False), any
    row whose `gl_account` is in this set is DROPPED entirely for a
    non-admin caller — not just its amounts, the whole row (rule 1: secret
    GL data must never reach a non-admin, including an approver reviewing a
    department). Re-checks `scope.is_admin` here too as defense-in-depth,
    same style as the `admin_wide` re-check above. `None` (the default)
    preserves old behavior for callers that don't pass it.

    `master_gl_codes` (GL master-membership rule, 2026-07-18 product
    decision by jakkaritw): when supplied, any row whose `gl_account` is
    NOT in this set is DROPPED entirely — for EVERY caller, admin or not
    (unlike `admin_gl_codes`, this rule is not role-based; reverses the
    earlier "add-later reference" behavior where such a row rendered
    read-only). Composes independently with the `admin_gl_codes` strip: a
    row survives only if (gl in master OR master_gl_codes is None) AND
    (gl not admin-locked OR caller is admin OR admin_gl_codes is None).
    `None` (the default) preserves old behavior for callers that don't
    pass it (e.g. existing tests).

    Net-zero GL row hiding, PER-MONTH rule (2026-08-11, jakkaritw —
    supersedes the 2026-07-24 full-year-net rule; `plan/hide-netzero-gl-rows.md`
    is deleted, canonical spec = the ADR-0010 amendment): a
    `(cost_center, gl_account)` row is dropped when EVERY individual SAP
    month rounds to 0.00 (2dp) — i.e. no SAP row at all, or a same-month
    +/- pair that cancels within one month — AND neither a board NOR a
    pending row exists for it. A cross-month reversal (a reversed accrual
    posting +X in one month and -X in a later month, e.g. SAP doc
    1110001154, CC 10CS010000/GL 6210900999: m03 +13,150 / m04 -13,150)
    nets to zero for the year but each month is individually nonzero, so
    it now STAYS VISIBLE — same-month +/- pairs (every month 0.00) remain
    hidden as noise. Presence, not value: a genuinely all-zero board/pending
    row still shows (WIP safeguard: a blank "+ เพิ่ม Transaction" row must
    never vanish). Not flag-gated, not role-based; always applied.

    `visible_sap_months` (ADR-0026): month numbers whose SAP actuals are
    complete enough to display — every other month of the SAP layer is nulled
    (see `_sap_layer`). `None` = mask nothing. This is a DISPLAY transform
    only: the net-zero row-hide above still reads the FULL year, so a row
    whose only actual falls in a hidden month keeps its row (ADR-0010 row
    visibility is deliberately untouched).

    `locked_departments` (ADR-0013 read-only lock, UI parity port with
    `write_model._ensure_department_not_locked`, 2026-08-05; department
    RESOLUTION fixed to match the write path, gate finding D2, 2026-08-07):
    departments whose `(department, fiscal_year)` approval record is
    mid-chain (PENDING_APPROVER1/2/3) or fully signed off (APPROVED) — a
    Fill-scope cost_center in one of these departments is no longer
    `editable`, because a write there would be rejected by that same
    write-side gate; opening the special-GL subform on such a row now opens
    READ-ONLY instead of failing late on save. Resolved per row via
    `_resolve_live_department` (live `cc_dims` first, then
    `row.pending.department`, then `row.board.department`), falling back to
    `department_filter` itself only when none of those three resolve —
    harmless as a last resort because the `department_filter is not None`
    block above already dropped every row that does not belong to that
    department via the SAME live-first chain, so any row reaching this point
    necessarily already resolved (or was never filtered at all). An
    unresolvable department (all sources `None`) stays fail-OPEN (editable),
    mirroring `_ensure_department_not_locked`'s own documented policy for a
    department that resolves to `None`. `admin_wide` always bypasses this
    check (ADR-0012 — admin edits any Pending freely, including a locked
    department). `None` (the default) preserves old behavior for callers
    that don't pass it (e.g. existing tests) — identical to today.

    D2 fix (2026-08-07): before this fix, the read path preferred the row's
    SNAPSHOT department (`pending.department`/`board.department`) and only
    fell back to live `cc_dims` when that snapshot was absent — so after a
    CC->ฝ่าย remap, a stale snapshot could outrank the live master and the
    read path would disagree with the write path in either direction (proven
    live against production 2026-08-07, CC 10IT012000). Both `merge_budget_rows`
    consumers now resolve live-first via the shared `_resolve_live_department`
    helper, matching the write path's own live-only resolution exactly. What
    still, in principle, differs: the write path has NO snapshot concept at
    all — a cost_center entirely REMOVED from `dbo.cc_filler_map` (not merely
    remapped) resolves `department=None` there and stays fail-OPEN, whereas
    the read path would still fall back to a stale snapshot for that same row
    if one exists, which could resolve to a locked department. `write_model`'s
    own docstring already notes this cannot currently be reached by a
    non-admin (their Fill scope is itself derived from `dbo.cc_filler_map`,
    so any cost_center they may address already has a department row there)
    — not fixed further here, same accepted edge as the write path's.

    `year_not_open` (2026-08-08 3-state extension, jakkaritw): `planning_year`
    has NO `dbo.submission_deadline` row at all (see `app.deadline`'s module
    docstring for the 3-state table) — a normal write to it would be
    rejected by `write_model._ensure_year_open_for_write`'s SAME
    `app.deadline.fiscal_year_state` check, so a Fill-scope cost_center in
    that year is no longer `editable` here either; opening a special-GL
    subform on such a row now opens READ-ONLY instead of failing late on
    save (the exact late-403 pattern ADR-0013 exists to eliminate).
    Deliberately scoped narrower than `locked_departments`: it does NOT
    also cover PAST_DEADLINE (a row exists but its date has passed) — that
    remains a pre-existing, separate gap between the read and write paths
    (the read side has never modeled `is_post_deadline` at all), left
    untouched here per the task's own scope; only the NOT_OPEN case was
    asked for. Bypassed by `admin_wide` exactly like `locked_departments`
    (admin edits any Pending freely, ADR-0012). `False` (the default)
    preserves old behavior for callers that don't pass it (e.g. existing
    tests) — identical to today.
    """
    admin_wide = scope.is_admin and admin_view_enabled
    visible_ccs = None if admin_wide else set(scope.see_cost_centers)
    fill_ccs = set(scope.fill_cost_centers)

    # PER-MONTH SAP nonzero check per key (2026-08-11, jakkaritw — supersedes
    # the full-year-net rule), computed BEFORE any month masking and before
    # `remaining_sap` is drained — the net-zero row-hide rule must not change
    # its answer just because some months are hidden from display (ADR-0026).
    # A key counts as nonzero if ANY individual month rounds to nonzero at
    # 2dp, even if the months sum to zero for the year (a reversed accrual
    # posts +X in one month and -X in another — SAP doc 1110001154, CC
    # 10CS010000/GL 6210900999: m03 +13,150 / m04 -13,150 — and must show
    # per posting period like SAP does, not disappear because the year nets
    # to zero). A same-month +/- pair, where every month is individually
    # 0.00, still counts as zero and is hidden as noise.
    sap_nonzero_keys = {
        key
        for key, months in sap_actuals.items()
        if any(round(months.get(col, 0.0), 2) != 0 for col in MONTH_COLUMNS)
    }

    # Presence (not value) of a board/pending row per key, from the join
    # rows themselves — `BoardLayer()`/`PendingLayer()` defaults look
    # identical to a real all-zero row, so presence can't be read off the
    # merged `BudgetRow` layer values.
    board_present = {(jr["cost_center"], jr["gl_account"]) for jr in join_rows if jr.get("board_cost_center") is not None}
    pending_present = {(jr["cost_center"], jr["gl_account"]) for jr in join_rows if jr.get("pending_cost_center") is not None}

    remaining_sap = dict(sap_actuals)
    merged: dict[tuple[str, str], BudgetRow] = {}

    for jr in join_rows:
        key = (jr["cost_center"], jr["gl_account"])
        sap_months = remaining_sap.pop(key, None)
        merged[key] = BudgetRow(
            cost_center=key[0],
            gl_account=key[1],
            sap=_sap_layer(sap_months, visible_sap_months),
            board=_board_layer(jr),
            pending=_pending_layer(jr),
        )

    for key, months in remaining_sap.items():
        merged[key] = BudgetRow(
            cost_center=key[0], gl_account=key[1], sap=_sap_layer(months, visible_sap_months)
        )

    result: list[BudgetRow] = []
    for (cc, gl), row in merged.items():
        if visible_ccs is not None and cc not in visible_ccs:
            continue
        if master_gl_codes is not None and gl not in master_gl_codes:
            continue
        if admin_gl_codes is not None and gl in admin_gl_codes and not scope.is_admin:
            continue
        if (cc, gl) not in sap_nonzero_keys and (cc, gl) not in board_present and (cc, gl) not in pending_present:
            continue  # net-zero GL row hide, per-month rule (2026-08-11, ADR-0010 amendment)
        if cost_center_filter is not None and cc != cost_center_filter:
            continue
        if department_filter is not None:
            dept = _resolve_live_department(cc, row, cc_dims)
            if dept != department_filter:
                continue
        row_dept = _resolve_live_department(cc, row, cc_dims) or department_filter
        row_locked = bool(locked_departments) and row_dept in locked_departments
        # year_not_open outranks even admin (jakkaritw 2026-08-10): a NOT_OPEN
        # year is file-import-only, so no web identity — admin included — gets
        # a writable cell there. Within an OPEN year, admin_wide still bypasses
        # the per-department approval lock (ADR-0012) exactly as before.
        row.editable = (admin_wide or (cc in fill_ccs and not row_locked)) and not year_not_open
        result.append(row)

    return sorted(result, key=lambda r: (r.cost_center, r.gl_account))


def get_budget_grid(
    fabric_conn: pyodbc.Connection,
    gold_conn: pyodbc.Connection,
    planning_year: int,
    scope: Scope,
    admin_view_enabled: bool = False,
    cost_center_filter: str | None = None,
    department_filter: str | None = None,
    settings: Settings | None = None,
) -> list[BudgetRow]:
    """Orchestrator: board_year = planning_year - 1 (SAP + Approved both use
    the standing/current year; only Pending uses the planning year itself,
    per the data-model spec §1c). Propagates `SapActualsFetchError` as-is —
    the router turns it into a loud 5xx, never a silent-empty layer.

    Resolves the SQL-side CC filter for `fetch_board_pending_rows` here: a
    non-admin (or an admin without the toggle) ALWAYS gets their own
    `see_cost_centers` list pushed into the SQL — this function is the only
    place allowed to pass `cost_centers=None` (admin-wide bypass), and only
    when `scope.is_admin AND admin_view_enabled` are both true.

    GL `edit_by` admin-only lock (design v2, flag-gated): only fetches the
    admin-GL set (one extra query) when `Settings.gl_edit_by_enabled` is True
    AND the caller is NOT admin — an admin never needs the set (nothing gets
    stripped for them), and the flag-OFF default never runs this query at
    all (zero behavior change).

    GL master-membership rule (2026-07-18, NOT flag-gated, NOT role-based):
    always fetches `dbo.gl_group`'s gl_code set and passes it to the merge
    so a GL absent from the master is hidden from EVERY caller, admin
    included.

    ADR-0013 read-only lock (UI parity port, 2026-08-05): fetches the
    locked-departments set for `planning_year` — skipped entirely for an
    admin-wide caller (`admin_wide` bypasses the lock unconditionally inside
    `merge_budget_rows`, so the result would never even be consulted;
    relevant to the first-load perf work). `cc_dims` is now ALSO fetched
    whenever something is actually locked (gate finding D1, 2026-08-05), not
    only when `department_filter` is set (D10's original reason) — a SAP-led
    row (no board/pending layer) has no department of its own, and without
    `cc_dims` it resolves to an unresolvable (fail-OPEN) department even when
    its real department IS locked, silently re-opening the exact defect this
    task exists to close for that row shape.

    3-state year model (2026-08-08, jakkaritw): fetches whether
    `planning_year` is NOT_OPEN (no `dbo.submission_deadline` row at all)
    via the SAME `app.deadline.fiscal_year_state` the write path's
    `_ensure_year_open_for_write` and A6's `submit_department` consult — one
    query, one source of truth, so this can never independently drift from
    either of those. Skipped entirely for admin-wide, same "never consulted"
    reasoning as `locked_departments` just above."""
    settings = settings or get_settings()
    board_year = planning_year - 1
    admin_wide = scope.is_admin and admin_view_enabled
    see_cost_centers_filter = None if admin_wide else list(scope.see_cost_centers)

    join_rows = fetch_board_pending_rows(
        fabric_conn, board_year=board_year, pending_year=planning_year, cost_centers=see_cost_centers_filter
    )
    # Both gold reads below are TTL-cached (perf fix — prod first-load
    # 10-11s -> 2-3s, `Settings.sap_cache_ttl_seconds`): the answer only
    # changes when new SAP data lands, not on every grid request.
    # ADR-0020 amendment 2026-08-11: `fabric_conn` is also threaded through
    # here so the cached loader can read `dbo.hide_document` (transactional
    # DB) and anti-join hidden documents out of the SUM.
    sap_actuals = fetch_sap_actuals_cached(gold_conn, fabric_conn, fiscal_year=board_year)
    # ADR-0026: one extra gold read (~1.2s live, uncached) resolves which
    # months of the SAP layer are complete enough to show. Any failure
    # raises SapActualsFetchError -> 502: fail closed, never "show everything".
    sap_coverage = resolve_sap_coverage_cached(gold_conn, fiscal_year=board_year)

    # ADR-0013 read-only lock: skipped entirely for admin-wide (nothing would
    # consult it — merge_budget_rows bypasses the lock unconditionally for
    # admin_wide before it ever looks at `locked_departments`).
    locked_departments: frozenset[str] = (
        frozenset() if admin_wide else fetch_locked_departments(fabric_conn, fiscal_year=planning_year)
    )

    # 2026-08-08 3-state extension, revised 2026-08-10 (jakkaritw): computed
    # for EVERY caller now, admin included — a NOT_OPEN year is file-import-
    # only, so even the admin-wide grid must render it read-only. (This no
    # longer follows locked_departments' skip-for-admin pattern on purpose.)
    year_not_open = fiscal_year_state(fabric_conn, planning_year) == YEAR_NOT_OPEN

    # D10 + gate finding D1 (2026-08-05): fetch cc_dims when the department
    # filter is in use (D10's original reason) OR when something is actually
    # locked (D1) — a SAP-led row (no board/pending layer) has no department
    # of its own; without cc_dims it resolves an unresolvable (fail-OPEN)
    # `row_dept` even when its real department IS locked. Skipped when
    # neither applies, to avoid the extra round-trip on a plain grid load.
    cc_dims = None
    if department_filter is not None or locked_departments:
        all_ccs = {jr["cost_center"] for jr in join_rows} | {key[0] for key in sap_actuals}
        cc_dims = fetch_cc_dims(fabric_conn, sorted(all_ccs))

    admin_gl_codes = None
    if settings.gl_edit_by_enabled and not scope.is_admin:
        admin_gl_codes = fetch_admin_gl_codes(fabric_conn)

    master_gl_codes = fetch_master_gl_codes(fabric_conn)

    return merge_budget_rows(
        join_rows,
        sap_actuals,
        scope,
        admin_view_enabled=admin_view_enabled,
        cost_center_filter=cost_center_filter,
        department_filter=department_filter,
        cc_dims=cc_dims,
        admin_gl_codes=admin_gl_codes,
        master_gl_codes=master_gl_codes,
        visible_sap_months=frozenset(sap_coverage.visible_months),
        locked_departments=locked_departments,
        year_not_open=year_not_open,
    )
