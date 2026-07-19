import importlib
import inspect
import json

from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from sheets_reports.models import Dashboard, DashboardUtilFunction, WidgetInstance
from sheets_reports.utils.gemini_client import generate_widget_code as generate_code_from_prompt
from sheets_reports.utils.gemini_client import generate_custom_util as generate_custom_util_from_prompt
from sheets_reports.utils.registry import get_available_utils
from sheets_reports.utils.widget_dispatcher import dispatch_widget


def home(request):
    return render(request, 'home.html')


def board_editor(request, board_slug):
    dashboard = get_object_or_404(Dashboard, slug=board_slug)
    return render(request, 'board_editor.html', {'board_id': dashboard.id, 'dashboard': dashboard})


def board_view(request, board_slug):
    dashboard = get_object_or_404(Dashboard, slug=board_slug)
    return render(request, 'board_view.html', {'board_id': dashboard.id, 'dashboard': dashboard})


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
        # No se incluye "prompt": es de un solo uso (se limpia tras generar, ver
        # generateWidgetCode en dashboard-store.js) y el drawer nunca lo muestra al abrir.
        widgets = dashboard.widgets.all().values(
            "id", "title", "chart_type", "function_path", "code", "properties", "order"
        )
        return JsonResponse(list(widgets), safe=False)

    try:
        data = _get_request_data(request)
        widget = WidgetInstance.objects.create(
            dashboard=dashboard,
            title=data.get("title", ""),
            chart_type=data.get("chart_type", "bar"),
            function_path=data.get("function_path", ""),
            code=data.get("code", ""),
            prompt=data.get("prompt", ""),
            properties=data.get("properties", {}),
            order=data.get("order", 0),
        )
        return JsonResponse({
            "id": widget.id,
            "title": widget.title,
            "chart_type": widget.chart_type,
            "function_path": widget.function_path,
            "code": widget.code,
            "prompt": widget.prompt,
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
        for field in ("title", "chart_type", "function_path", "code", "prompt", "properties", "order"):
            if field in data:
                setattr(widget, field, data[field])
        widget.save()
        return JsonResponse({
            "id": widget.id,
            "title": widget.title,
            "chart_type": widget.chart_type,
            "function_path": widget.function_path,
            "code": widget.code,
            "prompt": widget.prompt,
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


@csrf_exempt
@require_http_methods(["POST"])
def generate_widget_code(request, dashboard_id):
    """POST: genera código Python para un widget a partir de un prompt en lenguaje natural, vía Gemini."""
    try:
        dashboard = Dashboard.objects.get(id=dashboard_id)
    except Dashboard.DoesNotExist:
        return JsonResponse({"error": "Dashboard no encontrado"}, status=404)

    data = _get_request_data(request)
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return JsonResponse({"error": "prompt requerido"}, status=400)

    # El chart_type se saca de la BD cuando el widget ya existe (fuente de verdad); si es un
    # widget nuevo que aún no se guardó, no hay fila en la BD y se usa el que mande el frontend.
    chart_type = data.get("chart_type", "")
    widget_id = data.get("widget_id")
    if widget_id:
        widget = WidgetInstance.objects.filter(id=widget_id, dashboard_id=dashboard_id).first()
        if widget:
            chart_type = widget.chart_type

    existing_code = data.get("existing_code", "")

    try:
        code = generate_code_from_prompt(prompt, dashboard, chart_type=chart_type, existing_code=existing_code)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"code": code})


def _serialize_util(u):
    return {
        "id": u.id,
        "name": u.name,
        "signature": u.signature,
        "description": u.description,
        "category": u.category,
        "source_code": u.source_code,
        "created_from_prompt": u.created_from_prompt,
        "is_active": u.is_active,
        "origin": "custom",
        "editable": True,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
def dashboard_util_functions(request, dashboard_id):
    """GET: lista las utilidades disponibles para el tablero (del sistema + personalizadas).
    POST: guarda una función utilitaria personalizada nueva (ya generada y revisada)."""
    try:
        dashboard = Dashboard.objects.get(id=dashboard_id)
    except Dashboard.DoesNotExist:
        return JsonResponse({"error": "Dashboard no encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(get_available_utils(dashboard), safe=False)

    data = _get_request_data(request)
    try:
        util_fn = DashboardUtilFunction.objects.create(
            dashboard=dashboard,
            name=data.get("name", ""),
            signature=data.get("signature", ""),
            description=data.get("description", ""),
            category=data.get("category") or "Personalizada",
            source_code=data.get("source_code", ""),
            created_from_prompt=data.get("prompt", ""),
        )
    except IntegrityError:
        return JsonResponse({"error": f"Ya existe una función llamada '{data.get('name', '')}' en este tablero."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse(_serialize_util(util_fn), status=201)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def util_function_detail(request, util_id):
    """PUT: actualiza una función utilitaria personalizada. DELETE: la elimina."""
    try:
        util_fn = DashboardUtilFunction.objects.get(id=util_id)
    except DashboardUtilFunction.DoesNotExist:
        return JsonResponse({"error": "Función no encontrada"}, status=404)

    if request.method == "DELETE":
        util_fn.delete()
        return JsonResponse({"deleted": True})

    data = _get_request_data(request)
    for field in ("name", "signature", "description", "category", "source_code", "is_active"):
        if field in data:
            setattr(util_fn, field, data[field])
    try:
        util_fn.save()
    except IntegrityError:
        return JsonResponse({"error": f"Ya existe una función llamada '{util_fn.name}' en este tablero."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse(_serialize_util(util_fn))


@csrf_exempt
@require_http_methods(["POST"])
def generate_custom_util(request, dashboard_id):
    """POST: genera (o modifica) una función utilitaria personalizada a partir de un prompt,
    vía Gemini. No la guarda: la retorna para que el usuario la revise antes de guardarla."""
    try:
        dashboard = Dashboard.objects.get(id=dashboard_id)
    except Dashboard.DoesNotExist:
        return JsonResponse({"error": "Dashboard no encontrado"}, status=404)

    data = _get_request_data(request)
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return JsonResponse({"error": "prompt requerido"}, status=400)
    existing_util = data.get("existing_util")

    try:
        util_data = generate_custom_util_from_prompt(prompt, dashboard, existing_util=existing_util)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse(util_data)


def widget_functions(request, board_slug):
    """
    Retorna los nombres de las funciones disponibles del tablero `board_slug`,
    leídas desde server_functions/<slug>/functions.py. Solo incluye funciones
    definidas por el usuario (no las importadas ni las privadas que empiezan con _).
    """
    dashboard = get_object_or_404(Dashboard, slug=board_slug)
    module_name = f"sheets_reports.server_functions.{dashboard.functions_slug}.functions"

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return JsonResponse([], safe=False)

    functions = [
        name for name, obj in inspect.getmembers(module, inspect.isfunction)
        if not name.startswith("_") and getattr(obj, "__module__", None) == module_name
    ]

    return JsonResponse(functions, safe=False)
