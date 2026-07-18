import builtins
import importlib
import logging

from django.http import JsonResponse

from sheets_reports.models import WidgetInstance

logger = logging.getLogger(__name__)

# Whitelist de builtins seguros disponibles para el código de widget generado por IA.
# Deliberadamente excluye open, __import__, exec, eval, compile, etc.
_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
    "int", "len", "list", "map", "max", "min", "range", "repr", "reversed",
    "round", "set", "sorted", "str", "sum", "tuple", "zip", "print",
    "isinstance", "None", "True", "False",
    "Exception", "ValueError", "KeyError", "TypeError", "StopIteration",
)
SAFE_BUILTINS = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES if hasattr(builtins, name)}


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


def _build_exec_namespace():
    """
    Contexto disponible para el código Python guardado en widget.code (generado por IA).
    Expone las mismas utilidades que ya usan las funciones basadas en archivo, para que
    el código generado no necesite (ni pueda) hacer imports propios.
    """
    import pandas as pd

    from sheets_reports.utils.cache import get_cached_df
    from sheets_reports.utils.chart_helpers import distribucion_por_respuesta
    from sheets_reports.utils.table_helpers import tabla_conteo_por_respuesta

    return {
        "__builtins__": SAFE_BUILTINS,
        "pd": pd,
        "get_cached_df": get_cached_df,
        "apply_active_filters": apply_active_filters,
        "get_active_filters": get_active_filters,
        "distribucion_por_respuesta": distribucion_por_respuesta,
        "tabla_conteo_por_respuesta": tabla_conteo_por_respuesta,
        "JsonResponse": JsonResponse,
    }


def execute_widget_code(code: str, request, widget) -> JsonResponse:
    """
    Ejecuta el código Python guardado en widget.code. El código debe definir
    `def run(request, widget):` que retorna un JsonResponse (misma convención de
    retorno que las funciones basadas en archivo).
    """
    namespace = _build_exec_namespace()
    try:
        exec(code, namespace)
    except Exception as e:
        logger.exception("Error al compilar el código del widget %s", widget.id)
        return JsonResponse({"error": f"Error en el código del widget: {e}"}, status=500)

    run = namespace.get("run")
    if not callable(run):
        return JsonResponse(
            {"error": "El código del widget debe definir una función run(request, widget)."},
            status=500,
        )

    try:
        return run(request, widget)
    except Exception as e:
        logger.exception("Error al ejecutar el código del widget %s", widget.id)
        return JsonResponse({"error": str(e)}, status=500)


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

    if widget.code:
        return execute_widget_code(widget.code, request, widget)

    module, func_name, error = _import_function(widget.function_path, widget.dashboard.functions_slug)
    if error:
        return error

    func = getattr(module, func_name)

    try:
        return func(request, widget)
    except Exception as e:
        logger.exception("Error al ejecutar %s", widget.function_path)
        return JsonResponse({"error": str(e)}, status=500)
