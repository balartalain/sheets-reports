import builtins
import importlib
import logging

from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse

from sheets_reports.models import WidgetInstance
from sheets_reports.utils.registry import get_system_namespace, util

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


class _NumpyPandasJSONEncoder(DjangoJSONEncoder):
    """
    Serializa tipos de numpy/pandas que el código de widgets suele producir sin darse cuenta
    (ej. df.groupby(...).sum() retorna numpy.int64, no un int nativo). Sin esto, cualquier
    widget que use groupby/sum/value_counts de pandas puede fallar con
    "Object of type int64 is not JSON serializable".
    """

    def default(self, o):
        import numpy as np
        import pandas as pd

        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, pd.Timestamp):
            return o.isoformat()
        if o is pd.NaT or (isinstance(o, float) and pd.isna(o)):
            return None
        return super().default(o)


def _widget_json_response(data=None, **kwargs):
    """JsonResponse inyectado en el exec() de widgets: usa un encoder que tolera tipos
    numpy/pandas, para que el código generado no tenga que castear manualmente cada valor."""
    kwargs.setdefault("encoder", _NumpyPandasJSONEncoder)
    return JsonResponse(data, **kwargs)


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


@util(
    category="Filtros",
    description="Filtros activos guardados en sesión para el tablero de este widget: {campo: valor}.",
    example="active_filters = get_active_filters(request, widget)",
)
def get_active_filters(request, widget) -> dict:
    return request.session.get("dashboard_filters", {}).get(str(widget.dashboard_id), {})


@util(
    category="Filtros",
    description=(
        "Aplica los filtros activos del tablero a un DataFrame, comparando cada filtro contra "
        "la columna del mismo nombre (si existe). Filtros sin valor, o cuyo nombre no coincide "
        "con ninguna columna, se ignoran."
    ),
    example="df = apply_active_filters(df, request, widget)",
)
def apply_active_filters(df, request, widget):
    if df.empty:
        return df
    for field, value in get_active_filters(request, widget).items():
        if not value or field not in df.columns:
            continue
        df = df[df[field].astype(str) == str(value)]
    return df


class CustomUtilError(Exception):
    """Una función utilitaria personalizada del tablero (DashboardUtilFunction) no compiló."""


def _build_exec_namespace(dashboard=None):
    """
    Contexto disponible para el código Python guardado en widget.code (generado por IA).
    Las utilidades del sistema se toman todas del registro (sheets_reports.utils.registry),
    en vez de importarlas y listarlas una por una acá: decorar una función con @util ya
    alcanza para que quede disponible en el exec(), sin tocar este archivo.

    Las funciones utilitarias personalizadas del tablero (DashboardUtilFunction) se ejecutan
    en este mismo namespace antes de devolverlo, para que queden disponibles cuando se
    ejecute el código propio del widget a continuación.
    """
    import pandas as pd

    namespace = {
        "__builtins__": SAFE_BUILTINS,
        "pd": pd,
        "JsonResponse": _widget_json_response,
        **get_system_namespace(),
    }

    if dashboard is not None:
        for custom_util in dashboard.custom_utils.filter(is_active=True):
            try:
                exec(custom_util.source_code, namespace)
            except Exception as e:
                raise CustomUtilError(f"{custom_util.name}: {e}") from e

    return namespace


def execute_widget_code(code: str, request, widget) -> JsonResponse:
    """
    Ejecuta el código Python guardado en widget.code. El código debe definir
    `def run(request, widget):` que retorna un JsonResponse (misma convención de
    retorno que las funciones basadas en archivo).
    """
    try:
        namespace = _build_exec_namespace(widget.dashboard)
    except CustomUtilError as e:
        logger.exception("Error al compilar las funciones utilitarias del tablero %s", widget.dashboard_id)
        return JsonResponse({"error": f"Error en las funciones utilitarias del tablero: {e}"}, status=500)

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
