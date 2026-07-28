import json
import logging

from django.conf import settings
from google import genai

from sheets_reports.utils.cache import get_cached_tables
from sheets_reports.utils.registry import get_available_utils

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"

SYSTEM_INSTRUCTION_TEMPLATE = """\
Eres un generador de código Python para widgets de un dashboard interno de reportes.

Debes responder ÚNICAMENTE con código Python (sin explicación, sin markdown, sin ```),
que defina EXACTAMENTE una función con esta firma:

    def run(request, widget):
        ...
        return JsonResponse(...)

No hagas ningún `import`: ya tenés disponibles, inyectadas en el contexto de ejecución, `pd`
(pandas), `datetime` (el módulo estándar, para operar con fechas), `JsonResponse` (no la
redefinas) y las utilidades listadas abajo.

__UTILS_REFERENCE__

No uses `open`, `os`, `subprocess`, `__import__`, `eval`, `exec`, ni accedas a atributos
dunder — no están disponibles y el código fallará.

Para obtener los datos, usá SIEMPRE `get_query_connection(widget.dashboard)`, que retorna una
conexión DuckDB con las tablas del origen de datos de este tablero ya registradas/adjuntas
(sin importar si el origen es una hoja de cálculo, una base de datos SQL, etc. — la forma de
consultarlas es siempre la misma):

    con = get_query_connection(widget.dashboard)

Usá siempre el nombre EXACTO de tabla que se muestra abajo en la estructura del origen de
datos (según el tipo de origen puede ser, por ejemplo, `google_sheets__Ventas` o
`postgres.public.ventas` — nunca lo inventes ni lo adivines, copialo tal cual aparece abajo).
Para pasar valores dinámicos a la consulta (ej. un filtro activo), usá parámetros en vez de
interpolar el string a mano: `con.execute("SELECT * FROM tabla WHERE region = ?", [valor])`.
No generes `INSERT`/`UPDATE`/`DELETE` ni DDL: algunos orígenes son de solo lectura y esas
sentencias van a fallar. No uses `get_cached_df` en código nuevo — existe solo por
compatibilidad con widgets ya guardados de antes de que hubiera SQL genérico.

TODO el procesamiento de datos (conversiones de tipo, filtrado de nulos, agregaciones,
ordenamiento, formateo de fechas, etc.) debés hacerlo DENTRO de la consulta SQL, no con
pandas. DuckDB soporta `CAST`, `TRY_CAST`, `SUM`, `COUNT`, `GROUP BY`, `ORDER BY`, `WHERE`,
funciones de fecha, etc. — usá todo eso directamente en SQL. No recorras ni transformes el
resultado con pandas después de la consulta.

Al final, convertí el resultado a listas Python usando `.fetchall()` o `.df()` solo para
extraer los valores y armar el JsonResponse:

    rows = con.execute("SELECT categoria, SUM(ventas) FROM ... GROUP BY ...").fetchall()
    categories = [r[0] for r in rows]
    data_values = [r[1] for r in rows]

NO uses pandas para agrupar, sumar, filtrar, ordenar, ni ninguna otra operación de datos.
Todo eso va en DuckDB SQL.

El tipo de widget (chart_type) determina el shape exacto que `run` debe retornar en el
JsonResponse:
- bar / line / donut: {"series": [{"name": str, "data": [numeros]}], "categories": [etiquetas]}
- kpi: {"main_value": numero, "main_label": str, "secondary_values": [{"label": str, "value": numero}, ...]}
- table: {"columns": [{"title": str, "field": str}, ...], "rows": [{...}, ...]}
- filter: {"options": [valor, ...] | [{"value":..., "label":...}, ...], "selected": valor|null, "field": "<nombre exacto de columna>"}
Si no se te indica el chart_type explícitamente, infiérelo de la descripción del usuario.

Para widgets con chart_type="filter": vos mismo elegís, a partir del prompt del usuario y de
la estructura del origen de datos que se te muestra abajo, el nombre EXACTO de la columna que
este filtro va a controlar. No leas widget.filter_field para esto (puede no existir todavía
la primera vez que tu código corre) — usá el nombre de columna directamente como literal de
texto en tu código, ej. active_filters.get("Nivel", None) para obtener el valor actualmente
seleccionado. Devolvé ese mismo nombre de columna en tu respuesta bajo la clave "field", como
en el shape de arriba, para que el sistema lo guarde automáticamente en el widget.

Para widgets que NO son filter (bar, line, donut, kpi, table): obtené los filtros activos
con `active_filters = get_active_filters(request, widget)` y usá sus valores como
parámetros en tu consulta SQL, ej.:
    con.execute("SELECT * FROM tabla WHERE region = ?", [active_filters.get("region")])
Los widgets tipo filter NO deben filtrarse a sí mismos — deben mostrar todas las opciones
disponibles sin aplicar ningún filtro. Usá `get_active_filters` solo para preseleccionar
el valor actual: `selected = active_filters.get("<campo>", None)`.

Abajo se te muestran las columnas y filas de ejemplo de TODAS las pestañas del spreadsheet de
este tablero. Elegí la pestaña que mejor corresponda a lo que pide el usuario (si el prompt
nombra una pestaña explícitamente, se te marca como tal: priorizala salvo que sea claramente
incorrecta para lo que pide) y usá su nombre EXACTO en
get_cached_df(widget.dashboard, sheet_name='<nombre exacto>'). Especificá siempre sheet_name
explícitamente, incluso si es la primera pestaña — nunca lo omitas ni lo dejes en None.

Abajo se te muestra la estructura de las tablas disponibles en el origen de datos de este
tablero: sus columnas y filas de ejemplo. Elegí la(s) tabla(s) que mejor correspondan a lo que
pide el usuario (si el prompt nombra una tabla explícitamente, se te marca como tal: priorizala
salvo que sea claramente incorrecta para lo que pide) y usá su nombre EXACTO en la consulta SQL.

Tu respuesta debe ser SIEMPRE la función run(request, widget) completa y final, no un fragmento.
Si se te muestra el código ya existente de este widget, conservá su lógica salvo lo que el
prompt pida cambiar explícitamente, y modificá únicamente eso.
"""


CUSTOM_UTIL_SYSTEM_INSTRUCTION = """\
Eres un generador de funciones utilitarias reutilizables para un dashboard de reportes. Cada
función que generes podrá ser llamada, por su nombre, desde el código de cualquier widget de
este tablero (y desde otras funciones utilitarias personalizadas del mismo tablero).

Reglas:
- La función debe ser autocontenida: no hagas ningún `import` (ya tenés disponibles `pd` y
  `datetime`, sin necesidad de importarlos, más las utilidades ya existentes del tablero que
  se listan abajo).
- No uses `open`, `os`, `subprocess`, `__import__`, `eval`, `exec`, ni accedas a atributos dunder.
- Sé defensiva: verificá que las columnas que uses existan antes de acceder a ellas, ya que la
  función puede ser llamada con distintos DataFrames.
- Si se te pasa una función ya existente para modificar, conservá su nombre y su comportamiento
  salvo lo que el prompt pida cambiar explícitamente.

Respondé ÚNICAMENTE con un objeto JSON (sin markdown, sin ```) con estas claves:
- "name": nombre de la función en snake_case, válido como identificador Python.
- "signature": la firma de la función, solo los parámetros entre paréntesis, ej.
  "(df, columna: str, excluir=())".
- "category": una categoría corta en español que agrupe funciones similares (ej. "Filtros",
  "Columnas calculadas", "Formato").
- "description": 1-3 frases en español explicando qué hace la función y cuándo usarla.
- "source_code": el código Python COMPLETO de la función, incluyendo su `def nombre(...):` y
  docstring opcional, sin decoradores, sin imports, y sin ```.
"""

CUSTOM_UTIL_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "signature": {"type": "string"},
        "category": {"type": "string"},
        "description": {"type": "string"},
        "source_code": {"type": "string"},
    },
    "required": ["name", "signature", "category", "description", "source_code"],
}


def build_utils_reference(dashboard) -> str:
    """
    Arma el texto que se le muestra a la IA (y potencialmente a la UI) con todas las
    utilidades disponibles en el exec() de los widgets de este tablero: las del sistema
    (UTILS_REGISTRY) más las personalizadas de este tablero (DashboardUtilFunction),
    combinadas por sheets_reports.utils.registry.get_available_utils — única fuente de
    verdad para ambos usos.
    """
    utils = get_available_utils(dashboard)
    if not utils:
        return "(no hay utilidades disponibles)"

    by_category = {}
    for u in utils:
        by_category.setdefault(u["category"], []).append(u)

    lines = []
    for category in sorted(by_category):
        lines.append(f"### {category}")
        for u in by_category[category]:
            origin_note = " (definida por el usuario en este tablero)" if u["origin"] == "custom" else ""
            lines.append(f"- {u['name']}{u['signature']}{origin_note}")
            if u.get("description"):
                lines.append(f"  {u['description']}")
            if u.get("example"):
                lines.append(f"  Ejemplo: {u['example']}")
        lines.append("")
    return "\n".join(lines).strip()


def _build_system_instruction(dashboard) -> str:
    return SYSTEM_INSTRUCTION_TEMPLATE.replace("__UTILS_REFERENCE__", build_utils_reference(dashboard))


def _detect_table_name(prompt: str, names: list[str]) -> str | None:
    """Busca, case-insensitive, si el prompt del usuario menciona el nombre exacto de alguna
    de las tablas/pestañas dadas. Retorna el nombre exacto o None."""
    prompt_lower = prompt.lower()
    for name in names:
        if name.lower() in prompt_lower:
            return name
    return None


def _build_source_context(dashboard, prompt: str) -> str:
    """
    Arma el bloque de estructura del origen de datos que se le muestra a Gemini: tablas/pestañas
    disponibles, sus columnas y unas pocas filas de ejemplo, vía DataConnector.list_tables()
    (funciona igual para Google Sheets y Postgres), para que la IA pueda elegir la tabla correcta
    sin que el usuario tenga que nombrarla explícitamente en su descripción. Si el prompt sí
    menciona el nombre exacto de una tabla, se la marca para que Gemini le dé prioridad en caso
    de ambigüedad.

    El nombre que se muestra por cada tabla es el que arma
    DataConnector.qualified_table_name(table, alias) -- el mismo esquema de nombres que usa
    get_query_connection al registrar/adjuntar el origen (ver duckdb_query.py) -- y no el
    TableInfo.name "crudo" de list_tables(). Mostrar el nombre crudo acá sería un bug: no
    coincidiría con lo que la conexión DuckDB real expone (ej. mostraría "Destinatarios"
    cuando la tabla consultable es "google_sheets__Destinatarios"), y Gemini terminaría
    adivinando el prefijo/esquema en vez de copiarlo tal cual.
    """
    connector = dashboard.data_source.get_connector()
    alias = dashboard.data_source.source_type
    try:
        tables = get_cached_tables(dashboard)
    except Exception as e:
        return f"(no se pudo leer la estructura del origen de datos: {e})"
    if not tables:
        return "(el origen de datos no tiene tablas)"

    hinted = _detect_table_name(prompt, [t.name for t in tables])

    lines = []
    for table in tables:
        qualified_name = connector.qualified_table_name(table, alias)
        marker = " (mencionada explícitamente por el usuario)" if table.name == hinted else ""
        lines.append(f"Tabla '{qualified_name}'{marker}")
        if table.columns:
            lines.append(f"  Columnas: {table.columns}")
            lines.append(f"  Filas de ejemplo: {table.sample_rows}")
        else:
            lines.append("  (vacía)")
    return "\n".join(lines)


def _strip_markdown_fences(code: str) -> str:
    code = code.strip()
    if code.startswith("```"):
        lines = code.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)
    return code.strip()


def _call_gemini(full_prompt: str, system_instruction: str) -> str:
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY no está configurado en .env")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=full_prompt,
        config={"system_instruction": system_instruction},
    )

    code = (response.text or "").strip()
    if not code:
        raise ValueError("Gemini no devolvió código.")

    return _strip_markdown_fences(code)


def generate_widget_code(prompt: str, dashboard, chart_type: str = "", existing_code: str = "") -> str:
    """
    Genera (o modifica) código Python para un widget a partir de una descripción en lenguaje
    natural, usando Gemini. `chart_type` (bar/line/donut/kpi/table/filter) es opcional: si se
    conoce (ej. leído del widget en la BD), se le indica explícitamente a Gemini; si no, Gemini
    lo infiere de la descripción. `existing_code`, si se pasa, es el código actual del widget
    (ej. el draft del textarea): se le muestra a Gemini para que pueda hacer un cambio puntual
    sin perder el resto de la lógica. Retorna el código completo, listo para guardar en
    WidgetInstance.code.
    """
    source_context = _build_source_context(dashboard, prompt)

    chart_type_line = f"Tipo de widget (chart_type): {chart_type}\n\n" if chart_type else ""
    existing_code_block = (
        f"Código YA existente de este widget (modificalo si el prompt lo pide; si no, dejalo "
        f"tal cual en tu respuesta):\n{existing_code}\n\n"
        if existing_code else ""
    )
    full_prompt = (
        f"{chart_type_line}"
        f"{existing_code_block}"
        f"Estructura de las tablas disponibles en el origen de datos de este tablero:\n"
        f"{source_context}\n\n"
        f"Descripción del usuario:\n{prompt}"
    )

    return _call_gemini(full_prompt, _build_system_instruction(dashboard))


def generate_custom_util(prompt: str, dashboard, existing_util: dict | None = None) -> dict:
    """
    Genera (o modifica) una función utilitaria personalizada del tablero a partir de una
    descripción en lenguaje natural, usando Gemini. `existing_util`, si se pasa, es un dict
    con al menos `name`/`source_code` de la función actual (ej. la que se está editando): se
    le muestra a Gemini para que la modifique sin perder su nombre ni su comportamiento.
    Retorna un dict con name/signature/category/description/source_code, listo para revisar
    y guardar en un DashboardUtilFunction.
    """
    source_context = _build_source_context(dashboard, prompt)
    utils_reference = build_utils_reference(dashboard)

    existing_block = ""
    if existing_util and existing_util.get("source_code"):
        existing_block = (
            f"Función YA existente (modificala si el prompt lo pide; si no, dejala tal cual "
            f"en tu respuesta):\nnombre: {existing_util.get('name', '')}\n"
            f"código:\n{existing_util['source_code']}\n\n"
        )

    full_prompt = (
        f"Utilidades ya disponibles en este tablero (no las redefinas, ya las podés llamar):\n"
        f"{utils_reference}\n\n"
        f"{existing_block}"
        f"Estructura de las tablas disponibles en el origen de datos de este tablero:\n"
        f"{source_context}\n\n"
        f"Descripción del usuario:\n{prompt}"
    )

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY no está configurado en .env")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=full_prompt,
        config={
            "system_instruction": CUSTOM_UTIL_SYSTEM_INSTRUCTION,
            "response_mime_type": "application/json",
            "response_schema": CUSTOM_UTIL_RESPONSE_SCHEMA,
        },
    )

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Gemini no devolvió una función.")

    data = json.loads(text)
    data["source_code"] = _strip_markdown_fences(data.get("source_code", ""))
    return data
