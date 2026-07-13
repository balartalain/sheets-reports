"""
Vistas de datos para el tablero "Ventas Región Norte".
Cada función recibe (df, request, widget) y retorna un JsonResponse.
"""
from django.http import JsonResponse

def ventas_por_producto(df, request, widget):
    """
    Ejemplo: retorna ventas agregadas por producto.
    Retorna formato compatible con ApexCharts: { series: [{ name, data }], categories: [...] }.
    """
    if df.empty:
        categories = ["Producto A", "Producto B", "Producto C"]
        data_values = [45000, 32000, 28000]
    else:
        grouped = df.groupby("Producto")["Ventas"].sum()
        categories = grouped.index.tolist()
        data_values = grouped.tolist()

    return JsonResponse({
        "series": [{"name": "Ventas", "data": data_values}],
        "categories": categories,
    })

_MESES_ORDEN = {
    "Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12,
}


def total_ventas(df, request, widget):
    """
    Ejemplo: retorna el total de ventas por mes.
    Mock: si el DataFrame está vacío o no tiene las columnas esperadas,
    devuelve datos de muestra.
    Retorna formato compatible con ApexCharts: { series: [{ name, data }], categories: [...] }.
    """
    if df.empty:
        categories = ["Ene", "Feb", "Mar", "Abr", "May", "Jun"]
        data_values = [14300, 19800, 8500, 11000, 16400, 15000]
    else:
        grouped = df.groupby("Mes")["Ventas"].sum().reset_index()
        grouped["_orden"] = grouped["Mes"].map(_MESES_ORDEN)
        grouped = grouped.sort_values("_orden")
        categories = grouped["Mes"].tolist()
        data_values = grouped["Ventas"].tolist()

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
        categories = ["Cajero 1", "Cajero 2", "Cajero 3"]
        data_values = [32000, 28500, 22400, 19100]
    else:
        grouped = df.groupby("Vendedor")["Ventas"].sum()
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
            "total_ventas": int(df["Ventas"].sum()),
            "promedio_por_mes": int(df["Ventas"].mean()),
            "total_vendedores": df["Vendedor"].nunique(),
            "mejor_mes": df.groupby("Mes")["Ventas"].sum().idxmax(),
        }

    return JsonResponse(data)
