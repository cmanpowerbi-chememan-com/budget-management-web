"""POST /api/master/gl-group/save

Handles:
  1. Auth + payload validation
  2. Fail Fast duplicate check (locked decision #5)
  3. Resolve group_id (existing dim or create new via create_on_save)
  4. MERGE upsert into gl_group_mapping
"""
import json
import uuid
import azure.functions as func
from auth import authenticate, AuthError
from db import execute, exists, find_group_id_by_name
from models import SaveRequest

TABLE = "cfg_master.gl_group_mapping"


def _resolve_group_id(payload: SaveRequest) -> str:
    """Return the group_id to use, creating a new dim row if needed."""
    if payload.group_id:
        return payload.group_id

    # create_on_save path: look up by name first to avoid duplicate dims
    existing = find_group_id_by_name(payload.group_name)
    if existing:
        return existing

    # Truly new group → mint UUID and INSERT via MERGE
    new_id = str(uuid.uuid4())
    execute(
        """
        MERGE cfg_master.gl_group_dim AS t
        USING (SELECT ? AS group_id, ? AS group_name) AS s
        ON t.group_id = s.group_id
        WHEN NOT MATCHED THEN
            INSERT (group_id, group_name) VALUES (s.group_id, s.group_name);
        """,
        (new_id, payload.group_name),
    )
    return new_id


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

    # ── Fail Fast duplicate check ────────────────────
    if not payload.is_edit_mode and exists(
        TABLE,
        "gl_code = ?",
        (payload.gl_code,),
    ):
        return func.HttpResponse(
            json.dumps({
                "code": "DUPLICATE_KEY",
                "message_th": "รหัส GL Code นี้มีอยู่ในระบบแล้ว กรุณา refresh แล้วลองใหม่",
                "message_en": "Row already exists. Refresh and try again.",
            }),
            status_code=409,
            mimetype="application/json",
        )

    # ── Resolve group_id (handles create_on_save) ────
    group_id = _resolve_group_id(payload)

    # ── MERGE upsert into mapping ────────────────────
    execute(
        """
        MERGE cfg_master.gl_group_mapping AS t
        USING (SELECT ? AS gl_code, ? AS group_id) AS s
        ON t.gl_code = s.gl_code
        WHEN MATCHED THEN
            UPDATE SET group_id = s.group_id
        WHEN NOT MATCHED THEN
            INSERT (gl_code, group_id) VALUES (s.gl_code, s.group_id);
        """,
        (payload.gl_code, group_id),
    )

    return func.HttpResponse(
        json.dumps({"status": "success", "group_id": group_id}),
        status_code=200,
        mimetype="application/json",
    )
