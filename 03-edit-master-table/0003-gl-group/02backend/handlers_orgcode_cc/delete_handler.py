"""DELETE /api/master/orgcode-costcenter/delete

Hard delete by composite key (cost_center, orgcode) — both required.
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import execute
from models_orgcode_cc import DeleteRequest

TABLE = "cfg_master.orgcode_costcenter_map"


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
        payload = DeleteRequest(**req.get_json())
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": f"Invalid payload: {e}"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        execute(
            f"DELETE FROM {TABLE} WHERE cost_center = ? AND orgcode = ?",
            (payload.cost_center, payload.orgcode),
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e), "type": type(e).__name__}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps({
            "status": "deleted",
            "cost_center": payload.cost_center,
            "orgcode": payload.orgcode,
        }),
        status_code=200,
        mimetype="application/json",
    )
