"""POST /api/master/orgcode-costcenter/save"""
import json
import pyodbc
import azure.functions as func
from auth import authenticate, AuthError
from db import exists, execute
from models_orgcode_cc import SaveRequest

TABLE = "cfg_master.orgcode_costcenter_map"


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

    if exists(TABLE, "cost_center = ? AND orgcode = ?", (payload.cost_center, payload.orgcode)):
        return func.HttpResponse(
            json.dumps({
                "code": "DUPLICATE_KEY",
                "message_th": "Cost Center และ Orgcode คู่นี้มีอยู่ในระบบแล้ว",
                "message_en": "This (cost_center, orgcode) pair already exists.",
            }),
            status_code=409,
            mimetype="application/json",
        )

    try:
        execute(
            f"INSERT INTO {TABLE} (orgcode, cost_center) VALUES (?, ?)",
            (payload.orgcode, payload.cost_center),
        )
    except pyodbc.IntegrityError:
        # Race condition: another request inserted the same pair between exists() and execute()
        return func.HttpResponse(
            json.dumps({
                "code": "DUPLICATE_KEY",
                "message_th": "Cost Center และ Orgcode คู่นี้มีอยู่ในระบบแล้ว",
                "message_en": "This (cost_center, orgcode) pair already exists.",
            }),
            status_code=409,
            mimetype="application/json",
        )
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e), "type": type(e).__name__}),
            status_code=500,
            mimetype="application/json",
        )

    return func.HttpResponse(
        json.dumps({"status": "success"}),
        status_code=200,
        mimetype="application/json",
    )
