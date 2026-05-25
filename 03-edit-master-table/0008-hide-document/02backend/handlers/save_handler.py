"""POST /api/master/hide-document/save

Handles:
  1. Auth + payload validation (incl. year/month range checks)
  2. Fail Fast duplicate check (ALL 3 PK columns)
  3. MERGE INSERT (no UPDATE branch — exclusion table has no
     non-PK columns to update)
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import spark, exists
from models import SaveRequest

TABLE = "cfg_master.hide_document_number"


def handle(req: func.HttpRequest) -> func.HttpResponse:
    # ── Auth ─────────────────────────────────────────
    try:
        authenticate(req)
    except AuthError as e:
        return func.HttpResponse(
            json.dumps({"error": e.message}),
            status_code=e.status,
            mimetype="application/json",
        )

    # ── Parse + validate ─────────────────────────────
    # Pydantic enforces:
    #   - fiscal_year ∈ [2020, 2099]
    #   - fiscal_month ∈ [1, 12]
    try:
        payload = SaveRequest(**req.get_json())
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": f"Invalid payload: {e}"}),
            status_code=400,
            mimetype="application/json",
        )

    # ── Fail Fast duplicate check (ALL 3 PK columns) ──
    # ⚠️ For 3-column composite PK, the existence check MUST
    # include all three columns. Missing any column risks
    # false-positive rejection on valid new (doc, period) triples.
    if exists(
        TABLE,
        "doc_num = :doc_num AND fiscal_year = :fiscal_year AND fiscal_month = :fiscal_month",
        {
            "doc_num":      payload.doc_num,
            "fiscal_year":  payload.fiscal_year,
            "fiscal_month": payload.fiscal_month,
        },
    ):
        period = f"{payload.fiscal_year}-{payload.fiscal_month:02d}"
        return func.HttpResponse(
            json.dumps({
                "code": "DUPLICATE_KEY",
                "message_th": (
                    f"Document Number {payload.doc_num} ถูก hide "
                    f"ในงวด {period} อยู่แล้ว"
                ),
                "message_en": (
                    f"Document {payload.doc_num} is already hidden "
                    f"for period {period}."
                ),
            }),
            status_code=409,
            mimetype="application/json",
        )

    # ── MERGE upsert (no UPDATE branch — all cols are PK) ──
    # ⚠️ 3-column composite PK requires ALL THREE in ON clause.
    spark().sql(
        """
        MERGE INTO cfg_master.hide_document_number t
        USING (
            SELECT DISTINCT
                :doc_num      AS doc_num,
                :fiscal_year  AS fiscal_year,
                :fiscal_month AS fiscal_month
        ) s
        ON  t.doc_num      = s.doc_num
        AND t.fiscal_year  = s.fiscal_year
        AND t.fiscal_month = s.fiscal_month
        WHEN NOT MATCHED THEN INSERT (doc_num, fiscal_year, fiscal_month)
        VALUES (s.doc_num, s.fiscal_year, s.fiscal_month)
        """,
        doc_num=payload.doc_num,
        fiscal_year=payload.fiscal_year,
        fiscal_month=payload.fiscal_month,
    )

    return func.HttpResponse(
        json.dumps({
            "status": "success",
            "period": f"{payload.fiscal_year}-{payload.fiscal_month:02d}",
        }),
        status_code=200,
        mimetype="application/json",
    )
