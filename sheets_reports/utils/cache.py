import pandas as pd
from django.core.cache import cache

from .google_sheets import fetch_sheet_as_dataframe

CACHE_TIMEOUT = 300  # 5 minutos


def get_cached_df(dashboard) -> pd.DataFrame:
    """
    Retorna el DataFrame de la hoja de Google Sheets asociada al dashboard.
    Lo busca en cache primero; si no existe o expiró, lo obtiene de Google Sheets y lo cachea.
    """
    cache_key = f"sheet_df_{dashboard.id}"

    df = cache.get(cache_key)
    if df is not None:
        return df

    df = fetch_sheet_as_dataframe(dashboard.source_url)
    cache.set(cache_key, df, CACHE_TIMEOUT)
    return df


def invalidate_dashboard_cache(dashboard_id: int):
    """Invalida la cache para un dashboard (útil tras actualizar la hoja)."""
    cache.delete(f"sheet_df_{dashboard_id}")
