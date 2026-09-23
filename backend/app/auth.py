"""Entra Easy Auth identity extraction (ADR-0004).

The platform (Container Apps Easy Auth) validates the Entra ID token and
injects `x-ms-client-principal-name` = the logged-in user's email. This
module trusts that header as-is — no JWT validation here, Easy Auth already
did it before the request reached the app.

Locally there is no Easy Auth in front of uvicorn, so a DEV override
(`DEV_AUTH_EMAIL`) is honored, but ONLY when `APP_ENV=local` — it must never
leak into a deployed environment even if the var is set by mistake.

Permanent production impersonation (ADR-0031, 2026-09-23 — supersedes the
2026-08-10/08-17 staging-only design): after a real header resolves an
identity, `SIT_IMPERSONATE` may rewrite it to one of a LIVE, DB-backed set of
target emails — see `_apply_sit_impersonation`. It never runs on the
dev-override or 401 paths, so it can only ever rewrite an already-real Easy
Auth login.
"""
import logging

from fastapi import Cookie, Depends, Header, HTTPException

from app.cache import TTLCache
from app.config import Settings, get_settings
from app.db import get_fabric_conn

PRINCIPAL_NAME_HEADER = "x-ms-client-principal-name"

# The browser cookie that selects WHICH live impersonation target the caller
# is rewritten to (see `_select_sit_target` / `app.routers.sit`).
SIT_COOKIE_NAME = "sit_as"

logger = logging.getLogger(__name__)


def _resolve_raw_identity(x_ms_client_principal_name: str | None, settings: Settings) -> str:
    """The real (non-impersonated) identity: header > local DEV override > 401.

    Shared by `get_current_user_email` (which then applies SIT impersonation
    on top) and `get_real_caller_email` (used only by the SIT admin endpoint,
    `app.routers.sit`, which must see the ACTUAL caller — never an
    already-impersonated identity, or an admin who is already impersonating
    someone could never change or clear their own selection).
    """
    if x_ms_client_principal_name and x_ms_client_principal_name.strip():
        return x_ms_client_principal_name.strip()

    if settings.is_local and settings.dev_auth_email:
        return settings.dev_auth_email

    raise HTTPException(status_code=401, detail="Not authenticated")


def get_current_user_email(
    x_ms_client_principal_name: str | None = Header(default=None, alias=PRINCIPAL_NAME_HEADER),
    sit_as: str | None = Cookie(default=None, alias=SIT_COOKIE_NAME),
    settings: Settings = Depends(get_settings),
) -> str:
    """Resolve the authenticated user's email, or raise 401.

    Priority: real Easy Auth header (subject to SIT impersonation) >
    local DEV override > 401. SIT impersonation only ever applies to the
    header-resolved path.
    """
    if x_ms_client_principal_name and x_ms_client_principal_name.strip():
        email = x_ms_client_principal_name.strip()
        return _apply_sit_impersonation(email, settings, cookie_target=sit_as)

    return _resolve_raw_identity(x_ms_client_principal_name, settings)


def get_real_caller_email(
    x_ms_client_principal_name: str | None = Header(default=None, alias=PRINCIPAL_NAME_HEADER),
    settings: Settings = Depends(get_settings),
) -> str:
    """The ACTUAL Easy-Auth identity, bypassing SIT impersonation entirely.

    Used only by `app.routers.sit` (the SIT admin endpoint that lets a
    caller choose which impersonation target the `sit_as` cookie selects) —
    that endpoint must authorize and log the REAL caller, not whoever they
    are currently impersonating.
    """
    return _resolve_raw_identity(x_ms_client_principal_name, settings)


def _sit_guard_ok(email: str, settings: Settings) -> bool:
    """Three required conditions for SIT impersonation (defense in depth,
    order matters):

    1. HARD: `app_env` is NOT "production" — the canonical environment
       discriminator (PRD=production, stg=local, verified 2026-08-10).
       Identity-rewrite can never run on PRD no matter what the other
       settings hold. Prd deliberately runs `app_env=uat` (ADR-0031), which
       is why impersonation is live there by design, not by accident.
    2. The resolved caller email is in `settings.admin_emails_set`. This is
       NECESSARY but NOT SUFFICIENT: it only rules out a non-admin
       entirely. The caller must ALSO equal the configured `from_email` —
       enforced separately, by `sit_targets_for` and
       `_apply_sit_impersonation` below — so a DIFFERENT admin (e.g.
       `piyadad@chememan.com`) is refused too (2026-08-18 gate fix: this
       guard alone must never be read as "any admin may impersonate").
    3. `sit_impersonate` is set at all (well-formedness of the from-email
       is checked separately by `_parse_sit_from_email`).

    Any one of these failing => passthrough (real Easy Auth identity kept).
    """
    if settings.app_env.strip().lower() == "production":
        return False
    if email.lower() not in settings.admin_emails_set:
        return False
    if not settings.sit_impersonate:
        return False
    return True


def _parse_sit_from_email(raw: str) -> str | None:
    """Parses `SIT_IMPERSONATE`'s from-side only (ADR-0031 — WHO may be
    impersonated is no longer this env var's job, see `live_sit_targets`).

    Accepts a bare email with no colon at all (the new, minimal grammar) as
    well as the legacy "from_email:target1,target2,..." shape (everything
    from the first ':' onward is ignored, so the live prd value keeps
    working unedited). Blank/whitespace-only from-side => `None` (off).
    """
    if not raw or not raw.strip():
        return None
    from_email = raw.split(":", 1)[0].strip()
    return from_email or None


# --- Live impersonation target set (ADR-0031) ------------------------------
# Every distinct Filler email in `dbo.cc_filler_map` UNION each Filler's
# PRIMARY-row `dbo.v_employee_budget_01.manager_email` (ADR-0031 names the
# Primary-row manager specifically, matching `app.approval.resolve_submitter`
# and the project's own primary-manager rule) — 95 people on 2026-09-23 (74
# Fillers + 21 managers who are not Fillers). `is_primary_row = 1` is
# defense in depth, not a live filter today: live-verified 2026-09-23, every
# row in `dbo.v_employee_budget_01` already has `is_primary_row = 1` (the
# view is pre-filtered upstream), so this clause is currently a no-op but
# guards against that assumption ever silently breaking. Both source tables
# are read for RLS too (see `app.rls._FILL_SQL` / `_MANAGER_SEE_ADD_SQL`),
# but this query answers a different question ("who may ever be a target",
# a global set) rather than "one caller's own scope" — kept separate on
# purpose.
_SIT_LIVE_TARGETS_SQL = """
    SELECT DISTINCT LOWER(LTRIM(RTRIM(filler_email))) AS target_email
    FROM dbo.cc_filler_map
    WHERE filler_email IS NOT NULL AND LTRIM(RTRIM(filler_email)) <> ''

    UNION

    SELECT DISTINCT LOWER(LTRIM(RTRIM(e.manager_email))) AS target_email
    FROM dbo.cc_filler_map f
    JOIN dbo.v_employee_budget_01 e
      ON LOWER(LTRIM(RTRIM(e.email))) = LOWER(LTRIM(RTRIM(f.filler_email)))
    WHERE e.manager_email IS NOT NULL AND LTRIM(RTRIM(e.manager_email)) <> ''
      AND e.is_primary_row = 1
"""

_SIT_TARGETS_CACHE_KEY = "live_targets"
_sit_targets_cache: TTLCache[frozenset[str]] = TTLCache()


def clear_sit_targets_cache() -> None:
    """Test-only reset — mirrors `app.sap.clear_sap_caches`."""
    _sit_targets_cache.clear()


def _query_live_sit_targets(settings: Settings) -> frozenset[str]:
    """One-shot DB read behind `live_sit_targets`'s cache. Opens (and
    closes) its own connection — this only ever runs once the SIT guard has
    already passed, never on an ordinary request."""
    with get_fabric_conn(settings) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(_SIT_LIVE_TARGETS_SQL)
            return frozenset(row[0] for row in cursor.fetchall() if row[0])
        finally:
            cursor.close()


def live_sit_targets(settings: Settings) -> frozenset[str]:
    """The live, TTL-cached (`settings.sit_targets_cache_ttl_seconds`) set of
    lower-cased impersonation target emails.

    Raises on a connection/query failure — `pyodbc.Error`, or whatever the
    msal token acquisition the connection depends on raises (not
    necessarily a pyodbc type; see `app.db._acquire_access_token`). Callers
    that must fail closed (i.e. `_apply_sit_impersonation`, which runs on
    every authenticated request once a cookie is present) use
    `_live_sit_targets_fail_closed` instead. `app.routers.sit` calls this
    directly so a hiccup on the picker page surfaces as a 503, not a
    silently empty list."""
    return _sit_targets_cache.get_or_load(
        _SIT_TARGETS_CACHE_KEY,
        settings.sit_targets_cache_ttl_seconds,
        lambda: _query_live_sit_targets(settings),
    )


def _live_sit_targets_fail_closed(settings: Settings) -> frozenset[str]:
    """`live_sit_targets`, but ANY failure logs a WARNING and returns an
    empty set instead of raising (ADR-0031 item 5) — used only by
    `_apply_sit_impersonation`, where a hiccup must never break an
    otherwise-ordinary request. Catches `Exception`, not just
    `pyodbc.Error`: the underlying connection also does an msal token
    acquisition (`app.db._acquire_access_token`) before pyodbc is ever
    involved, and a network failure there raises whatever msal/requests
    raises, not a pyodbc type — narrower handling would 500 every
    jakkaritw request while a `sit_as` cookie is set (gate finding,
    2026-09-23). The failed load is never cached (see `TTLCache`
    docstring), so the very next call retries the DB."""
    try:
        return live_sit_targets(settings)
    except Exception:
        logger.warning("auth: failed to load live SIT impersonation targets from the DB", exc_info=True)
        return frozenset()


def _select_sit_target(targets: frozenset[str] | list[str], cookie_target: str | None, self_email: str) -> str:
    """Default = `self_email` (ADR-0031 — no more `targets[0]` fallback: the
    from-email, e.g. jakkaritw, is never itself a member of the live target
    set). A `cookie_target` matching one of `targets` (case-insensitive)
    overrides the default. A missing/blank cookie is the silent default
    case; a cookie that no longer matches any LIVE target (e.g. someone
    dropped from `cc_filler_map`, or an old hand-typed target like
    `pornthipp@chememan.com`) falls back to `self_email` and logs a
    warning — never raises."""
    if not cookie_target or not cookie_target.strip():
        return self_email

    cookie_target = cookie_target.strip()
    for target in targets:
        if target.lower() == cookie_target.lower():
            return target

    logger.warning(
        "auth: sit_as cookie %r is not a live SIT impersonation target, using self (%s)",
        cookie_target,
        self_email,
    )
    return self_email


def sit_targets_for(email: str, settings: Settings) -> list[str] | None:
    """The sorted live impersonation target list (ADR-0031), if `email`
    satisfies the SIT guard (non-prod, admin caller, `SIT_IMPERSONATE` set)
    AND equals the configured from-email — else `None`.

    The from-email check keeps this EXACTLY as strict as
    `_apply_sit_impersonation`'s own rewrite gate: `_sit_guard_ok` alone
    only proves "some admin", which is necessary but not sufficient — a
    different admin than the configured from-email must be refused here
    too, otherwise the router would let someone enumerate/impersonate on
    behalf of an identity that can never actually be rewritten.

    Used by `app.routers.sit` to 404 the endpoint's existence for an
    authenticated caller the guard refuses (never 403 — indistinguishable
    from a route that does not exist), to enumerate the picker's rows, and
    to validate a POSTed target. Touches the DB (via `live_sit_targets`) —
    callers must let any exception it raises propagate to a 503, per
    ADR-0031; UNLIKE `_apply_sit_impersonation`, this is never called on an
    ordinary request, only from the two SIT admin endpoints.
    """
    if not _sit_guard_ok(email, settings):
        return None

    from_email = _parse_sit_from_email(settings.sit_impersonate)
    if from_email is None:
        return None
    if email.lower() != from_email.lower():
        return None

    return sorted(live_sit_targets(settings))


def _apply_sit_impersonation(email: str, settings: Settings, cookie_target: str | None = None) -> str:
    """Rewrite `email` to a live impersonation target if it matches the
    configured from-email and the guard (`_sit_guard_ok`) passes, else
    return `email` unchanged. See module docstring + `_sit_guard_ok` for the
    three required conditions.

    DB is touched ONLY once the guard has passed AND a non-blank cookie is
    present (ADR-0031 item 5) — the overwhelmingly common case (no cookie,
    or a non-admin/prod request) never reaches Fabric at all. Fails closed:
    a DB error leaves `email` unchanged and logs a warning, never raises.
    """
    if not _sit_guard_ok(email, settings):
        return email

    from_email = _parse_sit_from_email(settings.sit_impersonate)
    if from_email is None:
        logger.warning("auth: SIT_IMPERSONATE has no from-email (expected 'from_email' or 'from_email:...'): %r", settings.sit_impersonate)
        return email
    if email.lower() != from_email.lower():
        return email

    if not cookie_target or not cookie_target.strip():
        return email

    targets = _live_sit_targets_fail_closed(settings)
    target = _select_sit_target(targets, cookie_target, self_email=email)
    if target != email:
        logger.info("auth: SIT impersonation %s -> %s", email, target)
    return target
