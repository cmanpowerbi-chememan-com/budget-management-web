"""On-demand CI probe (issue #28) — proves whether THIS runner's own
Microsoft Graph credentials can send mail, without sending any.

The gap this closes: the two preview mails verified on 2026-09-18 were sent
from the developer's own machine using `backend/.env` (ENTRA_CLIENT_ID/
_SECRET/_TENANT_ID). `.github/workflows/budget-automations.yml` maps those
same env var NAMES from different repository secrets
(`FABRIC_AAD_CLIENT_ID`/`FABRIC_AAD_CLIENT_SECRET`/`FABRIC_AAD_TENANT_ID`),
and nothing has ever exercised THAT service principal against Microsoft
Graph — the nightly automation run never calls Graph unless a reminder is
actually due. If that service principal lacks the `Mail.Send` application
role, every one of the 71 real sends planned for 2026-09-30 would fail at
the moment it mattered. This job answers that one question ahead of time.

Reuses `app.notifications._get_graph_token` (the same token path/env vars
the notification layer sends real mail through) rather than fetching a
second token — a probe that used a different code path could pass while the
real one still fails. Makes exactly ONE Graph-related call: the token
request. Never calls `sendMail`.

Run (from `backend/`):
    python -m jobs.probe_graph_permissions

Exit code 0 = PASS (Mail.Send present), 1 = FAIL (missing role, or the
token request itself failed) — a CI step must fail loudly, not just log.
"""
import base64
import json
import logging

from app import notifications
from app.config import get_settings
from jobs.common import configure_logging

logger = logging.getLogger("jobs.probe_graph_permissions")

# The one application permission a real send depends on (Settings.notifications_sender_email's
# mailbox is sent-AS via this role — see app/notifications.py's module docstring).
REQUIRED_ROLE = "Mail.Send"


class TokenDecodeError(ValueError):
    """The Graph access token could not be decoded into a JSON claims dict."""


def decode_jwt_payload(token: str) -> dict:
    """Decodes (does NOT verify — no signature check, no extra dependency)
    the middle segment of a JWT access token into its claims dict. No
    verification is needed here: the token was just fetched directly from
    Microsoft's own token endpoint over TLS by `_get_graph_token`, so its
    authenticity is already established by the transport, not by this
    decode. Raises `TokenDecodeError` (never a raw traceback) on anything
    that is not a well-formed JWT-shaped string."""
    segments = token.split(".")
    if len(segments) != 3:
        raise TokenDecodeError(f"not a JWT: expected 3 dot-separated segments, got {len(segments)}")
    payload_b64 = segments[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, UnicodeDecodeError) as exc:
        # base64's own binascii.Error and json.JSONDecodeError are both
        # ValueError subclasses, so this one branch covers both stages.
        raise TokenDecodeError(f"could not decode JWT payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise TokenDecodeError("decoded JWT payload is not a JSON object")
    return payload


def check_mail_send_role(payload: dict) -> bool:
    """True when the token's `roles` claim (the application permissions
    actually granted to this service principal) includes Mail.Send. A
    missing/empty `roles` claim (e.g. a delegated-permission token) is a
    clean False, never a KeyError."""
    roles = payload.get("roles") or []
    return REQUIRED_ROLE in roles


def main() -> int:
    configure_logging()
    settings = get_settings()

    try:
        token = notifications._get_graph_token(settings)
    except notifications.NotificationError as exc:
        logger.error("probe_graph_permissions: token request failed: %s", exc)
        print(f"FAIL: could not obtain a Graph token with this runner's credentials — {exc}")
        return 1

    try:
        payload = decode_jwt_payload(token)
    except TokenDecodeError as exc:
        logger.error("probe_graph_permissions: token decode failed: %s", exc)
        print(f"FAIL: got a token but could not decode it — {exc}")
        return 1

    app_id = payload.get("appid", "(not present in token)")
    tenant_id = payload.get("tid", "(not present in token)")
    roles = sorted(payload.get("roles") or [])

    print(f"app id (appid): {app_id}")
    print(f"tenant (tid): {tenant_id}")
    print(f"roles: {roles}")

    if check_mail_send_role(payload):
        print(f"PASS: {REQUIRED_ROLE} is present — this runner's credentials CAN send mail through Microsoft Graph today.")
        return 0

    print(
        f"FAIL: {REQUIRED_ROLE} is missing from roles={roles} — "
        f"this runner's credentials CANNOT send mail through Microsoft Graph today."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
