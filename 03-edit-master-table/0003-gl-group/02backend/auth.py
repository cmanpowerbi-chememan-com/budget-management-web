"""SWA principal header auth with email allowlist.

Reads ADMIN_EMAILS env var (comma-separated) to check access.
Persistent across redeployments — no SWA invitation roles needed.
"""
import base64
import json
import os


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


def _allowed_emails() -> set:
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def authenticate(req) -> dict:
    """Read SWA-injected principal, check email allowlist. Raise AuthError on failure."""
    header = req.headers.get("x-ms-client-principal", "")
    if not header:
        raise AuthError(401, "Not authenticated")

    try:
        principal = json.loads(base64.b64decode(header).decode("utf-8"))
    except Exception:
        raise AuthError(401, "Invalid principal header")

    email = principal.get("userDetails", "").lower()
    if not email:
        raise AuthError(401, "No user identity found")

    allowed = _allowed_emails()
    if allowed and email not in allowed:
        raise AuthError(403, "Forbidden — not in admin list")

    return {
        "sub":   principal.get("userId", ""),
        "email": email,
    }
