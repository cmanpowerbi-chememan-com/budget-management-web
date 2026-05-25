"""POST /api/master/orgcode-costcenter/save

Handles:
  1. Auth + payload validation
  2. Fail Fast duplicate check (BOTH PK columns)
  3. MERGE INSERT into junction table (no UPDATE branch)
"""
import json
import azure.functions as func
from auth import authenticate, AuthError
from db import spark, exists
from models import SaveRequest

TABLE = "cfg_master.orgcode_costcenter"


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
    try:
        payload = SaveRequest(**req.get_json())
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": f"Invalid payload: {e}"}),
            status_code=400,
            mimetype="application/json",
        )

    # ── Fail Fast duplicate check (BOTH PK columns) ──
    # ⚠️ For composite PK, the existence check MUST include all PK
    # columns. Checking only cost_center would falsely reject inserts
    # of new (cost_center, orgcode) pairs that share an existing cost_center.
    if exists(
        TABLE,
        "cost_center = :cost_center AND orgcode = :orgcode",
        {"cost_center": payload.cost_center, "orgcode": payload.orgcode},
    ):
        return func.HttpResponse(
            json.dumps({
                "code": "DUPLICATE_KEY",
                "message_th": (
                    "Cost Center และ Orgcode คู่นี้มีอยู่ในระบบแล้ว "
                    "กรุณา refresh แล้วลองใหม่"
                ),
                "message_en": "This (cost_center, orgcode) pair already exists.",
            }),
            status_code=409,
            mimetype="application/json",
        )

    # ── MERGE upsert (junction table — no UPDATE branch) ──
    # ⚠️ Composite PK requires BOTH columns in ON clause.
    # Using single column would trigger DELTA_MULTIPLE_SOURCE_ROW_MATCHING.
    spark().sql(
        """
        MERGE INTO cfg_master.orgcode_costcenter t
        USING (
            SELECT DISTINCT
                :cost_center AS cost_center,
                :orgcode     AS orgcode
        ) s
        ON  t.cost_center = s.cost_center
        AND t.orgcode     = s.orgcode
        WHEN NOT MATCHED THEN INSERT (cost_center, orgcode)
        VALUES (s.cost_center, s.orgcode)
        """,
        cost_center=payload.cost_center,
        orgcode=payload.orgcode,
    )

    return func.HttpResponse(
        json.dumps({"status": "success"}),
        status_code=200,
        mimetype="application/json",
    )
