"""GET /api/master/gl-group/reference/{ref_name}

Serves reference dropdown data sourced from nightly SAP sync tables.
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import fetchall, fetchall_lakehouse

REFERENCE_MAP = {
    "gl-codes": {
        "sql": "SELECT gl_account_number AS code, gl_account_short_text AS name"
               " FROM dbo.gold_sap_m_gl_account_group_name ORDER BY gl_account_number",
        "source": "lakehouse",
    },
    "gl-groups": {
        "sql": "SELECT group_id, group_name"
               " FROM cfg_master.gl_group_dim ORDER BY group_name",
        "source": "fabric_sql",
    },
}


def handle(req: func.HttpRequest) -> func.HttpResponse:
    try:
        authenticate(req)
    except AuthError as e:
        return func.HttpResponse(
            json.dumps({"error": e.message}),
            status_code=e.status,
            mimetype="application/json",
        )

    ref_name = req.route_params.get("ref_name")
    if ref_name not in REFERENCE_MAP:
        return func.HttpResponse(
            json.dumps({"error": f"Unknown reference: {ref_name}"}),
            status_code=404,
            mimetype="application/json",
        )

    try:
        ref = REFERENCE_MAP[ref_name]
        rows = fetchall_lakehouse(ref["sql"]) if ref["source"] == "lakehouse" else fetchall(ref["sql"])
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e), "type": type(e).__name__, "ref": ref_name}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps(rows),
        status_code=200,
        mimetype="application/json",
    )
