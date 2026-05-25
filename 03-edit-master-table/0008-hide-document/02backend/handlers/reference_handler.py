"""GET /api/master/hide-document/reference/{ref_name}"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import spark

REFERENCE_MAP = {
    "doc-numbers": {
        "table": "cfg_master.sap_document_number_ref",
        "columns": ["code", "name"],
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
    rows = spark().sql(
        f"SELECT {cols} FROM {cfg['table']} ORDER BY {cfg['columns'][0]}"
    ).toJSON().collect()

    return func.HttpResponse(
        "[" + ",".join(rows) + "]",
        status_code=200,
        mimetype="application/json",
    )
