"""GET /api/master/hide-document/list

Returns all (doc_num, fiscal_year, fiscal_month) rows with a computed period string.
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
            SELECT doc_num, fiscal_year, fiscal_month
            FROM cfg_master.hide_document_number
            ORDER BY doc_num, fiscal_year DESC, fiscal_month DESC
        """)
        # Compute period 'YYYY-MM' in Python — avoids T-SQL FORMAT() (slow/CLR).
        for r in rows:
            r["period"] = f"{r['fiscal_year']}-{r['fiscal_month']:02d}"
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
