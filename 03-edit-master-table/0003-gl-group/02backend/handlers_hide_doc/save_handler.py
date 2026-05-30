"""POST /api/master/hide-document/save

Composite PK (doc_num, fiscal_year, fiscal_month) — exists() pre-check + INSERT.
Race-safe: catches pyodbc.IntegrityError as 409 in case two concurrent saves both
pass exists() and one fails the PK constraint.
"""
import json
import pyodbc
import azure.functions as func
from auth import authenticate, AuthError
from db import exists, execute
from models_hide_doc import SaveRequest

TABLE = "cfg_master.hide_document_number"


def _dup_response() -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({
            "code": "DUPLICATE_KEY",
            "message_th": "Document Number + Year + Month ชุดนี้มีอยู่แล้ว",
            "message_en": "This (doc_num, fiscal_year, fiscal_month) triple already exists.",
        }),
        status_code=409,
        mimetype="application/json",
    )


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
        payload = SaveRequest(**req.get_json())
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": f"Invalid payload: {e}"}),
            status_code=400,
            mimetype="application/json",
        )

    pk_where = "doc_num = ? AND fiscal_year = ? AND fiscal_month = ?"
    pk_params = (payload.doc_num, payload.fiscal_year, payload.fiscal_month)

    if exists(TABLE, pk_where, pk_params):
        return _dup_response()

    try:
        execute(
            f"INSERT INTO {TABLE} (doc_num, fiscal_year, fiscal_month) VALUES (?, ?, ?)",
            pk_params,
        )
    except pyodbc.IntegrityError:
        return _dup_response()
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e), "type": type(e).__name__}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps({
            "status": "success",
            "doc_num": payload.doc_num,
            "period": f"{payload.fiscal_year}-{payload.fiscal_month:02d}",
        }),
        status_code=200,
        mimetype="application/json",
    )
