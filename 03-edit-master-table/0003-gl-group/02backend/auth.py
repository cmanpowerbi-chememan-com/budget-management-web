"""SWA principal header auth.

In Azure Static Web Apps, the platform injects x-ms-client-principal
into every Function request after the user is authenticated.
We trust this header (SWA signs it) and check userRoles.
"""
import base64
import json

REQUIRED_ROLE = "master_table_admins"


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


def authenticate(req) -> dict:
    """Read SWA-injected principal header, check role. Raise AuthError on failure."""
    header = req.headers.get("x-ms-client-principal", "")
    if not header:
        raise AuthError(401, "Not authenticated")

    try:
        principal = json.loads(base64.b64decode(header).decode("utf-8"))
    except Exception:
        raise AuthError(401, "Invalid principal header")

    user_roles = principal.get("userRoles", [])
    if REQUIRED_ROLE not in user_roles:
        raise AuthError(403, "Forbidden — admin role required")

    return {
        "sub":    principal.get("userId", ""),
        "email":  principal.get("userDetails", ""),
        "groups": user_roles,
    }
