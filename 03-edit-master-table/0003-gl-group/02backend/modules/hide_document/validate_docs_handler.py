"""POST /api/master/hide-document/validate-docs

Body:    { "codes": ["5400005042", "5400005043", ...] }
Returns: { "valid":   ["5400005042", ...],
           "invalid": ["5400005043", ...] }

Validates each doc number against dbo.gold_sap_gl_trans on the Lakehouse SQL
Analytics Endpoint. Uses fetchall_lakehouse() — DO NOT use `with get_lakehouse_conn()`,
that pattern closes the per-thread cached connection and breaks subsequent requests
(including 0003's gl-codes dropdown which shares the same thread-local cache).
"""
import json
import re
import azure.functions as func
from auth import authenticate, AuthError
from db import fetchall_lakehouse

DOC_FORMAT = re.compile(r"^[0-9]{10}$")
MAX_CODES_PER_REQUEST = 200


def validate(codes: list[str]) -> dict[str, list[str]]:
    """Pure logic — testable without the Function runtime."""
    seen: set[str] = set()
    ordered_in: list[str] = []
    bad_format: list[str] = []
    for c in codes:
        c = str(c).strip()
        if not c or c in seen:
            continue
        seen.add(c)
        if not DOC_FORMAT.match(c):
            bad_format.append(c)
        else:
            ordered_in.append(c)

    if not ordered_in:
        return {"valid": [], "invalid": bad_format}

    placeholders = ",".join("?" * len(ordered_in))
    sql = (
        f"SELECT DISTINCT accounting_doc_number "
        f"FROM dbo.gold_sap_gl_trans "
        f"WHERE accounting_doc_number IN ({placeholders})"
    )
    rows = fetchall_lakehouse(sql, tuple(ordered_in))
    existing = {row["accounting_doc_number"] for row in rows}

    valid   = [c for c in ordered_in if c in existing]
    invalid = bad_format + [c for c in ordered_in if c not in existing]
    return {"valid": valid, "invalid": invalid}


def handle(req: func.HttpRequest) -> func.HttpResponse:
    try:
        authenticate(req)
    except AuthError as e:
        return func.HttpResponse(
            json.dumps({"error": e.message}),
            status_code=e.status,
            mimetype="application/json",
        )

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Body must be valid JSON"}),
            status_code=400,
            mimetype="application/json",
        )

    codes = body.get("codes")
    if not isinstance(codes, list) or not codes:
        return func.HttpResponse(
            json.dumps({"error": "codes must be a non-empty array"}),
            status_code=400,
            mimetype="application/json",
        )
    if len(codes) > MAX_CODES_PER_REQUEST:
        return func.HttpResponse(
            json.dumps({"error": f"max {MAX_CODES_PER_REQUEST} codes per request"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        result = validate(codes)
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e), "type": type(e).__name__}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps(result),
        status_code=200,
        mimetype="application/json",
    )
