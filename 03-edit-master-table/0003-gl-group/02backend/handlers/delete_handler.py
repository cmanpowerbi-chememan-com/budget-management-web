"""DELETE /api/master/gl-group/delete

Hard delete by gl_code (single PK).
Locked decision #22: hard delete + simple confirm modal in frontend.
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import execute
from models import DeleteRequest

TABLE = "cfg_master.gl_group_mapping"


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

    execute(
        f"DELETE FROM {TABLE} WHERE gl_code = ?",
        (payload.gl_code,),
    )

    return func.HttpResponse(
        json.dumps({"status": "deleted", "gl_code": payload.gl_code}),
        status_code=200,
        mimetype="application/json",
    )
