"""GET /api/master/gl-group/reference/{ref_name}

Serves reference dropdown data sourced from nightly SAP sync tables.
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import fetchall

REFERENCE_MAP = {
    "gl-codes": {
        "table": "cfg_master.sap_gl_code_ref",
        "columns": ["code", "name"],
    },
    "gl-groups": {
        "table": "cfg_master.gl_group_dim",
        "columns": ["group_id", "group_name"],
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

    cfg = REFERENCE_MAP[ref_name]
    cols = ", ".join(cfg["columns"])
    rows = fetchall(
        f"SELECT {cols} FROM {cfg['table']} ORDER BY {cfg['columns'][0]}"
    )

    return func.HttpResponse(
        json.dumps(rows),
        status_code=200,
        mimetype="application/json",
    )
