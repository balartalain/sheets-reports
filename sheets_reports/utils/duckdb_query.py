"""
Lenguaje de consulta genérico para widgets: conexión DuckDB persistente por dashboard
(archivo en disco), con las tablas del origen de datos ya registradas (Sheets, vía
duckdb.register de un DataFrame) o adjuntadas (Postgres, vía ATTACH).

La base de datos se inicializa una sola vez y se reusa entre widgets e incluso entre
workers/gunicorn (archivo compartido). Cuando expira el TTL del caché de DataFrames, el
archivo .db se invalida y se reconstruye desde los pickle de la siguiente solicitud.
"""
import os
import time
import duckdb

from django.core.cache import cache

from .cache import CACHE_TIMEOUT
from .registry import util
from sheets_reports.connectors.base import DataFrameBackedConnector

_DB_DIR = "/tmp"
_INIT_LOCK_TIMEOUT = 120  # margen amplio para inicializar (fetch de Google Sheets API)
_SENTINEL = "__initialized__"


def _db_path(dashboard_id: int) -> str:
    return os.path.join(_DB_DIR, f"duckdb_{dashboard_id}.db")


def _is_fresh(path: str) -> bool:
    """
    Retorna True si el archivo .db existe, tiene al menos una tabla de datos
    además del centinela, y su TTL no expiró.
    """
    if not os.path.exists(path):
        return False
    if os.path.getmtime(path) + CACHE_TIMEOUT < time.time():
        os.remove(path)
        return False
    try:
        con = duckdb.connect(path)
        try:
            con.execute(f"SELECT 1 FROM {_SENTINEL}")
            # Verificar que hay al menos una tabla real (no solo el centinela).
            # Esto descarta archivos corruptos de versiones anteriores donde
            # con.register() creaba vistas temporales que no persistían.
            row = con.execute(
                f"SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_name != '{_SENTINEL}'"
            ).fetchone()
            return bool(row and row[0] > 0)
        finally:
            con.close()
    except Exception:
        return False


def _init_database(dashboard) -> str:
    """
    Inicializa la base DuckDB persistente: crea tablas persistentes a partir
    de los DataFrames (Google Sheets) o adjunta el catálogo (Postgres).
    """
    dashboard_id = dashboard.id
    path = _db_path(dashboard_id)
    alias = dashboard.data_source.source_type

    if os.path.exists(path):
        os.remove(path)

    con = duckdb.connect(path)
    try:
        connector = dashboard.data_source.get_connector()

        if isinstance(connector, DataFrameBackedConnector):
            for table in connector.list_tables():
                df = connector.fetch_dataframe(table.name)
                if df.shape[1] == 0:
                    continue
                name = connector.qualified_table_name(table, alias)
                con.register("_df", df)
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM _df")
                con.execute("DROP VIEW IF EXISTS _df")
        else:
            connector.register(con, alias=alias)

        con.execute(f"CREATE TABLE {_SENTINEL} AS SELECT 1")
    except Exception:
        con.close()
        if os.path.exists(path):
            os.remove(path)
        raise

    con.close()
    return path


@util(
    category="Datos",
    description=(
        "Conexión DuckDB con las tablas del origen de datos del tablero ya registradas/adjuntas, "
        "lista para correr SQL. Funciona para cualquier tipo de origen (Google Sheets, Postgres, "
        "...) -- las tablas de Sheets quedan como '<tipo>__<pestaña>' (ver DataFrameBackedConnector), "
        "las de Postgres como '<tipo>.<schema>.<tabla>' (catálogo adjuntado vía ATTACH). "
        "La conexión se reusa entre widgets del mismo tablero (archivo DuckDB persistente)."
    ),
    example="con = get_query_connection(widget.dashboard); df = con.execute(\"SELECT * FROM postgres.public.ventas\").df()",
)
def get_query_connection(dashboard) -> duckdb.DuckDBPyConnection:
    if dashboard.data_source_id is None:
        raise ValueError(f"El tablero {dashboard.id} no tiene un origen de datos configurado (data_source).")

    path = _db_path(dashboard.id)

    # 1. Intentar abrir existente y fresco
    if _is_fresh(path):
        return duckdb.connect(path)

    # 2. Inicializar (con lock distribuido entre workers)
    lock_key = f"duckdb_init_{dashboard.id}"
    if cache.add(lock_key, "1", timeout=_INIT_LOCK_TIMEOUT):
        try:
            # Otro proceso pudo haber inicializado mientras esperábamos el lock
            if _is_fresh(path):
                return duckdb.connect(path)

            _init_database(dashboard)
        finally:
            cache.delete(lock_key)

        return duckdb.connect(path)

    # 3. Otro worker está inicializando — esperar a que termine
    deadline = time.monotonic() + _INIT_LOCK_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(0.2)
        if _is_fresh(path):
            return duckdb.connect(path)

    # Si el lock expiró sin éxito, reintentamos (recursión controlada)
    return get_query_connection(dashboard)
