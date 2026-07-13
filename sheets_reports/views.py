import importlib
import inspect
import json
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from sheets_reports.models import Dashboard, WidgetInstance
from sheets_reports.utils.widget_dispatcher import dispatch_widget


def home(request):
    return render(request, 'home.html')


def board_editor(request, board_id):
    return render(request, 'board_editor.html', {'board_id': board_id})


def widget_data(request, widget_id):
    """
    Endpoint AJAX que retorna los datos procesados para un widget específico.
    Delega en el dispatcher que importa el módulo de vistas del tablero
    y ejecuta la función correspondiente.
    """
    return dispatch_widget(request, widget_id)


def _get_request_data(request):
    """Extrae datos del request sin importar el método HTTP o content-type."""
    if request.content_type and "application/json" in request.content_type:
        return json.loads(request.body)
    if request.method == "POST":
        return request.POST
    if request.method == "PUT":
        try:
            return json.loads(request.body) if request.body else {}
        except (json.JSONDecodeError, AttributeError):
            return {}
    return request.GET


@csrf_exempt
@require_http_methods(["GET", "POST"])
def dashboard_widgets(request, dashboard_id):
    """GET: lista widgets de un dashboard. POST: crea un widget."""
    try:
        dashboard = Dashboard.objects.get(id=dashboard_id)
    except Dashboard.DoesNotExist:
        return JsonResponse({"error": "Dashboard no encontrado"}, status=404)

    if request.method == "GET":
        widgets = dashboard.widgets.all().values(
            "id", "title", "chart_type", "function_path", "properties", "order"
        )
        return JsonResponse(list(widgets), safe=False)

    try:
        data = _get_request_data(request)
        widget = WidgetInstance.objects.create(
            dashboard=dashboard,
            title=data.get("title", ""),
            chart_type=data.get("chart_type", "bar"),
            function_path=data.get("function_path", ""),
            properties=data.get("properties", {}),
            order=data.get("order", 0),
        )
        return JsonResponse({
            "id": widget.id,
            "title": widget.title,
            "chart_type": widget.chart_type,
            "function_path": widget.function_path,
            "properties": widget.properties,
            "order": widget.order,
        }, status=201)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def widget_detail(request, widget_id):
    """PUT: actualiza un widget. DELETE: elimina un widget."""
    try:
        widget = WidgetInstance.objects.get(id=widget_id)
    except WidgetInstance.DoesNotExist:
        return JsonResponse({"error": "Widget no encontrado"}, status=404)

    if request.method == "DELETE":
        widget.delete()
        return JsonResponse({"deleted": True})

    try:
        data = _get_request_data(request)
        for field in ("title", "chart_type", "function_path", "properties", "order"):
            if field in data:
                setattr(widget, field, data[field])
        widget.save()
        return JsonResponse({
            "id": widget.id,
            "title": widget.title,
            "chart_type": widget.chart_type,
            "function_path": widget.function_path,
            "properties": widget.properties,
            "order": widget.order,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def dashboard_filters(request, board_id):
    """POST: guarda un valor de filtro en la sesión, asociado a este dashboard."""
    try:
        Dashboard.objects.get(id=board_id)
    except Dashboard.DoesNotExist:
        return JsonResponse({"error": "Dashboard no encontrado"}, status=404)

    data = _get_request_data(request)
    field = data.get("field")
    if not field:
        return JsonResponse({"error": "field requerido"}, status=400)

    dashboard_filters = request.session.setdefault("dashboard_filters", {})
    dashboard_filters.setdefault(str(board_id), {})[field] = data.get("value")
    request.session.modified = True

    return JsonResponse({"ok": True})


def widget_functions(request):
    """
    Escanea sheets_reports/views_*.py y retorna las funciones disponibles
    agrupadas por módulo. Solo incluye funciones definidas por el usuario
    (no las importadas ni las privadas que empiezan con _).
    """
    views_dir = Path(__file__).parent
    modules = []

    for filepath in sorted(views_dir.glob("views_*.py")):
        if filepath.stem == "views_dashboard":
            continue
        module_name = f"sheets_reports.{filepath.stem}"
        module = importlib.import_module(module_name)

        functions = []
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_"):
                continue
            # Solo funciones definidas en este módulo, no importadas
            if getattr(obj, "__module__", None) == module_name:
                functions.append({
                    "path": f"{filepath.stem}.{name}",
                    "name": name,
                })

        if functions:
            modules.append({
                "module": filepath.stem.replace("views_", ""),
                "functions": functions,
            })

    return JsonResponse(modules, safe=False)
