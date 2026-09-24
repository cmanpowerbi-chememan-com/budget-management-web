"""Officer-review workbook builder — Module 1 of PRD #34 (issue #34).

Given a planning fiscal year and open connections to the transactional
Fabric SQL DB and the gold warehouse, `build_officer_workbook` returns the
saved workbook bytes plus everything `app.officer_reconcile` needs to prove
"file = web = Fabric" (the one testing property jakkaritw scoped this task
to, 2026-09-24).

Scope (jakkaritw 2026-09-24, "เอาที่แผนก อนุมัติจบloopแล้วเท่านั้น"): a
department whose `budget.approval_status` is APPROVED for the planning year,
UNION every `pending_budget` row with `template='ADMIN'` (Template 2,
instant-approve) — APPROVED always wins the status label on the same key.

WEB side (D1): rows come from `app.read_model.get_budget_grid` — the exact
function `GET /budget` calls — run once per in-scope department (the literal
admin-view web path), PLUS one extra unfiltered admin-wide call to recover
`template='ADMIN'` rows a per-department call never reaches (an ADMIN row
whose department cannot be resolved AT ALL by `_resolve_scope_departments`,
e.g. a CC missing from `cc_filler_map`, never gets a per-department call in
the first place — never silently dropped, PRD story: "(ไม่ทราบฝ่าย)"). The
unfiltered pass only ADDS a key not already present (fix round 2026-09-24,
finding F2/F3/SPEC-1/SPEC-2): the ORIGINAL D1 proof ("unfiltered
`department is None` implies live-unresolvable") was backwards — the
unfiltered call never fetches `cc_dims` at all (`read_model.py`:
`department_filter is None` and `locked_departments` empty for admin-wide),
so its `row.department` is only the pending/board SNAPSHOT, and CAN be
`None` even when the live master (`cc_filler_map`) resolves a real
department. The LABEL department for every row (from either pass) is
therefore resolved HERE, independently of what `get_budget_grid` happened to
fetch, via the shared `app.read_model._resolve_live_department` chain (live
`cc_dims` -> `pending` snapshot -> `board` snapshot -> `None` ->
`"(ไม่ทราบฝ่าย)"`) — see `_build_summary_rows`. This module never
re-implements the pending ∪ board ∪ SAP-nonzero merge, the net-zero hide, or
the master-GL drop — those rules are reused, not copied (issue #34 story 32).

Everything BudgetRow does not carry (CC name, live GL name/group, live
division/c_level, department status) is read here via the module's OWN
read-only SQL (`_q`, D10) — treated as builder-only enrichment, never
reconciled against the web (jakkaritw's decisions D1-D17, brief 2026-09-24).
"""
import dataclasses
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from zoneinfo import ZoneInfo

import pyodbc
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.budget_xlsx import (
    FIRST_NUM_COL,
    LAST_NUM_COL,
    FONT_NAME,
    NUM_FMT,
    ADMIN_TEMPLATE_STATUS_KEY,
    SummaryRow,
    UnknownStatusError,
    _write_text_cell,
    resolve_status_label,
    tint50,
    workbook_bytes,
    write_summary_sheet,
)
from app.config import SHARED_ADMIN_MAILBOX, Settings, get_settings
from app.read_model import BudgetRow, _resolve_live_department, fetch_cc_dims, get_budget_grid
from app.reference_data import fetch_gl_accounts
from app.rls import Scope
from app.sap import resolve_sap_coverage_cached
from app.special_gl import SPECIAL_GL_GROUPS
from app.subform_read import fetch_detail_lines, fetch_trips

logger = logging.getLogger(__name__)

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
UNKNOWN_DEPT = "(ไม่ทราบฝ่าย)"
SCOPE_LABEL = "ฝ่ายที่อนุมัติแล้ว"

MONTH_ABBR: tuple[str, ...] = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# ---------------------------------------------------------------------------
# D10 — ONE read-only SQL guard, shared with `app.officer_reconcile`. Every
# statement this module (and the reconcile module) composes ITSELF goes
# through this. Imported app functions (get_budget_grid, fetch_cc_dims,
# fetch_gl_accounts, fetch_detail_lines, fetch_trips, resolve_sap_coverage_cached)
# run their own already-audited SQL and are not re-guarded here.
# ---------------------------------------------------------------------------
_FORBIDDEN_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|GRANT|DENY|REVOKE|"
    r"DBCC|BACKUP|RESTORE|INTO|UPDATETEXT|WRITETEXT|OPENROWSET|OPENQUERY|OPENDATASOURCE)\b",
    re.IGNORECASE,
)


class ReadOnlyGuardError(RuntimeError):
    """A SQL statement this module composed failed the read-only guard."""


def q(conn: pyodbc.Connection, sql: str, *params) -> list[tuple]:
    """Read-only guard + execute. Statement must start with SELECT/WITH, must
    not contain ';', and must not contain any DML/DDL/admin keyword as a
    whole word (PRD #34 leftover bug: the prototype's guard missed
    `SELECT...INTO`, `UPDATETEXT`/`WRITETEXT`, `DENY`/`REVOKE`, `DBCC`,
    `BACKUP`/`RESTORE`, `OPENROWSET`/`OPENQUERY`/`OPENDATASOURCE` — all
    covered here)."""
    head = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
    if head not in ("SELECT", "WITH"):
        raise ReadOnlyGuardError(f"refusing non-SELECT/WITH statement (starts {head!r})")
    if ";" in sql:
        raise ReadOnlyGuardError("refusing SQL containing ';' (possible second statement)")
    m = _FORBIDDEN_SQL_RE.search(sql)
    if m:
        raise ReadOnlyGuardError(f"refusing SQL containing forbidden keyword {m.group(0)!r}")
    cursor = conn.cursor()
    try:
        cursor.execute(sql, *params)
        return cursor.fetchall()
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Builder-own SQL (D2/D10) — module-level constants, `?` params only.
# ---------------------------------------------------------------------------
_CC_NAME_SQL = """
    SELECT cost_center, description FROM (
        SELECT cost_center, description,
               ROW_NUMBER() OVER (PARTITION BY cost_center ORDER BY filler_email) AS rn
        FROM dbo.cc_filler_map
    ) ranked WHERE rn = 1
"""
_STATUS_BY_DEPT_SQL = "SELECT department, status FROM budget.approval_status WHERE fiscal_year = ?"
_ADMIN_TEMPLATE_PENDING_SQL = (
    "SELECT cost_center, gl_account, department FROM budget.pending_budget "
    "WHERE fiscal_year = ? AND template = 'ADMIN'"
)
_ADMIN_TEMPLATE_BOARD_DEPT_SQL = (
    "SELECT cost_center, gl_account, department FROM dbo.board_budget WHERE fiscal_year = ?"
)
_IS_AUTO_CALC_SQL = "SELECT detail_id, is_auto_calc FROM budget.pending_budget_detail WHERE fiscal_year = ?"
_TRAVELLER_PII_SQL = "SELECT traveler_name, traveler_empcode FROM budget.budget_trip WHERE fiscal_year = ?"

# ---------------------------------------------------------------------------
# Topic sheets (D9 PORTING SPEC) — order, swatch, columns.
# ---------------------------------------------------------------------------
TOPIC_SHEETS: list[tuple[str, str]] = [
    ("Travelling Expense", "FAE7EB"),
    ("Professional & Legal Fee", "E0D4E7"),
    ("Entertainment", "DBEEF7"),
    ("Training & Seminar", "BDD2E4"),
    ("Public Relation & Donation", "EECEDA"),
    ("Lease & Rental", "CCDCEB"),
]
TOPIC_GROUP_NAMES = frozenset(g for g, _ in TOPIC_SHEETS)

TOPIC_META_FIELDS: dict[str, list[str]] = {
    "Professional & Legal Fee": ["Project", "รายละเอียด"],
    "Entertainment": ["ประเภทการรับรอง", "รายละเอียด"],
    "Training & Seminar": ["หลักสูตรอบรม", "Method"],
    "Public Relation & Donation": ["รายละเอียด"],
    "Lease & Rental": ["ประเภทรถ", "ทะเบียนรถ", "สถานที่ใช้งาน", "กิจกรรม"],
}
# D9: the รายการ column is a FIXED travel column (PRD), never data-dependent.
TRAVEL_FIELDS = ["ทริป", "ชื่อผู้เดินทาง", "ประเทศปลายทาง", "Project", "วัตถุประสงค์การเดินทาง", "จำนวนวัน", "เดือนที่เดินทาง", "รายละเอียด", "รายการ"]
TRAVEL_STRUCTURED_HEADERS = frozenset({"ทริป", "จำนวนวัน", "เดือนที่เดินทาง"})
WRAP_FIELDS = frozenset({"รายละเอียด", "กิจกรรม", "วัตถุประสงค์การเดินทาง", "หลักสูตรอบรม", "รายการ"})
COMMON_HEADERS = ["ฝ่าย", "สายงาน", "Cost Center", "ชื่อ Cost Center", "GL", "ชื่อ GL", "COST/SGA", "สถานะฝ่าย"]
CC_COL, GL_COL = 3, 5

PII_KEY_RE = re.compile(r"email|empcode|employee|traveler|traveller|_user", re.IGNORECASE)


@dataclass
class TopicRow:
    department: str | None
    division: str | None
    cost_center: str
    cc_name: str | None
    gl_account: str
    gl_name: str | None
    side: str
    status_label: str
    topic_vals: list[str | int]
    total_year: float
    months: tuple[float, ...]
    sort_key: tuple


@dataclass
class SheetMeta:
    headers: list[str]
    first_money_col: int
    first: int
    last: int
    n_data_rows: int
    swatch: str
    n_common: int
    n_topic: int
    travel_name_col: int | None


@dataclass
class BuildResult:
    ok: bool
    xlsx_bytes: bytes | None
    failures: list[str]
    warnings: list[str]
    as_of: datetime
    planning_year: int
    n_departments: int
    sap_watermark: date | None
    grand_total_year: float
    grand_board_total: float
    grand_sap_total: float
    lines_per_topic: dict[str, int]
    row_keys: frozenset[tuple[str, str]]
    # For the reconcile (WEB side) — the BudgetRow list actually shown, the
    # topic-sheet detail lines actually used (keyed by parent), and each
    # parent's GL-master gl_group (so the reconcile can group WEB-side detail
    # lines into topics independently of where the FILE side placed them).
    web_rows: dict[tuple[str, str], BudgetRow]
    detail_by_key: dict[tuple[str, str], list[dict]]
    gl_group_by_key: dict[tuple[str, str], str | None]
    # SPEC-2: the resolved LABEL department per (cost_center, gl_account) key
    # — the SAME value written to sheet-1 column A — so the reconcile can key
    # its sheet-1 compare on (department, cost_center, gl_account), not just
    # (cost_center, gl_account) (a mislabeled-department row must FAIL, not
    # publish green).
    department_by_key: dict[tuple[str, str], str]


def _amt_whole_baht(value: float) -> str:
    d = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{d:,.0f} บาท"


def _month_abbrs(codes: list[str] | None) -> str:
    out = []
    for part in codes or []:
        part = str(part).strip()
        if part.isdigit() and 1 <= int(part) <= 12:
            out.append(MONTH_ABBR[int(part) - 1])
    return ", ".join(out)


def _meta_dict(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        d = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _detail_line_text(d: dict, trips_by_id: dict, trip_no_by_id: dict, is_auto_calc_by_id: dict) -> str:
    """Sheet-1 รายละเอียด text for one detail line (ported verbatim from the
    prototype's `detail_line`, D9 fix applied: omit the days part when NULL
    instead of writing 'None วัน')."""
    meta = _meta_dict(d.get("meta_json"))
    trip = trips_by_id.get(d.get("trip_id")) if d.get("trip_id") is not None else None
    if trip is not None:
        dest = str(trip.get("destination") or "").strip()
        head = f"ทริป {trip_no_by_id.get(d['trip_id'], '?')}" + (f": {dest}" if dest else "")
        parts = [head]
        if trip.get("days") is not None:
            parts.append(f"{trip['days']} วัน")
        mn = _month_abbrs(trip.get("travel_months"))
        if mn:
            parts.append(f"เดือน {mn}")
        project = str(trip.get("project") or "").strip()
        if project:
            parts.append(project)
        parts.append(_amt_whole_baht(d["total_year"]))
        suffix = " (เบี้ยเลี้ยงคำนวณอัตโนมัติ)" if is_auto_calc_by_id.get(d["detail_id"]) else ""
        return " · ".join(parts) + suffix
    if d.get("gl_group") == "Entertainment":
        parts = [str(meta[k]).strip() for k in ("ประเภทการรับรอง", "รายละเอียด") if str(meta.get(k) or "").strip()]
        return " · ".join(parts + [_amt_whole_baht(d["total_year"])])
    parts = [
        f"{k}: {str(v).strip()}"
        for k, v in meta.items()
        if str(v if v is not None else "").strip() and not PII_KEY_RE.search(str(k))
    ]
    return " · ".join(parts + [_amt_whole_baht(d["total_year"])])


# ---------------------------------------------------------------------------
# Scope discovery + WEB-side fetch (D1)
# ---------------------------------------------------------------------------
def _resolve_scope_departments(
    fabric_conn: pyodbc.Connection, planning_year: int, status_by_dept: dict[str, str]
) -> tuple[frozenset[str], frozenset[str]]:
    """approved_depts (status == APPROVED) and admin_depts (>=1 pending row
    with template='ADMIN', LIVE-resolved department via `fetch_cc_dims`,
    falling back to the row's own `pending` snapshot, THEN the `board`
    snapshot — the SAME 3-step chain `read_model._resolve_live_department`
    and the Fabric reconcile side both use (fix round finding F3: a CC
    dropped from `cc_filler_map`, e.g. the 08-31 purge, with only a board
    department on record used to resolve to no department here at all,
    silently excluding it from scope while the Fabric side still saw it)."""
    approved_depts = frozenset(d for d, s in status_by_dept.items() if s == "APPROVED")

    admin_rows = q(fabric_conn, _ADMIN_TEMPLATE_PENDING_SQL, planning_year)
    ccs = sorted({r[0] for r in admin_rows})
    cc_dims = fetch_cc_dims(fabric_conn, ccs) if ccs else {}
    board_dept_by_key = {
        (cc, gl): dept for cc, gl, dept in q(fabric_conn, _ADMIN_TEMPLATE_BOARD_DEPT_SQL, planning_year - 1)
    }
    admin_depts: set[str] = set()
    for cc, gl, snapshot_dept in admin_rows:
        dept = cc_dims.get(cc, {}).get("department") or snapshot_dept or board_dept_by_key.get((cc, gl))
        if dept:
            admin_depts.add(dept)
    return approved_depts, frozenset(admin_depts)


def _fetch_web_rows(
    fabric_conn: pyodbc.Connection,
    gold_conn: pyodbc.Connection,
    planning_year: int,
    settings: Settings,
    approved_depts: frozenset[str],
    admin_depts: frozenset[str],
) -> dict[tuple[str, str], BudgetRow]:
    """D1: the literal web path — `get_budget_grid(admin_view_enabled=True,
    department_filter=<dept>)` once per in-scope department, PLUS one extra
    unfiltered admin-wide pass to catch every `template='ADMIN'` key that
    per-department loop above did not already return.

    Fix round 2026-09-24 (F2/F3/SPEC-1): the unfiltered pass ADDS a key ONLY
    when it is not already in `web_rows` — it must NEVER overwrite a
    per-department row, because the unfiltered call never fetches `cc_dims`
    (`read_model.py`: no filter, `locked_departments` empty for admin-wide),
    so its own `row.department` is only the pending/board SNAPSHOT and can be
    `None` even when the per-department call already resolved the row's real
    (live) department correctly. The filter is now "ADMIN template, key not
    yet present" — no longer "department is None" (that check ran on the
    WRONG side's department value; see the module docstring). The row's
    LABEL department is resolved live, uniformly for every row regardless of
    which pass produced it, in `_build_summary_rows`."""
    admin_scope = Scope(email=SHARED_ADMIN_MAILBOX, is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])
    web_rows: dict[tuple[str, str], BudgetRow] = {}

    for department in sorted(approved_depts | admin_depts):
        dept_rows = get_budget_grid(
            fabric_conn, gold_conn, planning_year, admin_scope,
            admin_view_enabled=True, department_filter=department, settings=settings,
        )
        keep = dept_rows if department in approved_depts else [r for r in dept_rows if r.pending.template == "ADMIN"]
        for row in keep:
            web_rows[(row.cost_center, row.gl_account)] = row

    unfiltered = get_budget_grid(
        fabric_conn, gold_conn, planning_year, admin_scope,
        admin_view_enabled=True, department_filter=None, settings=settings,
    )
    for row in unfiltered:
        key = (row.cost_center, row.gl_account)
        if key in web_rows:
            continue
        if row.pending.template == "ADMIN":
            web_rows[key] = row

    return web_rows


def _build_summary_rows(
    web_rows: dict[tuple[str, str], BudgetRow],
    cc_dims: dict[str, dict[str, str | None]],
    cc_names: dict[str, str],
    gl_master: dict[str, dict[str, str | None]],
    status_by_dept: dict[str, str],
    approved_depts: frozenset[str],
) -> tuple[list[SummaryRow], list[str]]:
    failures: list[str] = []
    rows: list[SummaryRow] = []
    seen_keys: set[tuple[str, str]] = set()

    for (cc, gl), br in web_rows.items():
        key = (cc, gl)
        if key in seen_keys:
            failures.append(f"duplicate (cost_center, gl_account) row on sheet 1: {key}")
            continue
        seen_keys.add(key)

        # Fix round 2026-09-24 (F2/F3/SPEC-1/SPEC-2): resolve the LABEL
        # department here, uniformly for every row, via the SAME live-first
        # chain `read_model._resolve_live_department` uses — never trust
        # `br.department` directly, because for a row added by the
        # UNFILTERED admin-wide pass it is only the pending/board snapshot
        # (that call never fetches `cc_dims`). `cc_dims` here was fetched by
        # the caller for every cost_center now IN `web_rows` (after the
        # unfiltered merge), so a live master department is always available
        # when one exists, regardless of which pass produced the row.
        dept = _resolve_live_department(cc, br, cc_dims)
        dims = cc_dims.get(cc, {})
        glmeta = gl_master.get(gl, {})
        side = "COST" if gl.startswith("5") else ("SGA" if gl.startswith("6") else "")

        if dept is not None and dept in approved_depts:
            raw_status = "APPROVED"
        elif br.pending.template == "ADMIN":
            raw_status = ADMIN_TEMPLATE_STATUS_KEY
        else:
            raw_status = status_by_dept.get(dept)
        try:
            status_label = resolve_status_label(raw_status)
        except UnknownStatusError as exc:
            failures.append(f"{key}: {exc}")
            status_label = str(raw_status)

        rows.append(SummaryRow(
            cost_center=cc,
            gl_account=gl,
            department=dept or UNKNOWN_DEPT,
            division=dims.get("division") or br.pending.division or br.board.division,
            c_level=dims.get("c_level") or br.pending.c_level or br.board.c_level,
            cc_name=cc_names.get(cc),
            gl_name=glmeta.get("gl_name") or br.pending.gl_name or br.board.gl_name,
            gl_group=glmeta.get("gl_group") or br.pending.gl_group or br.board.gl_group,
            side=side,
            status_label=status_label,
            months=(
                br.pending.m01, br.pending.m02, br.pending.m03, br.pending.m04,
                br.pending.m05, br.pending.m06, br.pending.m07, br.pending.m08,
                br.pending.m09, br.pending.m10, br.pending.m11, br.pending.m12,
            ),
            total_year=br.pending.total_year,
            board_total_year=br.board.total_year,
            sap_total_year=br.sap.total_year,
            remark=br.pending.remark or "",
            detail_lines=(),
        ))

    rows.sort(key=lambda r: (r.c_level or "", r.division or "", r.department or "", r.cost_center, r.side, r.gl_group or "", r.gl_account))
    return rows, failures


# ---------------------------------------------------------------------------
# Topic-sheet detail lines (D2/D9)
# ---------------------------------------------------------------------------
def _fetch_detail_and_trips(
    fabric_conn: pyodbc.Connection, planning_year: int, rows: list[SummaryRow],
) -> tuple[dict[tuple[str, str], list[dict]], dict[int, dict], dict[int, int], dict[int, bool], list[str]]:
    """One `fetch_detail_lines` call per special-GL parent key (small scope,
    weekly job — acceptable round-trip count), one `fetch_trips` call per
    distinct cost_center that has a Travelling Expense parent (covers BOTH
    GL sides for that CC, per D9's trip-numbering rule), plus one bulk
    `is_auto_calc` read (not selected by `fetch_detail_lines`, D9).

    C-F7: a special-GL parent that carries PENDING money but has ZERO detail
    lines (a legacy/imported row, or its detail lines were deleted) is
    reported as a WARN — "keys only" (cost_center, gl_account), never a
    department or any other name — the topic sheet would silently understate
    that group otherwise, count/SUM still agreeing across FILE/WEB/FABRIC."""
    detail_by_key: dict[tuple[str, str], list[dict]] = {}
    warnings: list[str] = []
    travel_ccs: set[str] = set()
    for r in rows:
        if r.gl_group not in SPECIAL_GL_GROUPS:
            continue
        lines = fetch_detail_lines(fabric_conn, r.cost_center, r.gl_account, planning_year)
        if lines:
            detail_by_key[(r.cost_center, r.gl_account)] = lines
        elif r.total_year:
            warnings.append(f"special-GL parent with pending money but zero detail lines: ({r.cost_center}, {r.gl_account})")
        if r.gl_group == "Travelling Expense":
            travel_ccs.add(r.cost_center)

    trips_by_id: dict[int, dict] = {}
    trip_no_by_id: dict[int, int] = {}
    for cc in sorted(travel_ccs):
        trips = fetch_trips(fabric_conn, cc, planning_year)
        for i, t in enumerate(trips, start=1):
            trips_by_id[t["trip_id"]] = t
            trip_no_by_id[t["trip_id"]] = i

    is_auto_calc_by_id: dict[int, bool] = {r[0]: bool(r[1]) for r in q(fabric_conn, _IS_AUTO_CALC_SQL, planning_year)}
    return detail_by_key, trips_by_id, trip_no_by_id, is_auto_calc_by_id, warnings


def _attach_sheet1_detail_text(
    rows: list[SummaryRow], detail_by_key: dict, trips_by_id: dict, trip_no_by_id: dict, is_auto_calc_by_id: dict,
) -> list[SummaryRow]:
    out = []
    for r in rows:
        lines = detail_by_key.get((r.cost_center, r.gl_account), [])
        if not lines:
            out.append(r)
            continue
        ordered = sorted(lines, key=lambda d: (d.get("trip_id") is None, d.get("trip_id") or 0, d["detail_id"]))
        texts = tuple(_detail_line_text(d, trips_by_id, trip_no_by_id, is_auto_calc_by_id) for d in ordered)
        out.append(dataclasses.replace(r, detail_lines=texts))
    return out


def _build_topic_rows(
    rows: list[SummaryRow], detail_by_key: dict, trips_by_id: dict, trip_no_by_id: dict,
) -> dict[str, list[TopicRow]]:
    row_by_key = {(r.cost_center, r.gl_account): r for r in rows}
    topic_rows: dict[str, list[TopicRow]] = defaultdict(list)
    for key, lines in detail_by_key.items():
        r = row_by_key.get(key)
        if r is None or r.gl_group not in TOPIC_GROUP_NAMES:
            continue
        ordered = sorted(lines, key=lambda d: (d.get("trip_id") is None, d.get("trip_id") or 0, d["detail_id"]))
        for d in ordered:
            if r.gl_group == "Travelling Expense":
                trip = trips_by_id.get(d.get("trip_id"))
                tno = trip_no_by_id.get(d.get("trip_id"))
                topic_vals: list[str | int] = [
                    tno if tno is not None else "",
                    (trip.get("traveler_name") if trip else None) or "",
                    (trip.get("destination") if trip else None) or "",
                    (trip.get("project") if trip else None) or "",
                    (trip.get("purpose") if trip else None) or "",
                    trip.get("days") if (trip and trip.get("days") is not None) else "",
                    _month_abbrs(trip.get("travel_months")) if trip else "",
                    (trip.get("remark") if trip else None) or "",
                    d.get("line_label") or "",
                ]
                sort_extra = tno or 0
            else:
                meta = _meta_dict(d.get("meta_json"))
                topic_vals = [str(meta.get(k) or "").strip() for k in TOPIC_META_FIELDS[r.gl_group]]
                sort_extra = 0
            months = tuple(float(d.get(f"m{m:02d}", 0.0) or 0.0) for m in range(1, 13))
            topic_rows[r.gl_group].append(TopicRow(
                department=r.department, division=r.division, cost_center=r.cost_center, cc_name=r.cc_name,
                gl_account=r.gl_account, gl_name=r.gl_name, side=r.side, status_label=r.status_label,
                topic_vals=topic_vals, total_year=float(d["total_year"]), months=months,
                sort_key=(r.department or "", r.cost_center, sort_extra, r.gl_account, d["detail_id"]),
            ))
    for group in topic_rows:
        topic_rows[group].sort(key=lambda t: t.sort_key)
    return topic_rows


# ---------------------------------------------------------------------------
# Topic-sheet writer (officer-only — D17)
# ---------------------------------------------------------------------------
def _write_topic_sheets(
    wb: Workbook, topic_rows: dict[str, list[TopicRow]], planning_year: int, as_of: datetime, sap_watermark: date | None,
    *, warnings: list[str] | None = None,
) -> dict[str, SheetMeta]:
    base = Font(name=FONT_NAME, size=10)
    head_font = Font(name=FONT_NAME, size=10, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="00805E")
    total_fill = PatternFill("solid", fgColor="E6F2EE")
    top = Alignment(vertical="top")
    top_wrap = Alignment(vertical="top", wrap_text=True)
    board_year = planning_year - 1

    sheet_meta: dict[str, SheetMeta] = {}
    for group, swatch in TOPIC_SHEETS:
        rows_ = topic_rows.get(group, [])
        topic_headers = list(TRAVEL_FIELDS) if group == "Travelling Expense" else list(TOPIC_META_FIELDS[group])
        headers = COMMON_HEADERS + topic_headers + [f"รวมปี {planning_year}"] + [
            "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
        ]
        n_common, n_topic = len(COMMON_HEADERS), len(topic_headers)
        first_money_col = n_common + n_topic + 1
        travel_name_col = (n_common + 2) if group == "Travelling Expense" else None

        ws = wb.create_sheet(title=group)
        ws.sheet_properties.tabColor = swatch
        tint_head_fill = PatternFill("solid", fgColor=swatch)
        tint_value_fill = PatternFill("solid", fgColor=tint50(swatch))
        tint_head_font = Font(name=FONT_NAME, size=10, bold=True, color="1F1F1F")

        wm_text = sap_watermark.strftime("%d/%m/%Y") if sap_watermark else "ไม่ทราบ"
        ws["A1"] = f"{group} · FY{planning_year} · ข้อมูล ณ {as_of:%d/%m/%Y %H:%M} น."
        ws["A1"].font = Font(name=FONT_NAME, size=10, bold=True)
        ws["A2"] = "ยังไม่มีรายการ" if not rows_ else (
            f"1 แถว = 1 รายการย่อยจาก Special-GL subform ({group}) · ผลรวมต่อฝ่าย/CC/GL อยู่ในชีทสรุป (หน้าแรก) · SAP {board_year} watermark {wm_text}"
        )
        ws["A2"].font = base

        first = 5
        last = max(first, 4 + len(rows_))
        label = ws.cell(row=3, column=first_money_col - 1, value="รวม (ตามตัวกรอง)")
        label.font = Font(name=FONT_NAME, size=10, bold=True)
        label.alignment = Alignment(horizontal="right")
        label.fill = total_fill
        for c in range(first_money_col, first_money_col + 13):
            col = get_column_letter(c)
            cell = ws.cell(row=3, column=c, value=f"=SUBTOTAL(9,{col}{first}:{col}{last})")
            cell.font = Font(name=FONT_NAME, size=10, bold=True)
            cell.number_format = NUM_FMT
            cell.fill = total_fill

        for c, h in enumerate(headers, start=1):
            cell = ws.cell(row=4, column=c, value=h)
            is_topic = n_common < c <= n_common + n_topic
            cell.font = tint_head_font if is_topic else head_font
            cell.fill = tint_head_fill if is_topic else head_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[4].height = 30

        for i, t in enumerate(rows_):
            rn = first + i
            common_vals = [t.department, t.division, t.cost_center, t.cc_name, t.gl_account, t.gl_name, t.side, t.status_label]
            for c, v in enumerate(common_vals, start=1):
                cell = _write_text_cell(ws, rn, c, v if v is not None else "", warnings=warnings)
                cell.font = base
                cell.alignment = top
                if c in (CC_COL, GL_COL):
                    cell.number_format = "@"
            for j, v in enumerate(t.topic_vals):
                c = n_common + 1 + j
                cell = _write_text_cell(ws, rn, c, v if v is not None else "", warnings=warnings)
                cell.font = base
                cell.alignment = top_wrap if topic_headers[j] in WRAP_FIELDS else top
                cell.fill = tint_value_fill
            money_vals = [t.total_year] + list(t.months)
            for j, v in enumerate(money_vals):
                c = first_money_col + j
                cell = ws.cell(row=rn, column=c, value=float(v))
                cell.font = base
                cell.number_format = NUM_FMT
                cell.alignment = top

        for c in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(c)].width = 16 if c <= n_common else (26 if n_common < c <= n_common + n_topic else 12)
        ws.freeze_panes = f"{get_column_letter(first_money_col)}{first}"
        ws.auto_filter.ref = f"A4:{get_column_letter(len(headers))}{last}"
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_title_rows = "4:4"

        sheet_meta[group] = SheetMeta(
            headers=headers, first_money_col=first_money_col, first=first, last=last,
            n_data_rows=len(rows_), swatch=swatch, n_common=n_common, n_topic=n_topic,
            travel_name_col=travel_name_col,
        )
    return sheet_meta


# ---------------------------------------------------------------------------
# PDPA read-back (D7)
# ---------------------------------------------------------------------------
def _fill_rgb(cell) -> str | None:
    fill = cell.fill
    if fill is None or not fill.fill_type or fill.fgColor is None or not fill.fgColor.rgb:
        return None
    return str(fill.fgColor.rgb).upper()


def _scan_pdpa(
    wb: Workbook, sheet1_name: str, sheet_meta: dict[str, SheetMeta],
    traveller_names: set[str], traveller_codes: set[str],
) -> tuple[list[str], list[str]]:
    """D7: system-sourced columns FAIL on '@' / traveller name / traveller
    empcode; USER free-text columns (Remark, รายละเอียด, meta-sourced topic
    columns, trip project/purpose/remark/destination, รายการ) WARN only —
    count + coordinate, never the value (a typed email must never be able to
    block the weekly file by itself). The traveller-NAME column
    (Travelling Expense!ชื่อผู้เดินทาง) is the one PDPA-granted exemption from
    the name check, never from the '@'/empcode checks."""
    failures: list[str] = []
    warnings: list[str] = []
    code_res = [re.compile(rf"(?<![0-9]){re.escape(c)}(?![0-9])") for c in traveller_codes]

    def _check(cell, *, is_free_text: bool, is_name_col: bool, exempt_from_code: bool) -> None:
        v = cell.value
        if not isinstance(v, str):
            return
        coord = cell.coordinate
        level = warnings if is_free_text else failures
        # SEC-F1/OPS-8/SPEC-6 fix round 2026-09-24: sheet!coordinate ONLY,
        # never the value — the ONE column this check exists to catch would
        # otherwise print the caught PII into the (public repo's) CI log.
        if "@" in v:
            level.append(f"PDPA at-sign in {cell.parent.title}!{coord}")
        if not is_name_col and any(n and n in v for n in traveller_names):
            level.append(f"PDPA traveller name in {cell.parent.title}!{coord}")
        if not exempt_from_code and any(rx.search(v) for rx in code_res):
            level.append(f"PDPA traveller empcode in {cell.parent.title}!{coord}")

    free_text_sheet1 = {26, 27}  # Remark, รายละเอียด (fixed sheet-1 layout)
    ws1 = wb[sheet1_name]
    for row in ws1.iter_rows(min_row=1, max_row=ws1.max_row):
        for cell in row:
            _check(
                cell,
                is_free_text=cell.column in free_text_sheet1,
                is_name_col=False,
                exempt_from_code=cell.column in (4, 6),
            )

    for group, meta in sheet_meta.items():
        ws = wb[group]
        headers = meta.headers
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
            for cell in row:
                if cell.column > len(headers):
                    continue
                header = headers[cell.column - 1]
                is_topic = meta.n_common < cell.column <= meta.n_common + meta.n_topic
                is_name_col = group == "Travelling Expense" and cell.column == meta.travel_name_col and cell.row >= meta.first
                is_structured = group == "Travelling Expense" and header in TRAVEL_STRUCTURED_HEADERS
                is_free_text = is_topic and not is_name_col and not is_structured
                _check(
                    cell,
                    is_free_text=is_free_text,
                    is_name_col=is_name_col,
                    exempt_from_code=cell.column in (CC_COL, GL_COL),
                )

    return failures, warnings


# D9/SPEC-4: LITERAL expected hexes, declared independently of
# `app.budget_xlsx.COL_TINT`/`tint50` — the read-back control must never
# import the same table the painter used to paint (SPEC-4's own complaint:
# a bug in the shared table would move the paint AND the check together).
# Sheet-1 X/Y columns 24/25 (งบอนุมัติ/ใช้จริง SAP <board_year>).
_SHEET1_TINT_LITERAL: dict[int, tuple[str, str]] = {
    24: ("FAE7EB", "FDF3F5"),
    25: ("E0D4E7", "F0EAF3"),
}
# Topic-sheet value-column tint per group (header hex = the group's own
# literal `TOPIC_SHEETS` swatch, already independent of the painter).
_TOPIC_TINT_VALUE_HEX: dict[str, str] = {
    "Travelling Expense": "FDF3F5",
    "Professional & Legal Fee": "F0EAF3",
    "Entertainment": "EDF7FB",
    "Training & Seminar": "DEE9F2",
    "Public Relation & Donation": "F7E7ED",
    "Lease & Rental": "E6EEF5",
}

# R8/SPEC-4 fix round 2026-09-24: LITERAL expected header text, written out
# independently of `app.budget_xlsx._sheet1_headers` and of this SAME
# module's own `COMMON_HEADERS`/`TRAVEL_FIELDS`/`TOPIC_META_FIELDS` (the
# constants `_write_topic_sheets` — the PAINTER — actually uses). SPEC-4's
# own complaint was exactly this: the read-back control used to import the
# painter's own tables, so a header RENAME in those tables moved the paint
# and the check together and still published green. These lists must never
# import from, or be derived from, the writer's tables above.
_EXPECTED_SHEET1_HEADERS_STATIC = [
    "ฝ่าย", "สายงาน", "C-Level", "Cost Center", "ชื่อ Cost Center", "GL", "ชื่อ GL", "กลุ่ม GL", "COST/SGA", "สถานะฝ่าย",
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]
_EXPECTED_COMMON_HEADERS = ["ฝ่าย", "สายงาน", "Cost Center", "ชื่อ Cost Center", "GL", "ชื่อ GL", "COST/SGA", "สถานะฝ่าย"]
_EXPECTED_TOPIC_META_HEADERS: dict[str, list[str]] = {
    "Professional & Legal Fee": ["Project", "รายละเอียด"],
    "Entertainment": ["ประเภทการรับรอง", "รายละเอียด"],
    "Training & Seminar": ["หลักสูตรอบรม", "Method"],
    "Public Relation & Donation": ["รายละเอียด"],
    "Lease & Rental": ["ประเภทรถ", "ทะเบียนรถ", "สถานที่ใช้งาน", "กิจกรรม"],
}
_EXPECTED_TRAVEL_HEADERS = [
    "ทริป", "ชื่อผู้เดินทาง", "ประเทศปลายทาง", "Project", "วัตถุประสงค์การเดินทาง", "จำนวนวัน", "เดือนที่เดินทาง", "รายละเอียด", "รายการ",
]
_EXPECTED_MONTH_HEADERS_TH = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _expected_sheet1_headers(planning_year: int) -> list[str]:
    board_year = planning_year - 1
    return _EXPECTED_SHEET1_HEADERS_STATIC + [
        f"รวมปี {planning_year}", f"งบอนุมัติ {board_year}", f"ใช้จริง SAP {board_year} (YTD)", "Remark", "รายละเอียด",
    ]


def _expected_topic_headers(group: str, planning_year: int) -> list[str]:
    topic = _EXPECTED_TRAVEL_HEADERS if group == "Travelling Expense" else _EXPECTED_TOPIC_META_HEADERS[group]
    return _EXPECTED_COMMON_HEADERS + topic + [f"รวมปี {planning_year}"] + _EXPECTED_MONTH_HEADERS_TH


def _check_layout(wb: Workbook, planning_year: int, sheet1_name: str, sheet_meta: dict[str, SheetMeta]) -> list[str]:
    """SPEC-4: restore the prototype's runtime layout read-back controls
    (sheet names/order, row-4 headers, SUBTOTAL(9)-only formulas, CC/GL
    text-typed, freeze/autofilter, tab colours, sheet-1 + topic tints,
    empty-sheet note). Called on the SAVED bytes only (SEC-F7 — the caller
    passes `load_workbook(BytesIO(xlsx_bytes))`, never the in-memory `wb`).

    R8/SPEC-4 fix round 2026-09-24: the header TEXT is now checked against
    LITERAL expected lists declared independently in this module
    (`_expected_sheet1_headers`/`_expected_topic_headers`) — it no longer
    reuses `app.budget_xlsx._sheet1_headers` or this module's own
    `COMMON_HEADERS`/`TRAVEL_FIELDS`/`TOPIC_META_FIELDS` (the writer's own
    tables), so a header rename in either writer FAILs this check instead of
    moving the paint and the check together. Every tint/colour value below
    was already a hardcoded literal, independent of the code that painted
    it."""
    failures: list[str] = []

    expected_sheets = [sheet1_name] + [g for g, _ in TOPIC_SHEETS]
    if wb.sheetnames != expected_sheets:
        failures.append(f"sheet name/order mismatch: expected {expected_sheets} got {wb.sheetnames}")
        return failures  # every other check below indexes sheets by name — bail out loud

    ws1 = wb[sheet1_name]

    # -- row-4 headers per sheet, exactly — against LITERAL expected text
    # (R8/SPEC-4: `_expected_sheet1_headers`/`_expected_topic_headers`
    # above, never the writer's own `_sheet1_headers`/`COMMON_HEADERS`/
    # `TRAVEL_FIELDS`/`TOPIC_META_FIELDS`).
    expected_sheet1_headers = _expected_sheet1_headers(planning_year)
    actual_sheet1_headers = [ws1.cell(row=4, column=c).value for c in range(1, len(expected_sheet1_headers) + 1)]
    if actual_sheet1_headers != expected_sheet1_headers:
        failures.append(f"{sheet1_name}: row-4 headers mismatch: expected {expected_sheet1_headers} got {actual_sheet1_headers}")
    for group, meta in sheet_meta.items():
        ws = wb[group]
        expected_headers = _expected_topic_headers(group, planning_year)
        actual_headers = [ws.cell(row=4, column=c).value for c in range(1, len(expected_headers) + 1)]
        if actual_headers != expected_headers:
            failures.append(f"{group}: row-4 headers mismatch: expected {expected_headers} got {actual_headers}")

    # D6 empty-scope edge: `ws1.max_row` under-counts to 4 (header only) when
    # 0 data rows were ever written (row 5 then has no cell at all), but the
    # writer's own `last = max(first, 4 + len(rows))` still resolves to 5 —
    # floor-clamp to reconstruct that same structural fact without
    # re-deriving it from `len(rows)` (never available here).
    last1 = max(5, ws1.max_row)

    # -- formulas: ONLY row-3 SUBTOTAL(9,...) over the declared range, nowhere else --
    allowed: dict[tuple[str, str], str] = {}
    for c in range(FIRST_NUM_COL, LAST_NUM_COL + 1):
        col = get_column_letter(c)
        allowed[(sheet1_name, f"{col}3")] = f"=SUBTOTAL(9,{col}5:{col}{last1})"
    for group, meta in sheet_meta.items():
        for j in range(13):
            col = get_column_letter(meta.first_money_col + j)
            allowed[(group, f"{col}3")] = f"=SUBTOTAL(9,{col}{meta.first}:{col}{meta.last})"
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f" and (ws.title, cell.coordinate) not in allowed:
                    # N6 fix round 2026-09-24: coordinate ONLY — this guard
                    # tripping means the formula-injection guard (SEC-F3)
                    # regressed, so `cell.value` here could be user-typed
                    # free text; this repo is public, so the cell TEXT must
                    # never reach the FAIL message, only where to look.
                    failures.append(f"unexpected formula outside row-3 SUBTOTAL at {ws.title}!{cell.coordinate}")
    for (sheet, coord), expected_formula in allowed.items():
        cell = wb[sheet][coord]
        if cell.data_type != "f" or cell.value != expected_formula:
            failures.append(f"missing/altered SUBTOTAL(9,...) formula at {sheet}!{coord}: got {cell.value!r}")

    # -- CC / GL columns: text-typed, number_format "@" --
    for name in expected_sheets:
        ws = wb[name]
        cc_col, gl_col = (4, 6) if name == sheet1_name else (CC_COL, GL_COL)
        for r in range(5, ws.max_row + 1):
            for col in (cc_col, gl_col):
                cell = ws.cell(row=r, column=col)
                if cell.value in (None, ""):
                    continue
                if not isinstance(cell.value, str) or cell.number_format != "@":
                    failures.append(
                        f"{name}!{cell.coordinate} (CC/GL) not text-typed: value={cell.value!r} number_format={cell.number_format!r}"
                    )

    # -- freeze panes + autofilter --
    expected_freeze1 = f"{get_column_letter(FIRST_NUM_COL)}5"
    if ws1.freeze_panes != expected_freeze1:
        failures.append(f"{sheet1_name}: freeze_panes expected {expected_freeze1!r} got {ws1.freeze_panes!r}")
    expected_af1 = f"A4:{get_column_letter(ws1.max_column)}{last1}"
    if str(ws1.auto_filter.ref) != expected_af1:
        failures.append(f"{sheet1_name}: autofilter expected {expected_af1!r} got {ws1.auto_filter.ref!r}")
    for group, meta in sheet_meta.items():
        ws = wb[group]
        expected_freeze = f"{get_column_letter(meta.first_money_col)}{meta.first}"
        if ws.freeze_panes != expected_freeze:
            failures.append(f"{group}: freeze_panes expected {expected_freeze!r} got {ws.freeze_panes!r}")
        expected_af = f"A4:{get_column_letter(len(meta.headers))}{meta.last}"
        if str(ws.auto_filter.ref) != expected_af:
            failures.append(f"{group}: autofilter expected {expected_af!r} got {ws.auto_filter.ref!r}")

    # -- empty-sheet note (D6) --
    has_sheet1_rows = ws1.cell(row=5, column=4).value not in (None, "")
    a2 = ws1["A2"].value
    if has_sheet1_rows == (a2 == "ยังไม่มีรายการ"):
        failures.append(f"{sheet1_name}!A2 empty-scope note inconsistent with data rows present={has_sheet1_rows}: {a2!r}")
    for group, meta in sheet_meta.items():
        a2 = wb[group]["A2"].value
        if (meta.n_data_rows == 0) != (a2 == "ยังไม่มีรายการ"):
            failures.append(f"{group}!A2 empty-scope note inconsistent with n_data_rows={meta.n_data_rows}: {a2!r}")

    # -- sheet-1 X/Y tint (header + values), literal hexes --
    for c, (head_hex, value_hex) in _SHEET1_TINT_LITERAL.items():
        head_ok = (_fill_rgb(ws1.cell(row=4, column=c)) or "").endswith(head_hex)
        # row 3 (the SUBTOTAL total) is always painted; data rows only exist
        # when the sheet is non-empty (D6 edge — nothing was ever written to
        # row 5 when `rows` was empty, so checking it would false-positive).
        rows_to_check = [3] + (list(range(5, last1 + 1)) if has_sheet1_rows else [])
        vals_ok = all((_fill_rgb(ws1.cell(row=r, column=c)) or "").endswith(value_hex) for r in rows_to_check)
        if not (head_ok and vals_ok):
            failures.append(f"{sheet1_name}: tint mismatch on column {get_column_letter(c)}: header expected #{head_hex}, values expected #{value_hex}")

    # -- topic tab colour + swatch header (#1F1F1F font) + literal value tint, no fill elsewhere --
    for group, swatch in TOPIC_SHEETS:
        ws = wb[group]
        meta = sheet_meta[group]
        tab = (ws.sheet_properties.tabColor.rgb if ws.sheet_properties.tabColor else None) or ""
        if not str(tab).upper().endswith(swatch):
            failures.append(f"{group}: tab colour expected #{swatch} got {tab!r}")
        value_hex = _TOPIC_TINT_VALUE_HEX[group]
        for c in range(meta.n_common + 1, meta.n_common + meta.n_topic + 1):
            head_cell = ws.cell(row=4, column=c)
            head_fill = _fill_rgb(head_cell) or ""
            if not head_fill.endswith(swatch):
                failures.append(f"{group}!{head_cell.coordinate}: topic header tint expected #{swatch} got {head_fill}")
            font_color = str((head_cell.font.color.rgb if head_cell.font and head_cell.font.color else "") or "")
            if not font_color.upper().endswith("1F1F1F"):
                failures.append(f"{group}!{head_cell.coordinate}: topic header font expected #1F1F1F got {font_color}")
        for r in range(meta.first, meta.first + meta.n_data_rows):  # empty sheet -> no data rows -> nothing to check
            for c in range(1, len(meta.headers) + 1):
                cell = ws.cell(row=r, column=c)
                fill = _fill_rgb(cell)
                is_topic_col = meta.n_common < c <= meta.n_common + meta.n_topic
                if is_topic_col:
                    if not (fill or "").endswith(value_hex):
                        failures.append(f"{group}!{cell.coordinate}: topic value tint expected #{value_hex} got {fill}")
                elif fill:
                    failures.append(f"{group}!{cell.coordinate}: unexpected fill outside topic-detail columns: {fill}")

    return failures


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
def build_officer_workbook(
    fabric_conn: pyodbc.Connection,
    gold_conn: pyodbc.Connection,
    *,
    planning_year: int,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> BuildResult:
    """Build the officer-review workbook and run its runtime PDPA/layout
    controls. The FILE=WEB=FABRIC reconcile itself is a SEPARATE step
    (`app.officer_reconcile.reconcile`, run by the job) — this function only
    builds the artifact and the WEB-side data the reconcile needs."""
    settings = settings or get_settings()
    as_of = now or datetime.now(BANGKOK_TZ)
    board_year = planning_year - 1
    failures: list[str] = []
    warnings: list[str] = []

    gl_master = {g["gl_code"]: g for g in fetch_gl_accounts(fabric_conn)}
    cc_names = {r[0]: r[1] for r in q(fabric_conn, _CC_NAME_SQL)}
    status_by_dept = {r[0]: r[1] for r in q(fabric_conn, _STATUS_BY_DEPT_SQL, planning_year)}
    approved_depts, admin_depts = _resolve_scope_departments(fabric_conn, planning_year, status_by_dept)

    web_rows = _fetch_web_rows(fabric_conn, gold_conn, planning_year, settings, approved_depts, admin_depts)

    all_ccs = sorted({cc for cc, _gl in web_rows})
    cc_dims = fetch_cc_dims(fabric_conn, all_ccs) if all_ccs else {}

    summary_rows, dup_failures = _build_summary_rows(web_rows, cc_dims, cc_names, gl_master, status_by_dept, approved_depts)
    failures.extend(dup_failures)

    detail_by_key, trips_by_id, trip_no_by_id, is_auto_calc_by_id, special_gl_warnings = _fetch_detail_and_trips(
        fabric_conn, planning_year, summary_rows
    )
    warnings.extend(special_gl_warnings)
    summary_rows = _attach_sheet1_detail_text(summary_rows, detail_by_key, trips_by_id, trip_no_by_id, is_auto_calc_by_id)
    topic_rows = _build_topic_rows(summary_rows, detail_by_key, trips_by_id, trip_no_by_id)

    try:
        coverage = resolve_sap_coverage_cached(gold_conn, fiscal_year=board_year, settings=settings)
        sap_watermark = coverage.watermark_date
    except Exception as exc:  # noqa: BLE001 — freshness is informational only, never blocks the build
        logger.warning("officer_workbook: SAP coverage lookup failed, watermark unknown: %s", exc)
        sap_watermark = None

    n_departments = len({r.department for r in summary_rows if r.department and r.department != UNKNOWN_DEPT})

    wb = Workbook()
    ws1 = wb.active
    write_summary_sheet(
        ws1, summary_rows, planning_year=planning_year, as_of=as_of,
        scope_label=SCOPE_LABEL, n_departments=n_departments, sap_watermark=sap_watermark,
        warnings=warnings,
    )
    sheet1_name = ws1.title
    sheet_meta = _write_topic_sheets(wb, topic_rows, planning_year, as_of, sap_watermark, warnings=warnings)
    wb.calculation.fullCalcOnLoad = True
    xlsx_bytes = workbook_bytes(wb)

    # SEC-F7 fix round 2026-09-24: every runtime read-back control below runs
    # on the SAVED BYTES (`load_workbook(BytesIO(xlsx_bytes))`), never the
    # in-memory `wb` — the control must check exactly what gets published,
    # the same rule `app.officer_reconcile._load_file_side` already follows.
    saved_wb = load_workbook(BytesIO(xlsx_bytes))
    failures.extend(_check_layout(saved_wb, planning_year, sheet1_name, sheet_meta))

    traveller_rows = q(fabric_conn, _TRAVELLER_PII_SQL, planning_year)
    traveller_names = {str(n).strip() for n, _c in traveller_rows if n and str(n).strip()}
    traveller_codes = {str(c).strip() for _n, c in traveller_rows if c and str(c).strip()}
    pdpa_failures, pdpa_warnings = _scan_pdpa(saved_wb, sheet1_name, sheet_meta, traveller_names, traveller_codes)
    failures.extend(pdpa_failures)
    warnings.extend(pdpa_warnings)

    grand_total_year = sum(r.total_year for r in summary_rows)
    grand_board_total = sum(r.board_total_year for r in summary_rows)
    grand_sap_total = sum(r.sap_total_year for r in summary_rows)
    lines_per_topic = {group: len(topic_rows.get(group, [])) for group, _ in TOPIC_SHEETS}

    return BuildResult(
        ok=not failures,
        xlsx_bytes=xlsx_bytes,
        failures=failures,
        warnings=warnings,
        as_of=as_of,
        planning_year=planning_year,
        n_departments=n_departments,
        sap_watermark=sap_watermark,
        grand_total_year=grand_total_year,
        grand_board_total=grand_board_total,
        grand_sap_total=grand_sap_total,
        lines_per_topic=lines_per_topic,
        row_keys=frozenset((r.cost_center, r.gl_account) for r in summary_rows),
        web_rows=web_rows,
        detail_by_key=detail_by_key,
        gl_group_by_key={(r.cost_center, r.gl_account): r.gl_group for r in summary_rows},
        department_by_key={(r.cost_center, r.gl_account): r.department for r in summary_rows},
    )
