"""GET /api/master/orgcode-costcenter/list"""
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
                m.id,
                m.cost_center,
                m.orgcode,
                COALESCE(e.orgnameth, '') AS orgcode_name
            FROM cfg_master.orgcode_costcenter_map m
            LEFT JOIN (
                SELECT DISTINCT orgcode, orgnameth
                FROM dbo.mas_employee_data
                WHERE orgcode IS NOT NULL
            ) e ON e.orgcode = m.orgcode
            ORDER BY m.cost_center, m.orgcode
        """)
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
