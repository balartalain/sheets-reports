import importlib
import logging

from django.http import JsonResponse

from sheets_reports.models import WidgetInstance
from sheets_reports.utils.cache import get_cached_df

logger = logging.getLogger(__name__)


def dispatch_widget(request, widget_id: int) -> JsonResponse:
    """
    Obtiene el widget, importa el módulo de vistas correspondiente al dashboard,
    y ejecuta la función definida en widget.function_name.
    """
    try:
        widget = WidgetInstance.objects.select_related("dashboard").get(id=widget_id)
    except WidgetInstance.DoesNotExist:
        return JsonResponse({"error": "Widget no encontrado"}, status=404)

    module_name = f"sheets_reports.views_{widget.dashboard.view_module}"

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        logger.exception("Módulo %s no encontrado", module_name)
        return JsonResponse(
            {"error": f"Módulo de vistas '{module_name}' no encontrado"},
            status=500,
        )

    func = getattr(module, widget.function_name, None)
    if func is None:
        return JsonResponse(
            {"error": f"Función '{widget.function_name}' no encontrada en {module_name}"},
            status=500,
        )

    try:
        df = get_cached_df(widget.dashboard)
    except Exception:
        logger.exception("Error al obtener datos de Google Sheets")
        return JsonResponse(
            {"error": "Error al obtener datos de la hoja de cálculo"},
            status=500,
        )

    return func(df, request, widget)
