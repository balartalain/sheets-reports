"""
Helpers de formateo/agregación de DataFrames para widgets tipo 'bar', 'line' y
'donut' (ApexCharts). Reciben el DataFrame ya cargado y filtrado (cada widget.code
sigue siendo responsable de llamar `get_cached_df` y `apply_active_filters` antes
de invocar estos helpers) y retornan un dict con el formato { "series": [{name, data}],
"categories": [...] } — quien llama es responsable de envolverlo en
JsonResponse.
"""
from .registry import util


def _truncar(texto: str, largo: int = 30) -> str:
    texto = str(texto)
    return texto[:largo] + "..." if len(texto) > largo else texto


@util(
    category="Gráficos",
    description=(
        "Agrupa `df` por `columna_categoria` y calcula, para cada valor único de "
        "`columna_valor`, el % que representa dentro de cada categoría. Formato compatible "
        "con ApexCharts (barras, líneas, dona): { series: [{name, data}], categories: [...] }. "
        "Excluye automáticamente valores nulos/vacíos, más los listados en `excluir`. Si "
        "`columna_categoria` o `columna_valor` no existen en `df`, retorna series/categories vacías."
    ),
    example="data = distribucion_por_respuesta(df, 'Categoría', 'Respuesta')",
)
def distribucion_por_respuesta(
    df,
    columna_categoria: str = "Categoría",
    columna_valor: str = "Respuesta",
    excluir=("No se utiliza", "No aplica", "N/A"),
) -> dict:
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
