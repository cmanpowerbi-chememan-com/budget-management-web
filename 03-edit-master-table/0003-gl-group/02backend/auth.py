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
    """Read SWA-injected headers, check email allowlist. Raise AuthError on failure."""
    # x-ms-client-principal-name gives the email/UPN directly — preferred path.
    # More reliable than decoding x-ms-client-principal for dynamic-route endpoints.
    email = req.headers.get("x-ms-client-principal-name", "").lower()
    user_id = req.headers.get("x-ms-client-principal-id", "")

    if not email:
        # Fallback: decode full principal JSON (base64, add padding if missing)
        header = req.headers.get("x-ms-client-principal", "")
        if not header:
            raise AuthError(401, "Not authenticated")
        try:
            padded = header + "=" * (-len(header) % 4)
            principal = json.loads(base64.b64decode(padded).decode("utf-8"))
        except Exception:
            raise AuthError(401, "Invalid principal header")
        email = principal.get("userDetails", "").lower()
        user_id = principal.get("userId", "")
        if not email:
            raise AuthError(401, "No user identity found")

    allowed = _allowed_emails()
    if allowed and email not in allowed:
        raise AuthError(403, f"Forbidden — not in admin list (got: {email})")

    return {"sub": user_id, "email": email}
