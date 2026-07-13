import importlib
import logging

from django.http import JsonResponse

from sheets_reports.models import WidgetInstance
from sheets_reports.utils.cache import get_cached_df

logger = logging.getLogger(__name__)


def _import_function(function_path: str):
    """
    Importa una función desde un path como 'views_ventas_norte.total_ventas'.
    Retorna (module, function_name, error_response).
    """
    parts = function_path.split(".")
    if len(parts) < 2:
        return None, None, JsonResponse(
            {"error": f"function_path inválido: '{function_path}'. Debe ser 'modulo.funcion'."},
            status=400,
        )

    func_name = parts[-1]
    module_path = "sheets_reports." + ".".join(parts[:-1])

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        logger.exception("Módulo %s no encontrado", module_path)
        return None, None, JsonResponse(
            {"error": f"Módulo '{module_path}' no encontrado"},
            status=500,
        )

    func = getattr(module, func_name, None)
    if func is None:
        return None, None, JsonResponse(
            {"error": f"Función '{func_name}' no encontrada en {module_path}"},
            status=500,
        )

    return module, func_name, None


def dispatch_widget(request, widget_id: int) -> JsonResponse:
    """
    Obtiene el widget, importa el módulo desde widget.function_path,
    y ejecuta la función correspondiente.
    """
    try:
        widget = WidgetInstance.objects.select_related("dashboard").get(id=widget_id)
    except WidgetInstance.DoesNotExist:
        return JsonResponse({"error": "Widget no encontrado"}, status=404)

    module, func_name, error = _import_function(widget.function_path)
    if error:
        return error

    func = getattr(module, func_name)

    try:
        df = get_cached_df(widget.dashboard)
    except Exception:
        logger.exception("Error al obtener datos de Google Sheets")
        return JsonResponse(
            {"error": "Error al obtener datos de la hoja de cálculo"},
            status=500,
        )

    return func(df, request, widget)
