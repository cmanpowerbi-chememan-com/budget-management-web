"""DELETE /api/master/hide-document/delete

Hard delete by composite PK (doc_num, fiscal_year, fiscal_month).

⚠️ CRITICAL: WHERE clause MUST include ALL 3 PK columns.

If only doc_num were used → would delete the rule across EVERY
fiscal period for that document.
If (doc_num, fiscal_year) → would delete all 12 months of that
year's exclusions. Both are catastrophic data loss.
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import spark
from models import DeleteRequest

TABLE = "cfg_master.hide_document_number"


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
        WHERE doc_num      = :doc_num
          AND fiscal_year  = :fiscal_year
          AND fiscal_month = :fiscal_month
        """,
        doc_num=payload.doc_num,
        fiscal_year=payload.fiscal_year,
        fiscal_month=payload.fiscal_month,
    )

    return func.HttpResponse(
        json.dumps({
            "status": "deleted",
            "doc_num": payload.doc_num,
            "period": f"{payload.fiscal_year}-{payload.fiscal_month:02d}",
        }),
        status_code=200,
        mimetype="application/json",
    )
