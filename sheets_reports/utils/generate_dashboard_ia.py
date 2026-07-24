import json

from django.conf import settings
from google import genai

from sheets_reports.utils.generate_widget_ia import (
    DEFAULT_MODEL,
    _build_sheets_context,
    generate_widget_code,
)

BOARD_PLANNER_SYSTEM_INSTRUCTION = """\
Eres un arquitecto de dashboards. Tu tarea es diseñar la estructura completa de un tablero de
reportes a partir de una descripción del usuario y la estructura de las hojas de cálculo disponibles.

Los únicos tipos de widget disponibles son:
- bar: Gráfico de Barras — para comparar valores entre categorías (ej. ventas por región).
- line: Gráfico de Líneas — para mostrar tendencias en el tiempo (ej. ventas por mes).
- donut: Gráfico de Dona — para mostrar proporciones de un total (ej. % por canal).
- kpi: Tarjeta KPI — para resaltar un número clave con etiqueta y opcionalmente valores secundarios.
- filter: Filtro — para que el usuario pueda segmentar los datos del tablero (ej. filtrar por año).
- table: Tabla — para mostrar el detalle crudo de los datos en formato tabular.

Sistema de rejilla (grid de 12 columnas):
Cada widget ocupa un ancho definido por clases CSS col-span. Las opciones disponibles son:
- md:col-span-2 (17%) — widgets estrechos, rara vez usados.
- md:col-span-3 (25%) — filtros o widgets compactos.
- md:col-span-4 (33%) — ideal para KPI, donut, filter.
- md:col-span-6 (50%) — ideal para bar, line, table.
- md:col-span-8 (66%) — widgets que necesitan más espacio horizontal.
- md:col-span-12 (100%) — tablas grandes o dashboards de una sola columna.

Reglas de layout:
- En una fila, la suma de col-span no debe superar 12.
- Si hay espacio sobrante, los widgets se distribuyen fluídamente (startCol vacío).
- Orden sugerido: filtros primero, luego KPIs/resumen, luego gráficos, luego tablas.
- Alto recomendado: 300px para gráficos, 300px para KPIs. Para widgets de tipo "filter", no incluyas la propiedad height (no debe tener altura fija).
- No generes más de 8 widgets por tablero. Sé selectivo: elige los que mejor respondan
  a la intención del usuario.
- No generes filtros redundantes ni widgets que se superpongan en propósito.

Debes responder ÚNICAMENTE con un objeto JSON (sin markdown, sin ```) que contenga:
- "title": título del tablero en español, descriptivo.
- "widgets": lista de objetos, cada uno con:
  - "title": título corto del widget.
  - "chart_type": uno de los 6 tipos listados arriba.
  - "order": índice numérico empezando desde 0 (define el orden en el lienzo).
  - "prompt": descripción detallada para que otro sistema genere el código Python
    de este widget. Incluí: qué hoja/pestaña usar (por su nombre exacto), qué columnas,
    cómo agrupar, qué calcular. Sé específico para que un desarrollador (o una IA) pueda
    escribir la función run() sin ambigüedad.
  - "properties": objeto con:
    - "width": clase CSS de ancho (ej. "md:col-span-6").
    - "height": alto en píxels (entero, ej. 300).
    - "startCol": cadena vacía "" (layout fluido).

A continuación se te muestra la estructura de las pestañas del spreadsheet de este tablero.
Seleccioná la(s) pestaña(s) más relevantes para cada widget.
"""

BOARD_PLANNER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "widgets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "chart_type": {
                        "type": "string",
                        "enum": ["bar", "line", "donut", "kpi", "filter", "table"],
                    },
                    "order": {"type": "integer"},
                    "properties": {
                        "type": "object",
                        "properties": {
                            "width": {"type": "string"},
                            "height": {"type": "integer"},
                            "startCol": {"type": "string"},
                        },
                        "required": ["width", "height", "startCol"],
                    },
                    "prompt": {"type": "string"},
                },
                "required": ["title", "chart_type", "order", "properties", "prompt"],
            },
        },
    },
    "required": ["title", "widgets"],
}


def generate_board_plan(user_prompt: str, dashboard) -> dict:
    """
    Genera un plan completo de tablero (título + lista de widgets con tipo, layout y prompt
    por widget) a partir de una descripción del usuario en lenguaje natural. Usa Gemini con
    BOARD_PLANNER_SYSTEM_INSTRUCTION y response_schema para obtener JSON estructurado.
    NO genera código Python todavía — solo el plan arquitectónico.
    Retorna un dict con "title" y "widgets".
    """
    sheets_context = _build_sheets_context(dashboard, user_prompt)
    full_prompt = (
        f"Estructura de las pestañas del spreadsheet:\n"
        f"{sheets_context}\n\n"
        f"Descripción del usuario:\n{user_prompt}"
    )

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY no está configurado en .env")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=full_prompt,
        config={
            "system_instruction": BOARD_PLANNER_SYSTEM_INSTRUCTION,
            "response_mime_type": "application/json",
            "response_schema": BOARD_PLANNER_RESPONSE_SCHEMA,
        },
    )

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Gemini no devolvió un plan de tablero.")

    plan = json.loads(text)
    if not plan.get("title") or not plan.get("widgets"):
        raise ValueError("El plan generado está incompleto (faltan title o widgets).")
    return plan


def generate_board_from_prompt(user_prompt: str, source_url: str, user):
    """
    Orquestador completo: crea un Dashboard, pide a Gemini el plan, genera el código de
    cada widget y persiste todo. Es un generador que va emitiendo dicts de progreso por
    cada etapa (pensado para alimentar un StreamingHttpResponse en
    views_dashboard.generate_dashboard_from_prompt); el último dict tiene
    event="done" y trae el Dashboard ya armado bajo la clave "dashboard".
    Si algo falla, emite event="error" y no deja registros huérfanos (borra el Dashboard).
    """
    from django.db import transaction
    from sheets_reports.models import Dashboard, WidgetInstance

    dashboard = Dashboard.objects.create(
        title="Generando…",
        source_url=source_url,
        user=user,
    )

    try:
        yield {"event": "planning"}
        plan = generate_board_plan(user_prompt, dashboard)

        dashboard.title = plan["title"]
        dashboard.save()

        total = len(plan["widgets"])
        yield {"event": "plan", "title": plan["title"], "total": total}

        with transaction.atomic():
            for index, w_data in enumerate(plan["widgets"], start=1):
                if w_data["chart_type"] == "filter":
                    w_data["properties"].pop("height", None)
                yield {"event": "widget_start", "index": index, "total": total, "title": w_data["title"]}
                code = generate_widget_code(
                    prompt=w_data["prompt"],
                    dashboard=dashboard,
                    chart_type=w_data["chart_type"],
                )
                widget = WidgetInstance.objects.create(
                    dashboard=dashboard,
                    title=w_data["title"],
                    chart_type=w_data["chart_type"],
                    code=code,
                    prompt=w_data["prompt"],
                    properties=w_data["properties"],
                    order=w_data["order"],
                )
                yield {"event": "widget_done", "index": index, "total": total, "widget_id": widget.id}
    except Exception as e:
        dashboard.delete()
        yield {"event": "error", "message": str(e)}
        return

    yield {"event": "done", "dashboard": dashboard}
