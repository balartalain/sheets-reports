import time

import pandas as pd
from django.core.cache import cache

from sheets_reports.connectors.base import DataFrameBackedConnector

CACHE_TIMEOUT = 300  # 5 minutos
LOCK_TIMEOUT = 30  # segundos máximo que puede tardar un fetch a Google Sheets (protegido por rate limiter global)
LOCK_POLL_INTERVAL = 0.2


def fetch_with_lock(cache_key: str, timeout: int, fetch_fn):
    """
    Obtiene `cache_key` de cache (DatabaseCache, compartido entre workers),
    o lo genera con `fetch_fn()` si no existe.
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

    deadline = time.monotonic() + LOCK_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(LOCK_POLL_INTERVAL)
        value = cache.get(cache_key)
        if value is not None:
            return value

    value = fetch_fn()
    cache.set(cache_key, value, timeout)
    return value


def _dataframe_connector(dashboard) -> DataFrameBackedConnector:
    """Resuelve el DataConnector del tablero y exige que sea DataFrame-backed (ej. Google
    Sheets) -- es el único tipo de origen que get_cached_df/get_cached_sheets_preview saben
    servir. Un origen SQL nativo (ej. Postgres) no tiene "DataFrame completo" que traer: se
    consulta con SQL vía get_query_connection (ver utils/duckdb_query.py)."""
    if dashboard.data_source_id is None:
        raise ValueError(f"El tablero {dashboard.id} no tiene un origen de datos configurado (data_source).")
    connector = dashboard.data_source.get_connector()
    if not isinstance(connector, DataFrameBackedConnector):
        raise TypeError(
            f"get_cached_df/get_cached_sheets_preview requieren un origen basado en DataFrame "
            f"(ej. Google Sheets); el origen de este tablero es de tipo "
            f"'{dashboard.data_source.source_type}'. Usá get_query_connection(widget.dashboard) "
            f"para consultarlo con SQL."
        )
    return connector


def get_cached_df(dashboard, sheet_name: str | None = None) -> pd.DataFrame:
    from sheets_reports.utils.duckdb_query import get_query_connection

    connector = _dataframe_connector(dashboard)
    tables = connector.list_tables()
    if not tables:
        return pd.DataFrame()

    if sheet_name is None:
        table = tables[0]
    else:
        table = next((t for t in tables if t.name == sheet_name), None)
        if table is None:
            raise ValueError(
                f"La pestaña '{sheet_name}' no existe en el origen del tablero {dashboard.id}."
            )

    alias = dashboard.data_source.source_type
    qualified_name = connector.qualified_table_name(table, alias)
    con = get_query_connection(dashboard)
    try:
        return con.execute(f'SELECT * FROM "{qualified_name}"').df()
    finally:
        con.close()


def get_cached_sheets_preview(dashboard, n_rows: int = 3) -> dict:
    """Columnas + primeras `n_rows` filas de cada pestaña del origen de datos del tablero,
    cacheado. A diferencia de get_cached_df, no trae cada pestaña completa: solo lo necesario
    para que Gemini elija la pestaña correcta al generar código. Solo sirve para orígenes
    DataFrame-backed; ver get_cached_tables() para el equivalente genérico (cualquier tipo de
    origen) que usa generate_widget_ia._build_source_context."""
    cache_key = f"sheets_preview_{dashboard.id}_{n_rows}"
    connector = _dataframe_connector(dashboard)

    def _fetch():
        return {
            table.name: {"columns": table.columns, "sample_rows": table.sample_rows[:n_rows]}
            for table in connector.list_tables()
        }

    return fetch_with_lock(cache_key, CACHE_TIMEOUT, _fetch)


def get_cached_tables(dashboard):
    """
    Tablas/pestañas del origen de datos del tablero, con columnas y filas de ejemplo
    (cacheado, TTL corto). A diferencia de get_cached_sheets_preview, sirve para cualquier
    tipo de origen (no solo DataFrame-backed) -- es lo que usa
    generate_widget_ia._build_source_context para mostrarle a Gemini la estructura disponible.

    Sin este cacheo, cada llamada repite la introspección completa del origen (para Sheets,
    llamadas a la API de Google; para Postgres, varias consultas al servidor) -- costoso en
    generaciones que la piden muchas veces seguidas, ej. una vez por cada widget de un tablero
    generado de punta a punta (generate_dashboard_ia.generate_board_from_prompt), al punto de
    agotar la cuota de lectura de la API de Sheets si el tablero tiene varios widgets.
    """
    if dashboard.data_source_id is None:
        raise ValueError(f"El tablero {dashboard.id} no tiene un origen de datos configurado (data_source).")
    cache_key = f"source_tables_{dashboard.id}"
    connector = dashboard.data_source.get_connector()
    return fetch_with_lock(cache_key, CACHE_TIMEOUT, connector.list_tables)
