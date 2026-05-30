"""GET /api/master/gl-group/list

Returns all mappings joined with dim table so frontend gets group_name
for display alongside group_id.
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import fetchall


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
        rows = fetchall("""
            SELECT
                m.gl_code,
                m.group_id,
                d.group_name
            FROM cfg_master.gl_group_mapping m
            LEFT JOIN cfg_master.gl_group_dim d
                ON m.group_id = d.group_id
            ORDER BY m.gl_code
        """)
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e), "type": type(e).__name__}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps(rows),
        status_code=200,
        mimetype="application/json",
    )
