import json
import logging

from django.conf import settings
from google import genai

from sheets_reports.utils.cache import get_cached_df, get_cached_sheet_titles
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
(pandas), `JsonResponse` (no la redefinas) y las utilidades listadas abajo.

__UTILS_REFERENCE__

No uses `open`, `os`, `subprocess`, `__import__`, `eval`, `exec`, ni accedas a atributos
dunder — no están disponibles y el código fallará.

El tipo de widget (chart_type) determina el shape exacto que `run` debe retornar en el
JsonResponse:
- bar / line / donut: {"series": [{"name": str, "data": [numeros]}], "categories": [etiquetas]}
- kpi: {"main_value": numero, "main_label": str, "secondary_values": [{"label": str, "value": numero}, ...]}
- table: {"columns": [{"title": str, "field": str}, ...], "rows": [{...}, ...]}
- filter: {"options": [valor, ...] | [{"value":..., "label":...}, ...], "selected": valor|null}
Si no se te indica el chart_type explícitamente, infiérelo de la descripción del usuario.

widget.filter_field -> str (SOLO para widgets con chart_type="filter": nombre exacto de la
columna que este filtro debe controlar, ya configurado por el usuario. Úsalo así:
active_filters.get(widget.filter_field, None) para obtener el valor actualmente
seleccionado. No inventes otros nombres como widget.field_name o widget.title para esto.)

La muestra de columnas/filas que se te da abajo ya corresponde a la pestaña que el usuario
mencionó en su descripción (si mencionó alguna); usa exactamente ese nombre de pestaña en
get_cached_df(widget.dashboard, sheet_name='<nombre exacto>'). Si el usuario menciona una
pestaña que no coincide con la de la muestra (typo, nombre parcial, etc.), usa igual el nombre
que dio el usuario en get_cached_df(...) e infiere las columnas razonablemente a partir de su
descripción, ya que no tienes la estructura real de esa pestaña.

Tu respuesta debe ser SIEMPRE la función run(request, widget) completa y final, no un fragmento.
Si se te muestra el código ya existente de este widget, conservá su lógica salvo lo que el
prompt pida cambiar explícitamente, y modificá únicamente eso.
"""


CUSTOM_UTIL_SYSTEM_INSTRUCTION = """\
Eres un generador de funciones utilitarias reutilizables para un dashboard de reportes. Cada
función que generes podrá ser llamada, por su nombre, desde el código de cualquier widget de
este tablero (y desde otras funciones utilitarias personalizadas del mismo tablero).

Reglas:
- La función debe ser autocontenida: no hagas ningún `import` (ya tenés disponible `pd`, sin
  necesidad de importarlo, más las utilidades ya existentes del tablero que se listan abajo).
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
    existing_code_block = (
        f"Código YA existente de este widget (modificalo si el prompt lo pide; si no, dejalo "
        f"tal cual en tu respuesta):\n{existing_code}\n\n"
        if existing_code else ""
    )
    full_prompt = (
        f"{chart_type_line}"
        f"{existing_code_block}"
        f"Estructura de muestra del spreadsheet de este tablero:\n"
        f"{sample_context}\n\n"
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
    sample_context = _build_sample_context(dashboard, prompt)
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
        f"Estructura de muestra del spreadsheet de este tablero:\n"
        f"{sample_context}\n\n"
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
