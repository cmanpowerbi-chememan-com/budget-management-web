"""GET /api/master/orgcode-costcenter/list

Returns all mappings joined with SAP orgcode reference for
display name alongside the orgcode itself.
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import spark


def handle(req: func.HttpRequest) -> func.HttpResponse:
    try:
        authenticate(req)
    except AuthError as e:
        return func.HttpResponse(
            json.dumps({"error": e.message}),
            status_code=e.status,
            mimetype="application/json",
        )

    rows = spark().sql("""
        SELECT
            m.cost_center,
            m.orgcode,
            COALESCE(r.name, '') AS orgcode_name
        FROM cfg_master.orgcode_costcenter m
        LEFT JOIN cfg_master.sap_orgcode_ref r
            ON m.orgcode = r.code
        ORDER BY m.cost_center, m.orgcode
    """).toJSON().collect()

    return func.HttpResponse(
        "[" + ",".join(rows) + "]",
        status_code=200,
        mimetype="application/json",
    )
