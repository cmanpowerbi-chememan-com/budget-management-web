"""DELETE /api/master/hide-document/delete

Hard delete by 3-col composite key (doc_num, fiscal_year, fiscal_month) — all required.
Returns rowcount so frontend can warn if the row was already gone (concurrent delete).
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import get_conn
from models_hide_doc import DeleteRequest

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

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            f"DELETE FROM {TABLE} "
            f"WHERE doc_num = ? AND fiscal_year = ? AND fiscal_month = ?",
            (payload.doc_num, payload.fiscal_year, payload.fiscal_month),
        )
        deleted = cur.rowcount  # 0 means row already gone (concurrent delete)
        conn.commit()
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e), "type": type(e).__name__}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps({
            "status": "deleted",
            "deleted": deleted,
            "doc_num": payload.doc_num,
            "period": f"{payload.fiscal_year}-{payload.fiscal_month:02d}",
        }),
        status_code=200,
        mimetype="application/json",
    )
