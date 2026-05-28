"""GET /api/master/orgcode-costcenter/reference/{ref_name}

ref_name = orgcodes  →  distinct orgcode + orgnameth from dbo.mas_employee_data
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import fetchall

REFERENCE_MAP = {
    "orgcodes": """
        SELECT DISTINCT
            CAST(orgcode AS NVARCHAR(20)) AS code,
            orgnameth                     AS name
        FROM dbo.mas_employee_data
        WHERE orgcode IS NOT NULL
        ORDER BY code
    """,
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
        rows = fetchall(REFERENCE_MAP[ref_name])
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e), "type": type(e).__name__}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps(rows, ensure_ascii=False),
        status_code=200,
        mimetype="application/json",
    )
