import logging

from django.conf import settings
from google import genai

from sheets_reports.utils.cache import get_cached_df, get_cached_sheet_titles

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = """\
Eres un generador de código Python para widgets de un dashboard interno de reportes.

Debes responder ÚNICAMENTE con código Python (sin explicación, sin markdown, sin ```),
que defina EXACTAMENTE una función con esta firma:

    def run(request, widget):
        ...
        return JsonResponse(...)

No hagas ningún `import`: ya tienes disponibles, inyectados en el contexto de ejecución:
- pd (pandas)
- get_cached_df(widget.dashboard, sheet_name=None) -> DataFrame (sheet_name=None usa la
  primera pestaña del spreadsheet; pasa el nombre exacto de otra pestaña si el usuario lo pide)
- apply_active_filters(df, request, widget) -> DataFrame (aplica los filtros activos del
  tablero, comparando cada filtro contra la columna del mismo nombre)
- get_active_filters(request, widget) -> dict
- widget.filter_field -> str (SOLO para widgets con chart_type="filter": nombre exacto de la
  columna que este filtro debe controlar, ya configurado por el usuario. Úsalo así:
  active_filters.get(widget.filter_field, None) para obtener el valor actualmente
  seleccionado. No inventes otros nombres como widget.field_name o widget.title para esto.)
- distribucion_por_respuesta(df, columna_categoria, columna_valor, excluir=()) -> dict
  (agrupa y arma el shape de bar/line/donut)
- tabla_conteo_por_respuesta(df, columna_categoria, columna_valor, excluir=()) -> dict
  (agrupa y arma el shape de table)
- JsonResponse

No uses `open`, `os`, `subprocess`, `__import__`, `eval`, `exec`, ni accedas a atributos
dunder — no están disponibles y el código fallará.

El tipo de widget (chart_type) determina el shape exacto que `run` debe retornar en el
JsonResponse:
- bar / line / donut: {"series": [{"name": str, "data": [numeros]}], "categories": [etiquetas]}
- kpi: {"main_value": numero, "main_label": str, "secondary_values": [{"label": str, "value": numero}, ...]}
- table: {"columns": [{"title": str, "field": str}, ...], "rows": [{...}, ...]}
- filter: {"options": [valor, ...] | [{"value":..., "label":...}, ...], "selected": valor|null}
Si no se te indica el chart_type explícitamente, infiérelo de la descripción del usuario.

La muestra de columnas/filas que se te da abajo ya corresponde a la pestaña que el usuario
mencionó en su descripción (si mencionó alguna); usa exactamente ese nombre de pestaña en
get_cached_df(widget.dashboard, sheet_name='<nombre exacto>'). Si el usuario menciona una
pestaña que no coincide con la de la muestra (typo, nombre parcial, etc.), usa igual el nombre
que dio el usuario en get_cached_df(...) e infiere las columnas razonablemente a partir de su
descripción, ya que no tienes la estructura real de esa pestaña.

Si el tablero tiene código compartido (funciones reutilizables entre widgets, ej. columnas
calculadas), se te muestra tal cual más abajo — YA está disponible en el contexto de ejecución,
no lo redefinas ni lo copies: solo llamá las funciones que necesites (ej. add_nivel_column(df)).

Tu respuesta debe ser SIEMPRE la función run(request, widget) completa y final, no un fragmento.
Si se te muestra el código ya existente de este widget, conservá su lógica salvo lo que el
prompt pida cambiar explícitamente, y modificá únicamente eso.
"""


SHARED_CODE_SYSTEM_INSTRUCTION = """\
Eres un generador de código Python de utilidades compartidas para un dashboard de reportes.

Debes responder ÚNICAMENTE con código Python (sin explicación, sin markdown, sin ```), que
defina una o más funciones reutilizables (ej. una columna calculada) que el código de otros
widgets de este mismo tablero podrá llamar explícitamente.

No definas `def run(request, widget):` — esto NO es un widget, son utilidades puras. Ejemplo de
forma esperada:

    def add_nivel_column(df):
        ...
        df["Nivel"] = ...
        return df

No hagas ningún `import`: solo tenés disponible `pd` (pandas) en el contexto de ejecución.
No uses `open`, `os`, `subprocess`, `__import__`, `eval`, `exec`, ni accedas a atributos dunder.
Las funciones que definas deben ser defensivas (ej. verificar que una columna exista antes de
usarla) ya que se van a llamar desde distintos widgets con distintos DataFrames.

Tu respuesta debe ser SIEMPRE el código compartido completo y final, no un fragmento aislado.
Si se te muestra código ya existente, conservá sin cambios las funciones que el prompt no pide
tocar, y modificá o agregá únicamente lo que el prompt pida.
"""


def _detect_sheet_name(prompt: str, dashboard) -> str | None:
    """Busca, case-insensitive, si el prompt del usuario menciona el nombre de alguna pestaña
    real del spreadsheet del dashboard. Retorna el nombre exacto de la pestaña o None."""
    try:
        titles = get_cached_sheet_titles(dashboard)
    except Exception:
        return None

    prompt_lower = prompt.lower()
    for title in titles:
        if title.lower() in prompt_lower:
            return title
    return None


def _build_sample_context(dashboard, prompt: str) -> str:
    sheet_name = _detect_sheet_name(prompt, dashboard)
    label = f"'{sheet_name}'" if sheet_name else "por defecto"

    try:
        df = get_cached_df(dashboard, sheet_name)
    except Exception as e:
        return f"(no se pudo leer la pestaña {label} del spreadsheet: {e})"
    if df.empty:
        return f"(la pestaña {label} del spreadsheet está vacía)"

    columns = list(df.columns)
    sample_rows = df.head(3).to_dict(orient="records")
    return f"Pestaña usada para la muestra: {label}\nColumnas: {columns}\nFilas de ejemplo: {sample_rows}"


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
    sample_context = _build_sample_context(dashboard, prompt)

    chart_type_line = f"Tipo de widget (chart_type): {chart_type}\n\n" if chart_type else ""
    shared_code_block = (
        f"Código compartido del tablero (ya disponible, no lo redefinas):\n{dashboard.shared_code}\n\n"
        if dashboard.shared_code else ""
    )
    existing_code_block = (
        f"Código YA existente de este widget (modificalo si el prompt lo pide; si no, dejalo "
        f"tal cual en tu respuesta):\n{existing_code}\n\n"
        if existing_code else ""
    )
    full_prompt = (
        f"{chart_type_line}"
        f"{shared_code_block}"
        f"{existing_code_block}"
        f"Estructura de muestra del spreadsheet de este tablero:\n"
        f"{sample_context}\n\n"
        f"Descripción del usuario:\n{prompt}"
    )

    return _call_gemini(full_prompt, SYSTEM_INSTRUCTION)


def generate_shared_code(prompt: str, dashboard, existing_code: str = "") -> str:
    """
    Genera (o modifica) código Python de utilidades compartidas por todos los widgets del
    tablero (ej. columnas calculadas), usando Gemini. `existing_code`, si se pasa, es el código
    compartido actual (ej. el draft del textarea, con ediciones aún no guardadas): se le muestra
    a Gemini para que pueda modificar una función puntual sin perder el resto. Retorna el código
    completo y final, listo para guardar en Dashboard.shared_code.
    """
    sample_context = _build_sample_context(dashboard, prompt)
    existing_code_block = (
        f"Código compartido YA existente en este tablero (modificalo si el prompt lo pide; si "
        f"no, dejalo tal cual en tu respuesta):\n{existing_code}\n\n"
        if existing_code else ""
    )
    full_prompt = (
        f"{existing_code_block}"
        f"Estructura de muestra del spreadsheet de este tablero:\n"
        f"{sample_context}\n\n"
        f"Descripción del usuario:\n{prompt}"
    )

    return _call_gemini(full_prompt, SHARED_CODE_SYSTEM_INSTRUCTION)
