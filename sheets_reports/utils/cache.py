import time

import pandas as pd
from django.core.cache import cache

from .google_sheets import fetch_sheet_as_dataframe, list_worksheet_titles

CACHE_TIMEOUT = 300  # 5 minutos
LOCK_TIMEOUT = 30  # segundos máximo que puede tardar un fetch a Google Sheets
LOCK_POLL_INTERVAL = 0.2


def _fetch_with_lock(cache_key: str, timeout: int, fetch_fn):
    """
    Obtiene `cache_key` de cache, o lo genera con `fetch_fn()` si no existe.
    Usa un lock (vía `cache.add`, atómico) para que, cuando varias requests piden
    la misma key al mismo tiempo con la cache fría, solo UNA llame a la API real;
    el resto espera y reusa ese resultado en vez de cada una golpear la API por su
    cuenta (lo que agota la cuota de lectura de Sheets en cargas con muchos widgets).
    """
    value = cache.get(cache_key)
    if value is not None:
        return value

    lock_key = f"{cache_key}_lock"
    if cache.add(lock_key, True, LOCK_TIMEOUT):
        try:
            value = fetch_fn()
            cache.set(cache_key, value, timeout)
            return value
        finally:
            cache.delete(lock_key)

    # Otra request ya está haciendo el fetch: esperamos a que lo deje en cache.
    deadline = time.monotonic() + LOCK_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(LOCK_POLL_INTERVAL)
        value = cache.get(cache_key)
        if value is not None:
            return value

    # El que tenía el lock nunca terminó (o expiró): lo intentamos nosotros.
    value = fetch_fn()
    cache.set(cache_key, value, timeout)
    return value


def get_cached_df(dashboard, sheet_name: str | None = None) -> pd.DataFrame:
    """
    Retorna el DataFrame de una pestaña del Google Sheet asociado al dashboard.
    Lo busca en cache primero; si no existe o expiró, lo obtiene de Google Sheets y lo cachea.

    Cada función de widget llama esto directamente indicando la hoja que necesita
    (sheet_name=None usa la primera hoja), y puede llamarla más de una vez para
    cruzar datos de varias pestañas del mismo spreadsheet.
    """
    cache_key = f"sheet_df_{dashboard.id}_{(sheet_name or '__default__').replace(' ', '_')}"
    return _fetch_with_lock(
        cache_key, CACHE_TIMEOUT, lambda: fetch_sheet_as_dataframe(dashboard.source_url, sheet_name)
    )


def get_cached_sheet_titles(dashboard) -> list[str]:
    """Retorna los títulos de las pestañas del spreadsheet del dashboard, cacheados."""
    cache_key = f"sheet_titles_{dashboard.id}"
    return _fetch_with_lock(
        cache_key, CACHE_TIMEOUT, lambda: list_worksheet_titles(dashboard.source_url)
    )
