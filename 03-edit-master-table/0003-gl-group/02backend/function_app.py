"""Azure Function entry point for GL Group Master CRUD.

Routes:
  GET    /api/master/gl-group/list
  POST   /api/master/gl-group/save
  DELETE /api/master/gl-group/delete
  GET    /api/master/gl-group/reference/gl-codes
"""
import azure.functions as func
from handlers import list_handler, save_handler, delete_handler, reference_handler

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
# AuthLevel.ANONYMOUS means "no function key required".
# Real auth is enforced by auth.py (JWT) + Static Web Apps (allowedRoles).


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
