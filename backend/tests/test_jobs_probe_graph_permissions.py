"""Unit tests for jobs.probe_graph_permissions — issue #28's open question
("can the CI runner's own Graph credentials actually send mail?").

Covers only the two pure, network-free units: decoding a JWT payload and
deciding PASS/FAIL from its `roles` claim. `main()` fetches a real token
and is deliberately NOT exercised here (no network, no real credentials in
this suite) — it is verified by running the job locally, see the task's
Verify step and the final report.
"""
import base64
import json

import pytest

from jobs.probe_graph_permissions import (
    REQUIRED_ROLE,
    TokenDecodeError,
    check_mail_send_role,
    decode_jwt_payload,
)


def _fake_jwt(payload: dict) -> str:
    """Builds a JWT-shaped string (header.payload.signature) carrying an
    arbitrary claims dict, padding-stripped the same way a real JWT is —
    exercises decode_jwt_payload's own re-padding without ever calling
    Microsoft's token endpoint. Header/signature content is never verified
    by the code under test, so both are throwaway."""
    header_b64 = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header_b64}.{payload_b64}.fake-signature"


# ---------------------------------------------------------------------------
# decode_jwt_payload
# ---------------------------------------------------------------------------

def test_decode_jwt_payload_returns_claims():
    token = _fake_jwt({
        "appid": "abc-123", "tid": "tenant-456",
        "roles": ["Mail.Send", "Sites.ReadWrite.All"],
    })

    payload = decode_jwt_payload(token)

    assert payload == {
        "appid": "abc-123", "tid": "tenant-456",
        "roles": ["Mail.Send", "Sites.ReadWrite.All"],
    }


def test_decode_jwt_payload_no_dots_raises_clear_error_not_traceback():
    with pytest.raises(TokenDecodeError, match="3 dot-separated segments"):
        decode_jwt_payload("not-a-jwt-at-all")


def test_decode_jwt_payload_wrong_segment_count_raises_clear_error():
    with pytest.raises(TokenDecodeError, match="3 dot-separated segments"):
        decode_jwt_payload("only.two-segments")


def test_decode_jwt_payload_invalid_payload_segment_raises_clear_error():
    with pytest.raises(TokenDecodeError, match="could not decode"):
        decode_jwt_payload("header.!!!not-base64-or-json!!!.sig")


def test_decode_jwt_payload_non_object_json_raises_clear_error():
    payload_b64 = base64.urlsafe_b64encode(b"[1, 2, 3]").rstrip(b"=").decode()
    token = f"header.{payload_b64}.sig"

    with pytest.raises(TokenDecodeError, match="not a JSON object"):
        decode_jwt_payload(token)


# ---------------------------------------------------------------------------
# check_mail_send_role
# ---------------------------------------------------------------------------

def test_check_mail_send_role_pass_when_present():
    assert check_mail_send_role({"roles": ["Sites.ReadWrite.All", REQUIRED_ROLE]}) is True


def test_check_mail_send_role_fail_when_absent():
    assert check_mail_send_role({"roles": ["Sites.ReadWrite.All"]}) is False


def test_check_mail_send_role_fail_when_roles_claim_missing_entirely():
    """A delegated-permission (non-application) token carries no `roles`
    claim at all — must be a clean False, never a KeyError."""
    assert check_mail_send_role({}) is False
