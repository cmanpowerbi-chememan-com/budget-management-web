"""GET /api/master/hide-document/list

Returns all exclusion rules joined with SAP document reference.
Computes "YYYY-MM" period string in SQL for frontend display.
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
            m.doc_num,
            m.fiscal_year,
            m.fiscal_month,
            COALESCE(r.name, '') AS doc_name,
            CONCAT(
                CAST(m.fiscal_year AS STRING),
                '-',
                LPAD(CAST(m.fiscal_month AS STRING), 2, '0')
            ) AS period
        FROM cfg_master.hide_document_number m
        LEFT JOIN cfg_master.sap_document_number_ref r
            ON m.doc_num = r.code
        ORDER BY m.doc_num, m.fiscal_year DESC, m.fiscal_month DESC
    """).toJSON().collect()

    return func.HttpResponse(
        "[" + ",".join(rows) + "]",
        status_code=200,
        mimetype="application/json",
    )
