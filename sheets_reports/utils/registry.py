"""
Registro único de utilidades disponibles en el exec() de los widgets: las del sistema
(decoradas con @util en su propia definición, donde sea que vivan) más las personalizadas
de cada tablero (DashboardUtilFunction). Es la única fuente de verdad tanto para el texto
que se le manda a la IA (ver gemini_client.build_utils_reference) como para la UI del
editor (panel de "Funciones utilitarias del tablero").
"""
import inspect

UTILS_REGISTRY = []


def _strip_decorators(source: str) -> str:
    """Desde Python 3.8, inspect.getsource() de una función decorada incluye las líneas de
    sus decoradores (co_firstlineno apunta al primer @decorador, no al def). Nos quedamos
    solo desde el `def`, para que el source guardado sea la función tal cual, sin @util(...)."""
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("def ", "async def ")):
            return "\n".join(lines[i:])
    return source


def util(category, description, example=None):
    """Decorador que registra una función utilitaria del sistema junto con su metadata,
    incluyendo la función real (clave "fn") — así el exec() de los widgets se arma iterando
    el registro en vez de tener que importar y listar cada utilidad a mano en otro lado.
    Cada función se documenta una sola vez, en su propia definición."""
    def decorator(fn):
        UTILS_REGISTRY.append({
            "name": fn.__name__,
            "signature": str(inspect.signature(fn)),
            "category": category,
            "description": description,
            "example": example,
            "source_code": _strip_decorators(inspect.getsource(fn)),
            "fn": fn,
        })
        return fn
    return decorator


def ensure_loaded():
    """Los módulos que definen funciones @util solo se registran cuando algo los importa.
    Como generar el prompt de la IA (o armar el namespace de exec()) puede pasar antes de
    que se ejecute ningún widget (que es lo que normalmente los importaría), forzamos su
    import acá para garantizar que UTILS_REGISTRY esté completo. Import diferido (no al
    tope del archivo) para evitar un ciclo: esos módulos importan `util` desde este mismo
    archivo."""
    import sheets_reports.utils.cache  # noqa: F401 (registra get_cached_df)
    import sheets_reports.utils.chart_helpers  # noqa: F401 (registra distribucion_por_respuesta)
    import sheets_reports.utils.table_helpers  # noqa: F401 (registra tabla_conteo_por_respuesta)
    import sheets_reports.utils.widget_dispatcher  # noqa: F401 (registra apply_active_filters, get_active_filters)


def get_system_namespace() -> dict:
    """Dict {nombre: función} con todas las utilidades del sistema, listo para mezclar en
    el namespace de exec() de un widget (ver widget_dispatcher._build_exec_namespace)."""
    ensure_loaded()
    return {u["name"]: u["fn"] for u in UTILS_REGISTRY}


def get_available_utils(dashboard):
    """Combina las utilidades del sistema (UTILS_REGISTRY) con las personalizadas del
    tablero (DashboardUtilFunction), en un único formato para la UI y el prompt de la IA."""
    ensure_loaded()

    utils = [
        {**{k: v for k, v in u.items() if k != "fn"}, "origin": "system", "editable": False}
        for u in UTILS_REGISTRY
    ]

    for u in dashboard.custom_utils.filter(is_active=True):
        utils.append({
            "id": u.id,
            "name": u.name,
            "signature": u.signature,
            "category": u.category,
            "description": u.description,
            "example": None,
            "source_code": u.source_code,
            "origin": "custom",
            "editable": True,
        })

    return utils
