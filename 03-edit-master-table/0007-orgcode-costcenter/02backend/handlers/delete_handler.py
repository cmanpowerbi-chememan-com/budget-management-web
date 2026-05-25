"""DELETE /api/master/orgcode-costcenter/delete

Hard delete by composite PK (cost_center, orgcode).

⚠️ CRITICAL: WHERE clause MUST include BOTH PK columns.
Using only cost_center would delete ALL mappings of that
Cost Center across every Orgcode — catastrophic data loss.
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import spark
from models import DeleteRequest

TABLE = "cfg_master.orgcode_costcenter"


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

    spark().sql(
        f"""
        DELETE FROM {TABLE}
        WHERE cost_center = :cost_center
          AND orgcode     = :orgcode
        """,
        cost_center=payload.cost_center,
        orgcode=payload.orgcode,
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
