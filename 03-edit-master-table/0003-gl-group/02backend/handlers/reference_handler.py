"""GET /api/master/gl-group/reference/{ref_name}

Serves reference dropdown data sourced from nightly SAP sync tables.
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import fetchall

REFERENCE_MAP = {
    # GL codes sourced from existing mapping table (all 137 codes already assigned).
    # Switch to cfg_master.sap_gl_code_ref once that table is populated.
    "gl-codes": {
        "sql": "SELECT DISTINCT gl_code AS code, gl_code AS name"
               " FROM cfg_master.gl_group_mapping ORDER BY gl_code",
    },
    "gl-groups": {
        "sql": "SELECT group_id, group_name"
               " FROM cfg_master.gl_group_dim ORDER BY group_name",
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
        rows = fetchall(REFERENCE_MAP[ref_name]["sql"])
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
