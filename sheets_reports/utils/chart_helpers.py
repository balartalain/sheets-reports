"""
Helpers de formateo/agregación de DataFrames para widgets tipo 'bar', 'line' y
'donut' (ApexCharts). Reciben el DataFrame ya cargado y filtrado (cada función
de widget en server_functions/<slug>/functions.py sigue siendo responsable de
llamar `get_cached_df` y `apply_active_filters` antes de invocar estos
helpers) y retornan un dict con el formato { "series": [{name, data}],
"categories": [...] } — quien llama es responsable de envolverlo en
JsonResponse.
"""


def _truncar(texto: str, largo: int = 30) -> str:
    texto = str(texto)
    return texto[:largo] + "..." if len(texto) > largo else texto


def distribucion_por_respuesta(
    df,
    columna_categoria: str = "Categoría",
    columna_valor: str = "Respuesta",
    excluir=("No se utiliza", "No aplica", "N/A"),
) -> dict:
    """
    Agrupa `df` por `columna_categoria` y calcula, para cada valor único de
    `columna_valor`, el % que representa dentro de cada categoría. Formato
    compatible con ApexCharts (barras, líneas, dona):
    { series: [{name, data}], categories: [...] }.

    Los valores únicos que generan las series se determinan sobre TODO el
    DataFrame (no por categoría individual), para que todas las categorías
    compartan las mismas series. Se excluyen automáticamente valores
    nulos/vacíos, más cualquier valor listado en `excluir`
    (ej. excluir=["N/A", "No aplica"]).

    El % de cada punto se calcula sobre el total de valores NO excluidos de
    esa categoría (no sobre el total real de filas de la categoría) — misma
    convención que `tabla_conteo_por_respuesta`, sin la columna 'Total' ya
    que un gráfico no la necesita.

    Si `columna_categoria` o `columna_valor` no existen en `df`, retorna
    { "series": [], "categories": [] }.
    """
    if columna_categoria not in df.columns or columna_valor not in df.columns:
        return {"series": [], "categories": []}

    excluidos = {str(v).strip().lower() for v in excluir} | {"", "nan", "none", "nat"}

    valores_col = df[columna_valor].astype(str).str.strip()
    valores_unicos = sorted(v for v in valores_col.unique() if v.lower() not in excluidos)

    categorias = sorted(df[columna_categoria].dropna().unique())
    series_data = {valor: [] for valor in valores_unicos}

    for cat in categorias:
        sub_valores = df.loc[df[columna_categoria] == cat, columna_valor].astype(str).str.strip()
        total = int(sub_valores.isin(valores_unicos).sum())
        for valor in valores_unicos:
            conteo = int((sub_valores == valor).sum())
            series_data[valor].append(round(conteo / total * 100, 2) if total else 0)

    return {
        "series": [{"name": valor, "data": series_data[valor]} for valor in valores_unicos],
        "categories": [_truncar(cat) for cat in categorias],
    }
