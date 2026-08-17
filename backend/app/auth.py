"""Entra Easy Auth identity extraction (ADR-0004).

The platform (Container Apps Easy Auth) validates the Entra ID token and
injects `x-ms-client-principal-name` = the logged-in user's email. This
module trusts that header as-is — no JWT validation here, Easy Auth already
did it before the request reached the app.

Locally there is no Easy Auth in front of uvicorn, so a DEV override
(`DEV_AUTH_EMAIL`) is honored, but ONLY when `APP_ENV=local` — it must never
leak into a deployed environment even if the var is set by mistake.

SIT impersonation (2026-08-10, staging test aid; guard redesigned + grammar
extended 2026-08-17): after a real header resolves an identity,
`SIT_IMPERSONATE` may rewrite it to one of the configured target emails —
see `_apply_sit_impersonation`. It never runs on the dev-override or 401
paths, so it can only ever rewrite an already-real Easy Auth login.
"""
import logging

from fastapi import Cookie, Depends, Header, HTTPException

from app.config import Settings, get_settings

PRINCIPAL_NAME_HEADER = "x-ms-client-principal-name"

# The browser cookie that selects WHICH configured SIT_IMPERSONATE target the
# caller is rewritten to (see `_select_sit_target` / `app.routers.sit`).
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
       settings hold.
    2. The resolved caller email is in `settings.admin_emails_set` (2026-08-17
       redesign — replaces the old `notifications_environment_label`
       check, which staging now removes so SIT mail looks byte-identical
       to production; see `.claude/plan.md`). This is NECESSARY but NOT
       SUFFICIENT: it only rules out a non-admin entirely. The caller must
       ALSO equal the configured `from_email` — enforced separately, by
       `sit_targets_for` and `_apply_sit_impersonation` below — so a
       DIFFERENT admin (e.g. `piyadad@chememan.com`) is refused too
       (2026-08-18 gate fix: this guard alone must never be read as "any
       admin may impersonate").
    3. `sit_impersonate` is set at all (well-formedness is checked
       separately by `_parse_sit_impersonate`).

    Any one of these failing => passthrough (real Easy Auth identity kept).
    """
    if settings.app_env.strip().lower() == "production":
        return False
    if email.lower() not in settings.admin_emails_set:
        return False
    if not settings.sit_impersonate:
        return False
    return True


def _parse_sit_impersonate(raw: str) -> tuple[str, list[str]] | None:
    """Parse `SIT_IMPERSONATE`'s "from_email:target1[,target2,...]" grammar.

    Returns `(from_email, [targets])`, or `None` if malformed (missing
    colon, empty from-side, or no non-blank target). Backward compatible
    with the original single-target "from:to" form (a 1-element list).
    """
    if ":" not in raw:
        return None

    from_email, _, targets_raw = raw.partition(":")
    from_email = from_email.strip()
    if not from_email:
        return None

    targets = [t.strip() for t in targets_raw.split(",") if t.strip()]
    if not targets:
        return None

    return from_email, targets


def _select_sit_target(targets: list[str], cookie_target: str | None) -> str:
    """Default = `targets[0]`. A `cookie_target` matching one of `targets`
    (case-insensitive) overrides the default; an unknown/blank cookie value
    falls back to `targets[0]` and logs a warning — never raises."""
    if not cookie_target or not cookie_target.strip():
        return targets[0]

    cookie_target = cookie_target.strip()
    for target in targets:
        if target.lower() == cookie_target.lower():
            return target

    logger.warning(
        "auth: sit_as cookie %r does not match any configured SIT_IMPERSONATE target, "
        "using the default",
        cookie_target,
    )
    return targets[0]


def sit_targets_for(email: str, settings: Settings) -> list[str] | None:
    """The configured impersonation target list, if `email` currently
    satisfies the SIT guard (non-prod, admin caller, `SIT_IMPERSONATE` set
    and well-formed) AND equals the configured `from_email` — else `None`.

    The `from_email` check (2026-08-18 gate fix) keeps this EXACTLY as
    strict as `_apply_sit_impersonation`'s own rewrite gate: `_sit_guard_ok`
    alone only proves "some admin", which is necessary but not sufficient —
    a different admin than the one `SIT_IMPERSONATE` names must be refused
    here too, otherwise the router would let someone impersonate on behalf
    of an identity that can never actually be rewritten.

    Used by `app.routers.sit` to 404 the endpoint's existence for an
    authenticated caller the guard refuses (never 403 — indistinguishable
    from a route that does not exist) and to validate a requested target
    against the allowlist. Note this does NOT change the 401 an
    UNAUTHENTICATED caller (no header, no local DEV override) still gets
    from `get_real_caller_email` before this function is ever reached —
    every protected route in this app answers the same way to a bare probe.
    """
    if not _sit_guard_ok(email, settings):
        return None

    parsed = _parse_sit_impersonate(settings.sit_impersonate)
    if parsed is None:
        return None

    from_email, targets = parsed
    if email.lower() != from_email.lower():
        return None

    return targets


def _apply_sit_impersonation(email: str, settings: Settings, cookie_target: str | None = None) -> str:
    """Rewrite `email` to one of `SIT_IMPERSONATE`'s configured targets if it
    matches the from_email and the guard (`_sit_guard_ok`) passes, else
    return `email` unchanged. See module docstring + `_sit_guard_ok` for the
    three required conditions.
    """
    if not _sit_guard_ok(email, settings):
        return email

    parsed = _parse_sit_impersonate(settings.sit_impersonate)
    if parsed is None:
        logger.warning("auth: SIT_IMPERSONATE malformed (expected 'from:to[,to2,...]'): %r", settings.sit_impersonate)
        return email

    from_email, targets = parsed
    if email.lower() != from_email.lower():
        return email

    target = _select_sit_target(targets, cookie_target)
    logger.info("auth: SIT impersonation %s -> %s", email, target)
    return target
