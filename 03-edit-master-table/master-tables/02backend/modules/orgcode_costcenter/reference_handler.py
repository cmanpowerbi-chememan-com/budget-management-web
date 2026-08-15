"""GET /api/master/orgcode-costcenter/reference/{ref_name}

ref_name = orgcodes       → distinct org_code + org_name_th from dbo.employee_master
ref_name = cost-centers   → cost_center_id + cost_center_name from dbo.gold_sap_m_cost_center
                            (Fabric Lakehouse SQL Analytics Endpoint)

dbo.employee_master is the RAW mirror — unlike the retired dbo.mas_employee_data,
which setup/sync_employees.py pre-filtered at sync time, nothing filters this table
upstream. The `orgcodes` ref re-applies that same filter (setup/sync_employees.py:
90-101) so the dropdown still excludes subsidiary org codes an admin should never
map a cost center to:
  hr status == 'Active'        -> record_status = 'active'
  empcode LIKE '4%'            -> employee_code NOT LIKE '4%'   (Gritsman subsidiary)
  orgcode LIKE '117%'          -> org_code NOT LIKE '117%'      (Vietnam + Australia,
                                                                  both share the 117 prefix)
  joblevelnameen in L5_LEVELS  -> job_level_name_en NOT IN (...) (L5 Operator/Driver/Maid)
Do not drop this filter — list_handler.py's join does NOT need it (verified: the
list is a pure name lookup returning the same 725 rows either way; adding it there
would only blank out names that currently resolve correctly).
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import fetchall, fetchall_lakehouse

_FABRIC_SQL_REFS = {
    "orgcodes": """
        SELECT DISTINCT
            CAST(org_code AS NVARCHAR(20)) AS code,
            org_name_th                    AS name
        FROM dbo.employee_master
        WHERE org_code IS NOT NULL
          AND record_status = 'active'
          AND employee_code NOT LIKE '4%'
          AND org_code NOT LIKE '117%'
          AND job_level_name_en NOT IN ('Operator 1','Operator 2','Operator 3','Driver','Maid')
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
