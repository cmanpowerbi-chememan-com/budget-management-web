"""GET /api/master/orgcode-costcenter/reference/{ref_name}

ref_name = orgcodes       → distinct orgcode + orgnameth from dbo.mas_employee_data
ref_name = cost-centers   → cost_center_id + cost_center_name from dbo.gold_sap_m_cost_center
                            (Fabric Lakehouse SQL Analytics Endpoint)
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import fetchall, fetchall_lakehouse

_FABRIC_SQL_REFS = {
    "orgcodes": """
        SELECT DISTINCT
            CAST(orgcode AS NVARCHAR(20)) AS code,
            orgnameth                     AS name
        FROM dbo.mas_employee_data
        WHERE orgcode IS NOT NULL
        ORDER BY code
    """,
}

_LAKEHOUSE_REFS = {
    "cost-centers": """
        SELECT
            cost_center_id   AS code,
            cost_center_name AS name
        FROM dbo.gold_sap_m_cost_center
        ORDER BY cost_center_id
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

    if ref_name in _FABRIC_SQL_REFS:
        fetch_fn = fetchall
        sql = _FABRIC_SQL_REFS[ref_name]
    elif ref_name in _LAKEHOUSE_REFS:
        fetch_fn = fetchall_lakehouse
        sql = _LAKEHOUSE_REFS[ref_name]
    else:
        return func.HttpResponse(
            json.dumps({"error": f"Unknown reference: {ref_name}"}),
            status_code=404,
            mimetype="application/json",
        )

    try:
        rows = fetch_fn(sql)
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
