"""Azure Function entry point — GL Group + Orgcode-CostCenter + Hide-Document Masters.

GL Group routes:
  GET    /api/master/gl-group/list
  POST   /api/master/gl-group/save
  DELETE /api/master/gl-group/delete
  GET    /api/master/gl-group/reference/{ref_name}

Orgcode-CostCenter routes:
  GET    /api/master/orgcode-costcenter/list
  POST   /api/master/orgcode-costcenter/save
  DELETE /api/master/orgcode-costcenter/delete
  GET    /api/master/orgcode-costcenter/reference/{ref_name}

Hide-Document routes:
  GET    /api/master/hide-document/list
  POST   /api/master/hide-document/save
  DELETE /api/master/hide-document/delete
  POST   /api/master/hide-document/validate-docs
"""
import azure.functions as func
from modules.gl_group import list_handler, save_handler, delete_handler, reference_handler
from modules.orgcode_costcenter import (
    list_handler as cc_list,
    save_handler as cc_save,
    delete_handler as cc_delete,
    reference_handler as cc_reference,
)
from modules.hide_document import (
    list_handler as hd_list,
    save_handler as hd_save,
    delete_handler as hd_delete,
    validate_docs_handler as hd_validate,
)

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


# ── GL Group ──────────────────────────────────────────────
@app.route(route="master/gl-group/list", methods=["GET"])
def list_route(req: func.HttpRequest) -> func.HttpResponse:
    return list_handler.handle(req)


@app.route(route="master/gl-group/save", methods=["POST"])
def save_route(req: func.HttpRequest) -> func.HttpResponse:
    return save_handler.handle(req)


@app.route(route="master/gl-group/delete", methods=["DELETE"])
def delete_route(req: func.HttpRequest) -> func.HttpResponse:
    return delete_handler.handle(req)


@app.route(route="master/gl-group/reference/{ref_name}", methods=["GET"])
def reference_route(req: func.HttpRequest) -> func.HttpResponse:
    return reference_handler.handle(req)


# ── Orgcode-CostCenter ────────────────────────────────────
@app.route(route="master/orgcode-costcenter/list", methods=["GET"])
def cc_list_route(req: func.HttpRequest) -> func.HttpResponse:
    return cc_list.handle(req)


@app.route(route="master/orgcode-costcenter/save", methods=["POST"])
def cc_save_route(req: func.HttpRequest) -> func.HttpResponse:
    return cc_save.handle(req)


@app.route(route="master/orgcode-costcenter/delete", methods=["DELETE"])
def cc_delete_route(req: func.HttpRequest) -> func.HttpResponse:
    return cc_delete.handle(req)


@app.route(route="master/orgcode-costcenter/reference/{ref_name}", methods=["GET"])
def cc_reference_route(req: func.HttpRequest) -> func.HttpResponse:
    return cc_reference.handle(req)


# ── Hide Document ─────────────────────────────────────────
@app.route(route="master/hide-document/list", methods=["GET"])
def hd_list_route(req: func.HttpRequest) -> func.HttpResponse:
    return hd_list.handle(req)


@app.route(route="master/hide-document/save", methods=["POST"])
def hd_save_route(req: func.HttpRequest) -> func.HttpResponse:
    return hd_save.handle(req)


@app.route(route="master/hide-document/delete", methods=["DELETE"])
def hd_delete_route(req: func.HttpRequest) -> func.HttpResponse:
    return hd_delete.handle(req)


@app.route(route="master/hide-document/validate-docs", methods=["POST"])
def hd_validate_route(req: func.HttpRequest) -> func.HttpResponse:
    return hd_validate.handle(req)
