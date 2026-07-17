"""
Helpers de formateo/agregación de DataFrames para widgets tipo 'table' (Tabulator).
Reciben el DataFrame ya cargado y filtrado (cada función de widget en
server_functions/<slug>/functions.py sigue siendo responsable de llamar
`get_cached_df` y `apply_active_filters` antes de invocar estos helpers) y
retornan un dict con el formato { "columns": [...], "rows": [...] } — quien
llama es responsable de envolverlo en JsonResponse.
"""
from django.utils.text import slugify


def _campo_desde_valor(valor: str, usados: set) -> str:
    """
    Convierte un valor de texto arbitrario (ej. 'Completamente satisfecho') en
    un nombre de campo único (ej. 'resp_completamente_satisfecho'), quitando
    tildes/espacios/puntuación con slugify. Si el resultado ya fue usado
    (colisión), le agrega un sufijo numérico incremental.
    """
    slug = slugify(valor).replace("-", "_") or "valor"
    field = f"resp_{slug}"
    base = field
    i = 2
    while field in usados:
        field = f"{base}_{i}"
        i += 1
    usados.add(field)
    return field


def tabla_conteo_por_respuesta(
    df,
    columna_categoria: str = "Categoría",
    columna_valor: str = "Respuesta",
    excluir=('No se utiliza', 'No aplica', 'N/A'),
) -> dict:
    """
    Agrupa `df` por `columna_categoria` y desglosa el conteo de
    `columna_valor` en una columna por cada valor único encontrado (con su %
    al lado), más una columna 'Total'. Formato compatible con Tabulator:
    { columns: [{title, field}], rows: [{...}] }.

    Los valores únicos que generan las columnas se determinan sobre TODO el
    DataFrame (no por categoría individual), para que todas las filas
    compartan el mismo set de columnas. Se excluyen automáticamente valores
    nulos/vacíos, más cualquier valor listado en `excluir`
    (ej. excluir=["N/A", "No aplica"]).

    El % y el 'Total' de cada fila se calculan sobre el total de valores NO
    excluidos de esa categoría (no sobre el total real de filas de la
    categoría). Como cada % se redondea de forma independiente, la suma de
    los % de una fila puede no dar exactamente 100%.

    Los nombres de campo (`field`) se derivan del texto de cada valor único
    vía slugify (ej. 'Completamente satisfecho' -> 'resp_completamente_satisfecho',
    con su % en 'pct_completamente_satisfecho'). El orden de las columnas de
    valor es alfabético, para ser determinista.

    Si `columna_categoria` o `columna_valor` no existen en `df`, retorna
    { "columns": [], "rows": [] }.
    """
    if columna_categoria not in df.columns or columna_valor not in df.columns:
        return {"columns": [], "rows": []}

    excluidos = {str(v).strip().lower() for v in excluir} | {"", "nan", "none", "nat"}

    valores_col = df[columna_valor].astype(str).str.strip()
    valores_unicos = sorted(v for v in valores_col.unique() if v.lower() not in excluidos)

    usados = set()
    campos = {}  # valor -> (field_conteo, field_pct)
    for valor in valores_unicos:
        field_valor = _campo_desde_valor(valor, usados)
        field_pct = "pct_" + field_valor[len("resp_"):]
        campos[valor] = (field_valor, field_pct)

    columns = [{"title": columna_categoria, "field": columna_categoria}]
    for valor in valores_unicos:
        field_valor, field_pct = campos[valor]
        columns.append({"title": valor, "field": field_valor})
        columns.append({"title": "%", "field": field_pct})
    columns.append({"title": "Total", "field": "Total"})

    rows = []
    for cat in sorted(df[columna_categoria].dropna().unique()):
        sub_valores = df.loc[df[columna_categoria] == cat, columna_valor].astype(str).str.strip()
        total = int(sub_valores.isin(valores_unicos).sum())

        fila = {columna_categoria: cat}
        for valor in valores_unicos:
            field_valor, field_pct = campos[valor]
            conteo = int((sub_valores == valor).sum())
            fila[field_valor] = conteo
            fila[field_pct] = f"{round(conteo / total * 100)}%" if total else "0%"
        fila["Total"] = total
        rows.append(fila)

    return {"columns": columns, "rows": rows}
