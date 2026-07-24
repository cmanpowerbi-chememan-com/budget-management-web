"""FX reconciliation job — re-persist every fiscal_year trip's STORED
per-diem with the CURRENT `dbo.master_currency_rate` FX (financial-critical,
GATE decision 2026-07-24, `docs/specs/feature-fx-repersist-perdiem.md`).

Problem this closes: per-diem is recompute-on-read only (ADR-0015) — after an
admin changes a year's FX, the trip SUBFORM shows the new number immediately,
but the STORED per-diem line in `budget.pending_budget_detail` and its parent
cell in `budget.pending_budget` (which the main GRID renders) keep the OLD
number until the trip is manually re-saved. This job closes that gap for the
stored value, once, per fiscal_year, on demand.

**RECONCILIATION, NOT A USER EDIT — re-prices ALL trips regardless of
approval status.** jakkaritw's GATE decision (2026-07-24) chose this over the
feature design doc's own default (`feature-fx-repersist-perdiem.md` §6/§12
Q1, which proposed skipping PENDING_APPROVER*/APPROVED departments to honor
ADR-0013's edit-lock) and instead sides with ADR-0015's original "an FX edit
re-prices ALL overseas per-diem incl APPROVED, every department." A background
FX correction is a system-level currency fix, not a live user edit — it does
NOT call `write_model._ensure_department_not_locked` and never looks up
`budget.approval_status` at all. **This is a deliberate divergence from
`write_model._save_one_trip`'s user-facing save path, not an oversight.**
This exception is recorded in both ADRs (shipped in this same changeset,
2026-07-24): `docs/adr/0013-editing-never-changes-status.md` (addendum —
this job is an explicit exception to the edit-lock) and
`docs/adr/0015-fx-recompute-on-read.md` (addendum — this job is the
mechanism that persists the "re-price ALL incl APPROVED" decision to the
stored DB value).

Reuses the SAME formula (`app.per_diem.derive_per_diem`) and the SAME
persistence primitives (`app.write_model._upsert_trip_detail_line` +
`_recompute_parent_cell`) as the user-facing trip save path — this module
never re-implements the split/rounding rule.

Rate policy (decision 3): a trip whose traveler position has NO
`dbo.per_diem_rate` row is a data gap — skip that ONE trip, log a WARNING,
count it, and keep going. A PRESENT rate (including a legitimate 0) is used
as-is. This is different from a missing FX for the whole year (decision =
fail loud, see `FxRateMissingError` below) — one is a per-trip config gap,
the other means nothing in the run can be trusted.

A trip with malformed stored data (empty `travel_months`, or a
`country_group` outside {1,2,3} — should never happen given the DB CHECK
constraint, but a stale/hand-edited row is a real possibility) makes
`derive_per_diem` raise `ValueError`. That is a PER-TRIP data gap too, not a
reason to abort the whole fiscal year's re-price — caught the same way as
`subform_read.fetch_trips` catches it on the read path, counted separately
as `skipped_invalid`, logged, and the batch continues.

Domestic trips (`country_group=1`, decision 4) always use FX=1, so a
USD-rate change never affects them — skipped for every run, reported
separately so "0 domestic touched" is visibly a choice, not a miss.

Run (from `backend/`):
    python -m jobs.repersist_perdiem_fx --fiscal-year 2027         # dry-run preview (default)
    python -m jobs.repersist_perdiem_fx --fiscal-year 2027 --run   # actually write
"""
import argparse
import logging
from datetime import datetime, timezone
from decimal import Decimal

from app.db import get_fabric_conn
from app.per_diem import MissingPerDiemRateError, derive_per_diem
from app.write_model import (
    PER_DIEM_GL_BY_SIDE,
    _derive_dim_snapshot,
    _lookup_fx,
    _lookup_per_diem_rate,
    _recompute_parent_cell,
    _upsert_trip_detail_line,
)
from jobs.common import configure_logging

logger = logging.getLogger("jobs.repersist_perdiem_fx")

_DOMESTIC_COUNTRY_GROUP = 1
_REPERSIST_ACTOR_EMAIL = "system:fx_repersist"
_PREVIEW_LIMIT = 20  # cap the per-trip old->new list in the summary; full counts are unabridged

_TRIP_COLUMNS: tuple[str, ...] = ("trip_id", "cost_center", "side", "position", "country_group", "days", "travel_months")


class FxRateMissingError(RuntimeError):
    """No `dbo.master_currency_rate` row for the fiscal_year. Fail loud and
    abort the WHOLE run (never re-persist with an invented fallback rate,
    same philosophy as `per_diem.MissingFxRateError`) — a "0 re-priced"
    success would otherwise hide a real config error."""


def _fetch_trips_for_year(conn, fiscal_year: int) -> list[dict]:
    """Every `budget.budget_trip` row for `fiscal_year`, regardless of side
    or approval status (decision 1 — no department-lock filter here).
    `position` is the trip's own stored job-level snapshot (subform_read.py
    `_TRIP_COLUMNS`), so no `_lookup_traveler` round-trip is needed."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT {', '.join(_TRIP_COLUMNS)} FROM budget.budget_trip WHERE fiscal_year = ? ORDER BY trip_id",
            fiscal_year,
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    trips = []
    for row in rows:
        trip = dict(zip(_TRIP_COLUMNS, row))
        trip["travel_months"] = trip["travel_months"].split(",") if trip["travel_months"] else []
        trips.append(trip)
    return trips


def _fetch_current_total(conn, trip_id: int, gl_account: str) -> float:
    """The per-diem detail line's currently-stored `total_year` for
    (trip_id, gl_account), or 0.0 if no line exists yet — the "old" side of
    the old->new report and the THB-delta calculation."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT total_year FROM budget.pending_budget_detail WHERE trip_id = ? AND gl_account = ?",
            trip_id, gl_account,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    return float(row[0]) if row else 0.0


def run(fiscal_year: int, dry_run: bool) -> dict:
    """Re-persist per-diem for every overseas trip of `fiscal_year`. Returns
    a summary dict: `scanned, repriced, skipped_domestic,
    skipped_missing_rate, skipped_invalid, total_delta_thb, preview`
    (preview = per-trip old->new for up to `_PREVIEW_LIMIT` trips, populated
    in both modes).

    Uses ONE connection for the whole run; each trip's write commits on its
    own (per-trip isolation, same idiom as `auto_submit`/`auto_escalate` —
    one trip's failure never aborts the batch)."""
    with get_fabric_conn() as conn:
        fx = _lookup_fx(conn, fiscal_year)
        if fx is None:
            raise FxRateMissingError(
                f"no dbo.master_currency_rate row for fiscal_year={fiscal_year} — "
                "cannot re-price overseas trips; aborting without touching anything "
                "(never a fallback rate)"
            )

        trips = _fetch_trips_for_year(conn, fiscal_year)
        scanned = len(trips)
        repriced = 0
        skipped_domestic = 0
        skipped_missing_rate = 0
        skipped_invalid = 0
        total_delta = Decimal("0.00")
        preview: list[dict] = []

        logger.info("fiscal_year=%s fx=%s: %d trip(s) found, dry_run=%s", fiscal_year, fx, scanned, dry_run)

        for trip in trips:
            trip_id = trip["trip_id"]

            if trip["country_group"] == _DOMESTIC_COUNTRY_GROUP:
                skipped_domestic += 1
                continue

            # F1/R1 fix: derive_per_diem AND the side->GL lookup both live
            # INSIDE this guard — a single malformed row (empty
            # travel_months, an out-of-range country_group, OR a
            # corrupted/legacy `side` not in {"COST","SGA"}) must never
            # propagate a ValueError/KeyError out of run() and abort a whole
            # fiscal year's re-price mid-batch (mirrors subform_read.fetch_trips'
            # per-trip try/except on the read path). `side` is DB-CHECK-constrained
            # to COST/SGA (db/ddl/budget_transactional_tables.sql
            # ck_budget_trip_side) so this should never fire live — the guard
            # exists for a stale/hand-edited row, same reasoning as ValueError above.
            try:
                rate_row = _lookup_per_diem_rate(conn, trip["position"])
                months = derive_per_diem(
                    days=trip["days"], country_group=trip["country_group"], rate_row=rate_row,
                    fx_rate=fx, travel_months=trip["travel_months"],
                )
                gl_account = PER_DIEM_GL_BY_SIDE[trip["side"]]
            except MissingPerDiemRateError:
                skipped_missing_rate += 1
                logger.warning(
                    "trip_id=%s cost_center=%s position=%r has no dbo.per_diem_rate row — "
                    "skipping this trip (data gap), continuing with the rest",
                    trip_id, trip["cost_center"], trip["position"],
                )
                continue
            except ValueError as exc:
                skipped_invalid += 1
                logger.warning(
                    "trip_id=%s cost_center=%s has malformed stored data (%s) — "
                    "skipping this trip (data gap), continuing with the rest",
                    trip_id, trip["cost_center"], exc,
                )
                continue
            except KeyError:
                skipped_invalid += 1
                logger.warning(
                    "trip_id=%s cost_center=%s has an invalid side=%r (not COST/SGA) — "
                    "skipping this trip (data gap), continuing with the rest",
                    trip_id, trip["cost_center"], trip["side"],
                )
                continue

            new_total = round(sum(months.values()), 2)
            old_total = _fetch_current_total(conn, trip_id, gl_account)
            delta = Decimal(str(new_total)) - Decimal(str(old_total))

            if len(preview) < _PREVIEW_LIMIT:
                preview.append({
                    "trip_id": trip_id, "cost_center": trip["cost_center"],
                    "old_total": old_total, "new_total": new_total, "delta": float(delta),
                })

            if dry_run:
                logger.info(
                    "[DRY-RUN] trip_id=%s cost_center=%s gl=%s: %.2f -> %.2f (delta %+.2f)",
                    trip_id, trip["cost_center"], gl_account, old_total, new_total, delta,
                )
            else:
                now = datetime.now(timezone.utc)
                try:
                    _upsert_trip_detail_line(
                        conn, trip_id, trip["cost_center"], gl_account, fiscal_year,
                        months, _REPERSIST_ACTOR_EMAIL, now,
                    )
                    dims = _derive_dim_snapshot(conn, trip["cost_center"], gl_account)
                    _recompute_parent_cell(conn, trip["cost_center"], gl_account, fiscal_year, dims, _REPERSIST_ACTOR_EMAIL, now)
                    conn.commit()
                except Exception:
                    conn.rollback()
                    logger.exception(
                        "re-persist failed for trip_id=%s cost_center=%s — continuing with next trip",
                        trip_id, trip["cost_center"],
                    )
                    continue
                logger.info(
                    "re-persisted trip_id=%s cost_center=%s gl=%s: %.2f -> %.2f (delta %+.2f)",
                    trip_id, trip["cost_center"], gl_account, old_total, new_total, delta,
                )

            repriced += 1
            total_delta += delta

        summary = {
            "fiscal_year": fiscal_year,
            "fx_rate": float(fx),
            "scanned": scanned,
            "repriced": repriced,
            "skipped_domestic": skipped_domestic,
            "skipped_missing_rate": skipped_missing_rate,
            "skipped_invalid": skipped_invalid,
            "total_delta_thb": float(total_delta),
            "preview": preview,
        }
        logger.info(
            "fiscal_year=%s fx=%s: scanned=%d repriced=%d skipped_domestic=%d skipped_missing_rate=%d "
            "skipped_invalid=%d total_delta_thb=%.2f dry_run=%s",
            fiscal_year, fx, scanned, repriced, skipped_domestic, skipped_missing_rate, skipped_invalid,
            float(total_delta), dry_run,
        )
        return summary


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(
        description=(
            "FX reconciliation: re-persist every fiscal_year trip's stored per-diem with the "
            "CURRENT dbo.master_currency_rate FX. Re-prices ALL trips regardless of approval "
            "status (GATE decision 2026-07-24) — see module docstring."
        )
    )
    parser.add_argument("--fiscal-year", type=int, required=True, help="the fiscal year to re-persist (no auto-detect)")
    parser.add_argument(
        "--run", action="store_true",
        help="actually write (default: dry-run preview only, never-cut safety rule)",
    )
    args = parser.parse_args()
    dry_run = not args.run

    logger.info("starting repersist_perdiem_fx fiscal_year=%s dry_run=%s", args.fiscal_year, dry_run)
    try:
        summary = run(args.fiscal_year, dry_run=dry_run)
    except FxRateMissingError as exc:
        logger.error(str(exc))
        return 1

    logger.info("done: %s", summary)

    # F3 (design-intent, docs/specs/feature-fx-repersist-perdiem.md §8/§10):
    # a data-gap skip (missing rate / malformed row) must stay visible in CI
    # even though it didn't abort the run — non-zero exit ON TOP of the
    # already-logged summary, never instead of it. A clean run (0 skips)
    # stays exit 0.
    if summary["skipped_missing_rate"] > 0 or summary["skipped_invalid"] > 0:
        logger.warning(
            "exiting non-zero: %d missing-rate + %d invalid-data skip(s) occurred this run — see WARNING lines above",
            summary["skipped_missing_rate"], summary["skipped_invalid"],
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
