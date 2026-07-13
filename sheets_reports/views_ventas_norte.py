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
    """
    if df.empty:
        data = {
            "ene": 14200,
            "feb": 19800,
            "mar": 8500,
            "abr": 11000,
            "may": 16400,
            "jun": 15000,
        }
    else:
        grouped = df.groupby("mes")["monto"].sum()
        data = grouped.to_dict()

    return JsonResponse(data)


def ventas_por_vendedor(df, request, widget):
    """
    Ejemplo: retorna ventas agregadas por vendedor.
    """
    if df.empty:
        data = {
            "Carlos": 32000,
            "María": 28500,
            "José": 22400,
            "Ana": 19100,
        }
    else:
        grouped = df.groupby("vendedor")["monto"].sum()
        data = grouped.to_dict()

    return JsonResponse(data)


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
