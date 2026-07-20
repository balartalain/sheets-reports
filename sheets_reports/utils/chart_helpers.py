"""
Helpers de formateo/agregación de DataFrames para widgets tipo 'bar', 'line' y
'donut' (ApexCharts). Reciben el DataFrame ya cargado y filtrado (cada widget.code
sigue siendo responsable de llamar `get_cached_df` y `apply_active_filters` antes
de invocar estos helpers) y retornan un dict con el formato { "series": [{name, data}],
"categories": [...] } — quien llama es responsable de envolverlo en
JsonResponse.
"""
from .registry import util


@util(
    category="Cadena",
    description=(
        "Trunca un texto al largo pasado por parámetro, agregando '...'"
        " al final si se excede. Retorna el texto original si no supera el largo."
    ),
    example="data = _truncar('Este es un texto muy largo', 10)",
)
def _truncar(texto: str, largo: int = 30) -> str:
    texto = str(texto)
    return texto[:largo] + "..." if len(texto) > largo else texto