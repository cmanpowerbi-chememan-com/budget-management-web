"""Entra Easy Auth identity extraction (ADR-0004).

The platform (Container Apps Easy Auth) validates the Entra ID token and
injects `x-ms-client-principal-name` = the logged-in user's email. This
module trusts that header as-is — no JWT validation here, Easy Auth already
did it before the request reached the app.

Locally there is no Easy Auth in front of uvicorn, so a DEV override
(`DEV_AUTH_EMAIL`) is honored, but ONLY when `APP_ENV=local` — it must never
leak into a deployed environment even if the var is set by mistake.
"""
from fastapi import Depends, Header, HTTPException

from app.config import Settings, get_settings

PRINCIPAL_NAME_HEADER = "x-ms-client-principal-name"


def get_current_user_email(
    x_ms_client_principal_name: str | None = Header(default=None, alias=PRINCIPAL_NAME_HEADER),
    settings: Settings = Depends(get_settings),
) -> str:
    """Resolve the authenticated user's email, or raise 401.

    Priority: real Easy Auth header > local DEV override > 401.
    """
    if x_ms_client_principal_name and x_ms_client_principal_name.strip():
        return x_ms_client_principal_name.strip()

    if settings.is_local and settings.dev_auth_email:
        return settings.dev_auth_email

    raise HTTPException(status_code=401, detail="Not authenticated")
