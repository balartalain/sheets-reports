import pandas as pd
from django.core.cache import cache

from .google_sheets import fetch_sheet_as_dataframe

CACHE_TIMEOUT = 300  # 5 minutos


def get_cached_df(dashboard, sheet_name: str | None = None) -> pd.DataFrame:
    """
    Retorna el DataFrame de una pestaña del Google Sheet asociado al dashboard.
    Lo busca en cache primero; si no existe o expiró, lo obtiene de Google Sheets y lo cachea.

    Cada función de widget llama esto directamente indicando la hoja que necesita
    (sheet_name=None usa la primera hoja), y puede llamarla más de una vez para
    cruzar datos de varias pestañas del mismo spreadsheet.
    """
    cache_key = f"sheet_df_{dashboard.id}_{sheet_name.replace(' ', '_') or '__default__'}"

    df = cache.get(cache_key)
    if df is not None:
        return df

    df = fetch_sheet_as_dataframe(dashboard.source_url, sheet_name)
    cache.set(cache_key, df, CACHE_TIMEOUT)
    return df


def invalidate_dashboard_cache(dashboard_id: int):
    """Invalida la cache para un dashboard (útil tras actualizar la hoja)."""
    cache.delete(f"sheet_df_{dashboard_id}")
