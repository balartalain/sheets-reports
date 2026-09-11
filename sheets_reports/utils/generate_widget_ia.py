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

Usá el nombre EXACTO de tabla de abajo (`google_sheets__Ventas`, `postgres.public.ventas`)
— nunca lo inventes ni adivines. Usá parámetros en vez de interpolar:
`con.execute("SELECT * FROM tabla WHERE region = ?", [valor])`.
No generes INSERT/UPDATE/DELETE ni DDL (orígenes de solo lectura).

Para condiciones con una LISTA de valores (ej. `WHERE columna IN (...)` / `NOT IN (...)` con
varios elementos), armá placeholders "?" repetidos y pasá la lista completa como parámetros —
nunca insertes los valores citándolos a mano dentro del string SQL:
    placeholders = ", ".join(["?"] * len(valores))
    con.execute(f'SELECT * FROM tabla WHERE "col" NOT IN ({placeholders})', valores)
Nunca anides un f-string dentro de otro usando el mismo tipo de comilla que el f-string
externo — rompe con "f-string: unterminated string" (ej. f'... {f"'{x}'" ...} ...' es
inválido). Si necesitás armar un string con comillas antes de interpolarlo, calculalo primero
en una variable aparte y después metela en el f-string.

TODO el procesamiento de datos (conversiones de tipo, filtrado de nulos, agregaciones,
ordenamiento, formateo de fechas, etc.) debés hacerlo DENTRO de la consulta SQL, no con
pandas. DuckDB soporta `CAST`, `TRY_CAST`, `SUM`, `COUNT`, `GROUP BY`, `ORDER BY`, `WHERE`,
funciones de fecha, etc. — usá todo eso directamente en SQL.
Si una columna contiene fechas pero está almacenada como texto (VARCHAR), usá
`CAST(columna AS TIMESTAMP)` o `TRY_CAST(columna AS TIMESTAMP)` antes de aplicar
funciones como `strftime`, `date_trunc`, etc. No recorras ni transformes el
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

Para widgets que NO son filter (bar, line, donut, kpi, table): TODOS deben respetar
implícitamente TODOS los filtros que estén activos en el tablero, aunque el usuario no lo
pida explícitamente en su prompt — es el comportamiento por default, no una excepción.
Solo dejá de aplicar un filtro puntual si el prompt del usuario lo pide explícitamente para
ESE widget (ej. "este gráfico no debe filtrarse por año").

Para lograrlo, usá SIEMPRE la utilidad `build_filters_where` (ver utilidades abajo) en vez de
armar el WHERE a mano filtrando por un único campo que creas relevante: te devuelve la cláusula
ya armada y parametrizada con TODOS los filtros activos, ignorando automáticamente los que no
correspondan a la tabla que estás consultando (no hace falta que vos mismo verifiques cuáles
aplican):
    where_sql, params = build_filters_where(con, table_name, request, widget)
    con.execute(f'SELECT * FROM "{table_name}"{where_sql}', params)
Solo evitá usarla si el prompt del usuario pide explícitamente que ESE widget no respete algún
filtro puntual — en ese caso armá el WHERE a mano, excluyendo ese campo.
El WHERE puede referenciar columnas que no estén en el SELECT sin problema — no hace falta
que la tabla incluya todas en el resultado final, solo que existan en ella.

Si además necesitás agregar una condición propia del widget (ej. "solo donde la columna X sea
'Sí'"), usá SIEMPRE `add_where_conditions` (ver utilidades abajo) — NUNCA intentes combinarlo
vos mismo concatenando `AND` o envolviendo `where_sql` entre paréntesis: `where_sql` puede venir
vacío (sin filtros activos, el caso normal la primera vez que se abre el tablero) o ya traer el
`WHERE` incluido, y adivinar cuál de los dos casos es rompe con
`Parser Error: syntax error at or near "AND"` (si concatenás `AND` cuando está vacío) o
`Parser Error: syntax error at or near "WHERE"` (si lo envolvés entre paréntesis asumiendo que
es una condición pelada, cuando en realidad ya trae el `WHERE`). `add_where_conditions` resuelve
esto por vos, sin que tengas que razonar sobre ninguno de los dos casos:
    where_sql, params = build_filters_where(con, table_name, request, widget)
    where_sql, params = add_where_conditions(
        where_sql, params, ['"columna" = ?'], [valor_extra],
    )
    con.execute(f'SELECT COUNT(*) FROM "{table_name}"{where_sql}', params)

Los widgets tipo filter NO deben filtrarse a sí mismos — deben mostrar todas las opciones
disponibles sin aplicar ningún filtro. Usá `get_active_filters` solo para preseleccionar
el valor actual: `selected = active_filters.get("<campo>", None)`.

Abajo se te muestra la estructura de las tablas disponibles en el origen de datos de este
tablero: sus columnas y filas de ejemplo. Elegí la(s) tabla(s) que mejor correspondan a lo que
pide el usuario (si el prompt nombra una tabla explícitamente, se te marca como tal: priorizala
salvo que sea claramente incorrecta para lo que pide) y usá su nombre EXACTO en la consulta SQL.

Tu respuesta debe ser SIEMPRE la función run(request, widget) completa y final, no un fragmento.
Si se te muestra el código ya existente de este widget, conservá su lógica salvo lo que el
prompt pida cambiar explícitamente, y modificá únicamente eso.
"""


SUMMARY_SYSTEM_INSTRUCTION = """\
Eres un redactor que traduce el código técnico de un widget de un dashboard a una
explicación breve y NO TÉCNICA, para que cualquier persona sin conocimientos de
programación entienda, con solo leerla, qué está mostrando ese widget.

Reglas:
- Una sola oración, en español, en tono neutro, de no más de ~160 caracteres.
- NUNCA menciones SQL, código, Python, DuckDB, "chart_type", ni nombres crudos de
  tablas/columnas. Traducilos a lenguaje de negocio (ej.: en vez de
  "SUM(ventas) GROUP BY region", decí "el total de ventas por región").
- Si el código filtra o agrupa por algo (región, mes, categoría, etc.), mencionalo.
- No repitas el título tal cual si ya es autoexplicativo: agregá información útil.
- No uses comillas ni markdown. Respondé ÚNICAMENTE con el texto del resumen.
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

CALCULATED_COLUMN_SYSTEM_INSTRUCTION = """\
Eres un generador de expresiones SQL para DuckDB que crean columnas calculadas a partir de
columnas ya existentes en una tabla de un dashboard de reportes.

Reglas:
- Tu respuesta va en el campo "expression": debe ser ÚNICAMENTE una expresión SQL de DuckDB
  válida — NO una sentencia completa (nada de SELECT, FROM, CREATE, ni punto y coma). Tiene
  que poder usarse tal cual dentro de: SELECT (tu_expresión) AS "nombre_columna" FROM tabla.
- Podés usar CASE WHEN ... END, funciones de texto (LOWER, UPPER, LIKE, REGEXP_MATCHES,
  TRIM, CONCAT), de fecha (CAST/TRY_CAST AS TIMESTAMP, date_trunc, strftime), aritmética,
  COALESCE, etc. — cualquier expresión válida de DuckDB.
- Referenciá SIEMPRE las columnas reales entre comillas dobles, usando el nombre EXACTO que
  se te muestra abajo (ej. "Período que está cursando"), nunca inventado.
- Si una columna con datos de fecha está guardada como texto (VARCHAR), usá
  TRY_CAST(columna AS TIMESTAMP) antes de aplicar funciones de fecha.
- "column_name": elegí un nombre corto y descriptivo en español, como los ya usados en la
  tabla (ej. "Nivel"). Si se te muestra una columna ya existente para modificar, conservá su
  nombre salvo que el prompt pida explícitamente cambiarlo.
- "description": 1-2 frases en español, en lenguaje NO técnico, explicando qué representa la
  columna resultante (se usa después para que la IA de generación de widgets entienda para
  qué sirve, y para mostrarla en la UI de gestión).

Respondé ÚNICAMENTE con un objeto JSON (sin markdown, sin ```) con las claves "column_name",
"expression" y "description".
"""

CALCULATED_COLUMN_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "column_name": {"type": "string"},
        "expression": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["column_name", "expression", "description"],
}


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

    calc_cols_by_table = {}
    for cc in dashboard.data_source.calculated_columns.filter(is_active=True):
        calc_cols_by_table.setdefault(cc.table_name, []).append(cc)

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
        for cc in calc_cols_by_table.get(qualified_name, []):
            lines.append(
                f"  Columna calculada ya incluida automáticamente (no hace falta ninguna "
                f"función, ya está en el SELECT * como cualquier otra columna): "
                f"\"{cc.column_name}\"" + (f" — {cc.description}" if cc.description else "")
            )
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


def generate_widget_summary(code: str, chart_type: str = "", prompt: str = "") -> str:
    """
    Genera, vía Gemini, una explicación breve y no técnica (una oración) de qué muestra
    un widget ya generado, a partir de su código Python final y su chart_type. No usa
    _build_source_context: el código ya nombra tablas/columnas/agregaciones reales, es
    contexto suficiente, y esta función corre en un hilo de background fuera del ciclo
    de vida de una request HTTP (ver widget_dispatcher.dispatch_widget) — conviene
    mantenerla liviana y sin dependencias extra de infraestructura del tablero.
    """
    if not code.strip():
        raise ValueError("No hay código para resumir.")

    prompt_block = (
        f"Descripción original pedida por el usuario al crear este widget:\n{prompt}\n\n"
        if prompt else ""
    )
    full_prompt = (
        f"Tipo de widget: {chart_type or '(no especificado)'}\n\n"
        f"{prompt_block}"
        f"Código Python que ejecuta este widget (define qué datos trae y cómo los "
        f"agrupa/filtra):\n{code}"
    )

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY no está configurado en .env")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=full_prompt,
        config={"system_instruction": SUMMARY_SYSTEM_INSTRUCTION},
    )

    text = (response.text or "").strip().strip('"')
    if not text:
        raise ValueError("Gemini no devolvió un resumen.")
    return text


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


def _build_table_context(dashboard, table_name: str) -> str:
    """Arma el bloque de columnas + filas de ejemplo de UNA tabla puntual (por su nombre
    calificado), para mostrárselo a Gemini al generar una columna calculada sobre ella."""
    connector = dashboard.data_source.get_connector()
    alias = dashboard.data_source.source_type
    try:
        tables = get_cached_tables(dashboard)
    except Exception as e:
        return f"(no se pudo leer la estructura del origen de datos: {e})"
    for table in tables:
        if connector.qualified_table_name(table, alias) == table_name:
            if not table.columns:
                return "(la tabla está vacía)"
            return f"Columnas: {table.columns}\nFilas de ejemplo: {table.sample_rows}"
    return f"(no se encontró la tabla '{table_name}')"


def generate_calculated_column(prompt: str, dashboard, table_name: str, existing: dict | None = None) -> dict:
    """
    Genera (o modifica) la expresión SQL de DuckDB de una columna calculada sobre una tabla
    puntual del origen de datos del tablero, a partir de una descripción en lenguaje natural.
    `existing`, si se pasa, es un dict con al menos `column_name`/`expression` de la columna
    actual (ej. la que se está editando): se le muestra a Gemini para que la modifique sin
    perder su nombre. Retorna un dict con column_name/expression/description, listo para
    revisar y guardar en un CalculatedColumn (ver sheets_reports.utils.duckdb_query, que la
    hornea como VIEW en la tabla física cacheada).
    """
    table_context = _build_table_context(dashboard, table_name)

    existing_block = ""
    if existing and existing.get("expression"):
        existing_block = (
            f"Columna calculada YA existente (modificala si el prompt lo pide; si no, dejala "
            f"tal cual en tu respuesta):\nnombre: {existing.get('column_name', '')}\n"
            f"expresión:\n{existing['expression']}\n\n"
        )

    full_prompt = (
        f"Tabla: '{table_name}'\n{table_context}\n\n"
        f"{existing_block}"
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
            "system_instruction": CALCULATED_COLUMN_SYSTEM_INSTRUCTION,
            "response_mime_type": "application/json",
            "response_schema": CALCULATED_COLUMN_RESPONSE_SCHEMA,
        },
    )

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Gemini no devolvió una columna calculada.")

    data = json.loads(text)
    data["expression"] = _strip_markdown_fences(data.get("expression", "")).strip()
    return data
