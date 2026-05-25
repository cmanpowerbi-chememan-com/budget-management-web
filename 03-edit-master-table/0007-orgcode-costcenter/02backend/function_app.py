"""Azure Function entry point for Orgcode-CostCenter Master.

Routes:
  GET    /api/master/orgcode-costcenter/list
  POST   /api/master/orgcode-costcenter/save
  DELETE /api/master/orgcode-costcenter/delete
  GET    /api/master/orgcode-costcenter/reference/orgcodes
"""
import azure.functions as func
from handlers import list_handler, save_handler, delete_handler, reference_handler

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="master/orgcode-costcenter/list", methods=["GET"])
def list_route(req: func.HttpRequest) -> func.HttpResponse:
    return list_handler.handle(req)


@app.route(route="master/orgcode-costcenter/save", methods=["POST"])
def save_route(req: func.HttpRequest) -> func.HttpResponse:
    return save_handler.handle(req)


@app.route(route="master/orgcode-costcenter/delete", methods=["DELETE"])
def delete_route(req: func.HttpRequest) -> func.HttpResponse:
    return delete_handler.handle(req)


@app.route(route="master/orgcode-costcenter/reference/{ref_name}", methods=["GET"])
def reference_route(req: func.HttpRequest) -> func.HttpResponse:
    return reference_handler.handle(req)
