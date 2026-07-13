"""
Vistas de datos para el tablero "Ventas Región Norte".
Cada función recibe (df, request, widget) y retorna un JsonResponse.
"""
from django.http import JsonResponse


def total_ventas(df, request, widget):
    """
    Ejemplo: retorna el total de ventas por mes.
    Mock: si el DataFrame está vacío o no tiene las columnas esperadas,
    devuelve datos de muestra.
    Retorna formato compatible con ApexCharts: { series: [{ name, data }], categories: [...] }.
    """
    if df.empty:
        categories = ["Ene", "Feb", "Mar", "Abr", "May", "Jun"]
        data_values = [14200, 19800, 8500, 11000, 16400, 15000]
    else:
        grouped = df.groupby("mes")["monto"].sum()
        categories = grouped.index.tolist()
        data_values = grouped.tolist()

    return JsonResponse({
        "series": [{"name": "Total ventas", "data": data_values}],
        "categories": categories,
    })


def ventas_por_vendedor(df, request, widget):
    """
    Ejemplo: retorna ventas agregadas por vendedor.
    Retorna formato compatible con ApexCharts: { series: [{ name, data }], categories: [...] }.
    """
    if df.empty:
        categories = ["Carlos", "María", "José", "Ana"]
        data_values = [32000, 28500, 22400, 19100]
    else:
        grouped = df.groupby("vendedor")["monto"].sum()
        categories = grouped.index.tolist()
        data_values = grouped.tolist()

    return JsonResponse({
        "series": [{"name": "Ventas", "data": data_values}],
        "categories": categories,
    })


def kpi_resumen(df, request, widget):
    """
    Ejemplo: retorna indicadores clave del tablero.
    """
    if df.empty:
        data = {
            "total_ventas": 102000,
            "promedio_por_mes": 17000,
            "total_vendedores": 4,
            "mejor_mes": "febrero",
        }
    else:
        data = {
            "total_ventas": int(df["monto"].sum()),
            "promedio_por_mes": int(df["monto"].mean()),
            "total_vendedores": df["vendedor"].nunique(),
            "mejor_mes": df.groupby("mes")["monto"].sum().idxmax(),
        }

    return JsonResponse(data)
