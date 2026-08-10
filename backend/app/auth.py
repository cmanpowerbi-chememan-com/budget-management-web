"""Entra Easy Auth identity extraction (ADR-0004).

The platform (Container Apps Easy Auth) validates the Entra ID token and
injects `x-ms-client-principal-name` = the logged-in user's email. This
module trusts that header as-is — no JWT validation here, Easy Auth already
did it before the request reached the app.

Locally there is no Easy Auth in front of uvicorn, so a DEV override
(`DEV_AUTH_EMAIL`) is honored, but ONLY when `APP_ENV=local` — it must never
leak into a deployed environment even if the var is set by mistake.

SIT impersonation (2026-08-10, staging test aid): after a real header
resolves an identity, `SIT_IMPERSONATE` may rewrite it to another email —
see `_apply_sit_impersonation`. It never runs on the dev-override or 401
paths, so it can only ever rewrite an already-real Easy Auth login.
"""
import logging

from fastapi import Depends, Header, HTTPException

from app.config import Settings, get_settings

PRINCIPAL_NAME_HEADER = "x-ms-client-principal-name"

logger = logging.getLogger(__name__)


def get_current_user_email(
    x_ms_client_principal_name: str | None = Header(default=None, alias=PRINCIPAL_NAME_HEADER),
    settings: Settings = Depends(get_settings),
) -> str:
    """Resolve the authenticated user's email, or raise 401.

    Priority: real Easy Auth header (subject to SIT impersonation) >
    local DEV override > 401.
    """
    if x_ms_client_principal_name and x_ms_client_principal_name.strip():
        email = x_ms_client_principal_name.strip()
        return _apply_sit_impersonation(email, settings)

    if settings.is_local and settings.dev_auth_email:
        return settings.dev_auth_email

    raise HTTPException(status_code=401, detail="Not authenticated")


def _apply_sit_impersonation(email: str, settings: Settings) -> str:
    """Rewrite `email` to `SIT_IMPERSONATE`'s to_email if it matches the
    from_email, else return `email` unchanged.

    Guard (defense in depth — three conditions, ALL required):
    1. `app_env` is NOT "production" — the canonical environment
       discriminator (PRD=production, stg=local, verified 2026-08-10). This
       is the HARD guard: identity-rewrite can never run on PRD no matter
       what the other two vars hold.
    2. `notifications_environment_label` non-blank — the existing
       non-production mail marker (blank on PRD, ' on stg server' on stg);
       a second, independent signal that this is a test environment.
    3. `sit_impersonate` set — the actual alias.
    Any one of these missing => passthrough (real Easy Auth identity kept).
    """
    if settings.app_env.strip().lower() == "production":
        return email
    if not settings.sit_impersonate or not settings.notifications_environment_label.strip():
        return email

    raw = settings.sit_impersonate
    if ":" not in raw:
        logger.warning("auth: SIT_IMPERSONATE malformed (missing ':'): %r", raw)
        return email

    from_email, _, to_email = raw.partition(":")
    from_email = from_email.strip()
    to_email = to_email.strip()
    if not from_email or not to_email:
        logger.warning("auth: SIT_IMPERSONATE malformed (empty side): %r", raw)
        return email

    if email.lower() != from_email.lower():
        return email

    logger.info("auth: SIT impersonation %s -> %s", email, to_email)
    return to_email
