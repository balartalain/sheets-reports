import importlib
import logging

from django.http import JsonResponse

from sheets_reports.models import WidgetInstance

logger = logging.getLogger(__name__)


def _import_function(func_name: str, board_slug: str):
    """
    Importa una función por su nombre desde server_functions/<board_slug>/functions.py.
    Retorna (module, function_name, error_response).
    """
    if not func_name:
        return None, None, JsonResponse(
            {"error": "El widget no tiene una función asignada."},
            status=400,
        )

    module_path = f"sheets_reports.server_functions.{board_slug}.functions"

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


def get_active_filters(request, widget) -> dict:
    """Filtros activos guardados en sesión para el tablero de este widget: {campo: valor}."""
    return request.session.get("dashboard_filters", {}).get(str(widget.dashboard_id), {})


def apply_active_filters(df, request, widget):
    """
    Aplica los filtros activos del tablero al DataFrame, comparando cada
    filtro contra la columna del mismo nombre (si existe). Filtros sin valor,
    o cuyo nombre no coincide con ninguna columna, se ignoran.
    """
    if df.empty:
        return df
    for field, value in get_active_filters(request, widget).items():
        if not value or field not in df.columns:
            continue
        df = df[df[field].astype(str) == str(value)]
    return df


def dispatch_widget(request, widget_id: int) -> JsonResponse:
    """
    Obtiene el widget, importa el módulo desde widget.function_path,
    y ejecuta la función correspondiente.

    Convención: cada función recibe (request, widget) y es responsable de cargar
    su(s) propio(s) DataFrame llamando a `get_cached_df(widget.dashboard, sheet_name)`
    (sheet_name=None usa la primera hoja). Así una misma función puede leer más de
    una pestaña del spreadsheet del tablero y cruzarlas entre sí.

    Convención para filtros: cada función puede aplicar los filtros activos
    de su tablero al DataFrame con `apply_active_filters(df, request, widget)`
    (o leerlos directamente con `get_active_filters(request, widget)`).
    """
    try:
        widget = WidgetInstance.objects.select_related("dashboard").get(id=widget_id)
    except WidgetInstance.DoesNotExist:
        return JsonResponse({"error": "Widget no encontrado"}, status=404)

    module, func_name, error = _import_function(widget.function_path, widget.dashboard.functions_slug)
    if error:
        return error

    func = getattr(module, func_name)

    try:
        return func(request, widget)
    except Exception as e:
        logger.exception("Error al ejecutar %s", widget.function_path)
        return JsonResponse({"error": str(e)}, status=500)
