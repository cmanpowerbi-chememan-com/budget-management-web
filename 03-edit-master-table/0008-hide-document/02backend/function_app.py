"""Azure Function entry point for Hide Document Number Master.

Routes:
  GET    /api/master/hide-document/list
  POST   /api/master/hide-document/save
  DELETE /api/master/hide-document/delete
  GET    /api/master/hide-document/reference/doc-numbers
"""
import azure.functions as func
from handlers import list_handler, save_handler, delete_handler, reference_handler

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="master/hide-document/list", methods=["GET"])
def list_route(req: func.HttpRequest) -> func.HttpResponse:
    return list_handler.handle(req)


@app.route(route="master/hide-document/save", methods=["POST"])
def save_route(req: func.HttpRequest) -> func.HttpResponse:
    return save_handler.handle(req)


@app.route(route="master/hide-document/delete", methods=["DELETE"])
def delete_route(req: func.HttpRequest) -> func.HttpResponse:
    return delete_handler.handle(req)


@app.route(route="master/hide-document/reference/{ref_name}", methods=["GET"])
def reference_route(req: func.HttpRequest) -> func.HttpResponse:
    return reference_handler.handle(req)
