"""JWT validation + Azure AD group claim check.

Identical across all entities in the master-table skill.
Verifies signature, issuer, audience, expiry, and required group.
"""
import os
import jwt
import requests
from functools import lru_cache

AAD_TENANT_ID  = os.environ["AAD_TENANT_ID"]
AAD_AUDIENCE   = os.environ["AAD_AUDIENCE"]
REQUIRED_GROUP = "master-table-admins"

JWKS_URL = f"https://login.microsoftonline.com/{AAD_TENANT_ID}/discovery/v2.0/keys"
ISSUER   = f"https://login.microsoftonline.com/{AAD_TENANT_ID}/v2.0"


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


@lru_cache(maxsize=1)
def _jwks() -> list:
    """Fetch Azure AD signing keys. Cached for process lifetime."""
    return requests.get(JWKS_URL, timeout=5).json()["keys"]


def _key_for(kid: str):
    for k in _jwks():
        if k["kid"] == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(k)
    raise AuthError(401, "Signing key not found")


def authenticate(req) -> dict:
    """Validate JWT, return decoded claims. Raise AuthError on failure.

    Performs the 5 mandatory checks:
      1. Signature (RS256 against Azure AD JWKS)
      2. Issuer (must match tenant)
      3. Audience (must match this Function App's client ID)
      4. Expiry (exp must be in the future)
      5. Group membership (master-table-admins must be in groups claim)
    """
    header = req.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthError(401, "Missing Authorization header")
    token = header[7:]

    try:
        unverified = jwt.get_unverified_header(token)
        key = _key_for(unverified["kid"])
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=AAD_AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.PyJWTError as e:
        raise AuthError(401, f"Token invalid: {e}")

    groups = claims.get("groups", [])
    if REQUIRED_GROUP not in groups:
        raise AuthError(403, "Forbidden — admin role required")

    return claims
