"""
Vistas de datos para el tablero "Encuesta satisfacción de  participantes 2026" (functions_slug: encuesta-satisfaccion-de-participantes-2026).
Cada función recibe (request, widget) y retorna un JsonResponse. Cada una es
responsable de cargar su(s) propio(s) DataFrame con
`get_cached_df(widget.dashboard, sheet_name)` (sheet_name=None usa la primera
hoja), lo que permite cruzar datos de varias pestañas del mismo spreadsheet
cuando haga falta.
"""
import pandas as pd
from django.http import JsonResponse

from sheets_reports.utils.cache import get_cached_df
from sheets_reports.utils.chart_helpers import distribucion_por_respuesta
from sheets_reports.utils.table_helpers import tabla_conteo_por_respuesta
from sheets_reports.utils.widget_dispatcher import apply_active_filters, get_active_filters


def _nivel_periodo(periodo: str):
    """Clasifica un 'Período que está cursando' en Nuevo Ingreso / Regular / Término."""
    periodo = str(periodo)
    if periodo == "1":
        return "Nuevo Ingreso"
    if periodo in ("12", "Curso final de grado", "Tesis"):
        return "Término"
    if periodo in {str(i) for i in range(2, 12)}:
        return "Regular"
    return None


def _add_nivel_column(df):
    """
    Agrega la columna derivada 'Nivel' (Nuevo Ingreso / Regular / Término) a
    partir de 'Período que está cursando'. Se llama antes de
    `apply_active_filters` en toda función de este tablero, para que el
    filtro de Nivel (ver `filtro_nivel`) les aplique a todas — como 'Nivel'
    no es una columna real de la hoja, `apply_active_filters` no puede
    filtrar por ella si esta columna no existe primero en el DataFrame.
    """
    if "Período que está cursando" not in df.columns:
        return df
    df["Nivel"] = df["Período que está cursando"].astype(str).map(_nivel_periodo)
    return df


def resumen_por_recinto(request, widget):
    """
    Retorna la cantidad y el porcentaje de respuestas por Recinto.
    Retorna formato compatible con Tabulator: { columns: [{title, field}], rows: [{...}] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    columns = [
        {"title": "Recinto", "field": "Recinto"},
        {"title": "Cantidad", "field": "Cantidad"},
        {"title": "Porcentaje", "field": "Porcentaje"},
    ]

    if "Recinto:" not in df.columns:
        rows = []
    else:
        conteo = df["Recinto:"].value_counts()
        total = int(conteo.sum())
        rows = [
            {
                "Recinto": recinto,
                "Cantidad": int(cantidad),
                "Porcentaje": f"{round(cantidad / total * 100, 2)}%",
            }
            for recinto, cantidad in conteo.items()
        ]
        if rows:
            rows.append({"Recinto": "Total", "Cantidad": total, "Porcentaje": "100%"})

    return JsonResponse({"columns": columns, "rows": rows})


def distribucion_por_recinto(request, widget):
    """
    Retorna la cantidad de respuestas por Recinto.
    Retorna formato compatible con ApexCharts (gráfico de dona): { series: [{ name, data }], categories: [...] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    if "Recinto:" not in df.columns:
        categories, data_values = [], []
    else:
        conteo = df["Recinto:"].value_counts()
        categories = conteo.index.tolist()
        data_values = conteo.tolist()

    return JsonResponse({
        "series": [{"name": "Respuestas", "data": data_values}],
        "categories": categories,
    })


_PERIODO_ORDEN = {str(i): i for i in range(1, 13)}
_PERIODO_ORDEN["Curso final de grado"] = 13
_PERIODO_ORDEN["Tesis"] = 14


def distribucion_por_periodo(request, widget):
    """
    Retorna el porcentaje de respuestas por "Período que está cursando",
    ordenado del 1 al 12 y luego Curso final de grado, Tesis.
    Retorna formato compatible con ApexCharts: { series: [{ name, data }], categories: [...] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    if "Período que está cursando" not in df.columns:
        categories, data_values = [], []
    else:
        conteo = df["Período que está cursando"].astype(str).value_counts()
        total = int(conteo.sum())
        categories = sorted(conteo.index, key=lambda p: _PERIODO_ORDEN.get(p, 999))
        data_values = [round(conteo[p] / total * 100, 2) for p in categories]

    return JsonResponse({
        "series": [{"name": "Porcentaje", "data": data_values}],
        "categories": categories,
    })


def resumen_por_periodo(request, widget):
    """
    Retorna la cantidad y el porcentaje de respuestas por "Período que está
    cursando", ordenado del 1 al 12 y luego Curso final de grado, Tesis.
    Retorna formato compatible con Tabulator: { columns: [{title, field}], rows: [{...}] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    columns = [
        {"title": "Período", "field": "Periodo"},
        {"title": "Cantidad", "field": "Cantidad"},
        {"title": "Porcentaje", "field": "Porcentaje"},
    ]

    if "Período que está cursando" not in df.columns:
        rows = []
    else:
        conteo = df["Período que está cursando"].astype(str).value_counts()
        total = int(conteo.sum())
        periodos = sorted(conteo.index, key=lambda p: _PERIODO_ORDEN.get(p, 999))
        rows = [
            {
                "Periodo": periodo,
                "Cantidad": int(conteo[periodo]),
                "Porcentaje": f"{round(conteo[periodo] / total * 100, 2)}%",
            }
            for periodo in periodos
        ]

    return JsonResponse({"columns": columns, "rows": rows})


def resumen_por_escuela(request, widget):
    """
    Retorna la cantidad y el porcentaje de respuestas por "Escuela a la que pertenece".
    Retorna formato compatible con Tabulator: { columns: [{title, field}], rows: [{...}] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    columns = [
        {"title": "Escuela", "field": "Escuela"},
        {"title": "Cantidad", "field": "Cantidad"},
        {"title": "Porcentaje", "field": "Porcentaje"},
    ]

    if "Escuela a la que pertenece" not in df.columns:
        rows = []
    else:
        conteo = df["Escuela a la que pertenece"].value_counts()
        total = int(conteo.sum())
        rows = [
            {
                "Escuela": escuela,
                "Cantidad": int(cantidad),
                "Porcentaje": f"{round(cantidad / total * 100, 2)}%",
            }
            for escuela, cantidad in conteo.items()
        ]
        if rows:
            rows.append({"Escuela": "Total", "Cantidad": total, "Porcentaje": "100%"})

    return JsonResponse({"columns": columns, "rows": rows})


def distribucion_por_escuela(request, widget):
    """
    Retorna el porcentaje de respuestas por "Escuela a la que pertenece".
    Retorna formato compatible con ApexCharts (gráfico de dona): { series: [{ name, data }], categories: [...] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    if "Escuela a la que pertenece" not in df.columns:
        categories, data_values = [], []
    else:
        conteo = df["Escuela a la que pertenece"].value_counts()
        total = int(conteo.sum())
        categories = conteo.index.tolist()
        data_values = [round(v / total * 100, 2) for v in conteo.tolist()]

    return JsonResponse({
        "series": [{"name": "Porcentaje", "data": data_values}],
        "categories": categories,
    })


def distribucion_por_nivel(request, widget):
    """
    Retorna, por "Escuela a la que pertenece", la cantidad y el porcentaje de
    participantes en Nuevo Ingreso (período 1), Regular (período 2 al 11) y
    Término (período 12, Curso final de grado o Tesis).
    Retorna formato compatible con Tabulator: { columns: [{title, field}], rows: [{...}] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    columns = [
        {"title": "Escuela", "field": "Escuela"},
        {"title": "Nuevo Ingreso", "field": "NuevoIngreso"},
        {"title": "%", "field": "PctNuevoIngreso"},
        {"title": "Regular", "field": "Regular"},
        {"title": "%", "field": "PctRegular"},
        {"title": "Término", "field": "Termino"},
        {"title": "%", "field": "PctTermino"},
        {"title": "Total General", "field": "TotalGeneral"},
    ]

    def pct(n, total):
        return f"{round(n / total * 100, 2)}%" if total else "0%"

    if "Escuela a la que pertenece" not in df.columns or "Nivel" not in df.columns:
        rows = []
    else:
        conteo = {}
        for escuela, nivel in zip(df["Escuela a la que pertenece"], df["Nivel"]):
            if nivel is None:
                continue
            conteo.setdefault(escuela, {"Nuevo Ingreso": 0, "Regular": 0, "Término": 0})
            conteo[escuela][nivel] += 1

        rows = []
        for escuela, niveles in conteo.items():
            nuevo = niveles["Nuevo Ingreso"]
            regular = niveles["Regular"]
            termino = niveles["Término"]
            total = nuevo + regular + termino
            rows.append({
                "Escuela": escuela,
                "NuevoIngreso": nuevo,
                "PctNuevoIngreso": pct(nuevo, total),
                "Regular": regular,
                "PctRegular": pct(regular, total),
                "Termino": termino,
                "PctTermino": pct(termino, total),
                "TotalGeneral": total,
            })

        if rows:
            nuevo_total = sum(r["NuevoIngreso"] for r in rows)
            regular_total = sum(r["Regular"] for r in rows)
            termino_total = sum(r["Termino"] for r in rows)
            gran_total = sum(r["TotalGeneral"] for r in rows)
            rows.append({
                "Escuela": "Total",
                "NuevoIngreso": nuevo_total,
                "PctNuevoIngreso": pct(nuevo_total, gran_total),
                "Regular": regular_total,
                "PctRegular": pct(regular_total, gran_total),
                "Termino": termino_total,
                "PctTermino": pct(termino_total, gran_total),
                "TotalGeneral": gran_total,
            })

    return JsonResponse({"columns": columns, "rows": rows})


def resumen_nivel_satisfaccion(request, widget):
    """
    Retorna, por Categoria, el conteo y % de cada valor de 'Respuesta'
    ('Completamente satisfecho', 'Satisfecho', etc.), mas el total de respuestas.
    Retorna formato compatible con Tabulator: { columns: [{title, field}], rows: [{...}] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas Indique su nivel de satisfacción con los siguientes aspectos")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    return JsonResponse(tabla_conteo_por_respuesta(df))


def distribucion_nivel_satisfaccion(request, widget):
    """
    Retorna, por Categoria, el % de cada valor de 'Respuesta'
    ('Completamente satisfecho', 'Satisfecho', etc.).
    Retorna formato compatible con ApexCharts (grafico de barras apiladas):
    { series: [{ name, data }], categories: [...] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas Indique su nivel de satisfacción con los siguientes aspectos")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    return JsonResponse(distribucion_por_respuesta(df))

def resumen_valoracion(request, widget):
    """
    Retorna, por Categoria, el conteo y % de cada valor de 'Respuesta'
    ('Alto', 'Bajo', etc.), mas el total de respuestas.
    Retorna formato compatible con Tabulator: { columns: [{title, field}], rows: [{...}] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas Valoración")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    return JsonResponse(tabla_conteo_por_respuesta(df))

def distribucion_valoracion(request, widget):
    df = get_cached_df(widget.dashboard, "Respuestas Valoración")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    return JsonResponse(distribucion_por_respuesta(df))

def respuestas_por_dia(request, widget):
    """
    Retorna la cantidad de respuestas recibidas por día, a partir de la
    columna 'Marca temporal' (formato DD/MM/yyyy HH:MM:SS), ordenadas
    cronológicamente.
    Retorna formato compatible con ApexCharts (gráfico de línea):
    { series: [{ name, data }], categories: [...] }.
    """
    df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    df = _add_nivel_column(df)
    df = apply_active_filters(df, request, widget)

    if "Marca temporal" not in df.columns:
        categories, data_values = [], []
    else:
        fechas = pd.to_datetime(df["Marca temporal"], format="%d/%m/%Y %H:%M:%S", errors="coerce").dt.date
        conteo = fechas.value_counts().sort_index()
        categories = [fecha.strftime("%d/%m/%Y") for fecha in conteo.index]
        data_values = conteo.tolist()

    return JsonResponse({
        "series": [{"name": "Respuestas", "data": data_values}],
        "categories": categories,
    })

def filtro_recintos(request, widget):
    """
    Retorna lista de recintos únicos para un filtro, junto con el valor ya
    guardado en sesión (si existe), para que el widget lo preseleccione al
    cargar la página en vez de mostrarse vacío.

    El widget de tipo filtro debe titularse exactamente 'Recinto:' (el nombre
    de la columna), ya que `apply_active_filters` usa el título del widget
    para saber contra qué columna filtrar en las demás funciones del tablero.
    """
    df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    if "Recinto:" not in df.columns:
        data = []
    else:
        data = sorted(df["Recinto:"].dropna().unique().tolist())

    selected = get_active_filters(request, widget).get("Recinto:")

    return JsonResponse({"options": data, "selected": selected})

def filtro_escuelas(request, widget):
    """
    Retorna lista de recintos únicos para un filtro, junto con el valor ya
    guardado en sesión (si existe), para que el widget lo preseleccione al
    cargar la página en vez de mostrarse vacío.

    El widget de tipo filtro debe titularse exactamente 'Recinto:' (el nombre
    de la columna), ya que `apply_active_filters` usa el título del widget
    para saber contra qué columna filtrar en las demás funciones del tablero.
    """
    df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    if "Escuela a la que pertenece" not in df.columns:
        data = []
    else:
        data = sorted(df["Escuela a la que pertenece"].dropna().unique().tolist())

    selected = get_active_filters(request, widget).get("Escuela a la que pertenece")

    return JsonResponse({"options": data, "selected": selected})


def kpi_destinatarios(request, widget):
    """
    Retorna el total de destinatarios, cuántos ya fueron notificados y
    cuántos han respondido la encuesta.
    Retorna formato compatible con el widget KPI:
    { main_value, main_label, secondary_values: [{label, value}] }.
    """
    df = get_cached_df(widget.dashboard, "Destinatarios")

    total = int(len(df))
    if "Estado" in df.columns:
        notificados = int((df["Estado"].astype(str).str.strip().str.upper() == "ENVIADO").sum())
    else:
        notificados = 0

    respuestas_df = get_cached_df(widget.dashboard, "Respuestas de formulario 1")
    respuestas = int(len(respuestas_df))

    return JsonResponse({
        "main_value": total,
        "main_label": "Participantes",
        "secondary_values": [
            {"label": "Han sido notificados", "value": notificados},
            {"label": "Han  respondido", "value": respuestas},
        ],
    })


def filtro_nivel(request, widget):
    """
    Retorna las opciones fijas del filtro de Nivel (Nuevo Ingreso, Regular,
    Término — ver `_nivel_periodo`), junto con el valor ya guardado en sesión
    (si existe), para que el widget lo preseleccione al cargar la página.

    Se usa una lista fija en vez de valores únicos del DataFrame para que las
    3 opciones siempre estén disponibles, aunque falten datos de alguna.

    El widget de tipo filtro debe titularse exactamente 'Nivel', ya que
    `apply_active_filters` usa el título del widget para saber contra qué
    columna filtrar en las demás funciones — y estas agregan la columna
    derivada 'Nivel' con `_add_nivel_column` antes de filtrar.
    """
    data = ["Nuevo Ingreso", "Regular", "Término"]
    selected = get_active_filters(request, widget).get("Nivel")

    return JsonResponse({"options": data, "selected": selected})