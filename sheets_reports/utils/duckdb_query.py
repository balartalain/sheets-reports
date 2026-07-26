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
_INIT_LOCK_TIMEOUT = 30  # init ahora solo crea esquemas vacíos, sin fetch de datos
_SENTINEL = "__initialized__"
_META = "__sheets_meta__"  # mapea qualified_name → nombre original de pestaña


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
    Crea el archivo DuckDB con tablas vacías (solo estructura) para cada pestaña
    del origen. No baja datos — eso se hace bajo demanda en _ensure_table_data
    cuando un widget realmente necesita la tabla.
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
            all_tables = connector.list_tables()
            con.execute(f"CREATE TABLE {_META} (qualified VARCHAR, original VARCHAR)")
            for table in all_tables:
                qname = connector.qualified_table_name(table, alias)
                if table.columns:
                    cols = ', '.join(f'"{c}" VARCHAR' for c in table.columns)
                    con.execute(f'CREATE TABLE "{qname}" ({cols})')
                esc_orig = table.original_name if hasattr(table, 'original_name') else table.name
                con.execute(
                    f"INSERT INTO {_META} VALUES ('{qname}', '{esc_orig.replace(chr(39), chr(39)+chr(39))}')"
                )
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


def _ensure_table_data(dashboard, qualified_table_name: str) -> None:
    """
    Si la tabla DuckDB está vacía (recién creada), baja los datos del origen
    y los inserta. Lock distribuido por tabla para que solo un worker lo haga.
    """
    path = _db_path(dashboard.id)
    if not _is_fresh(path):
        get_query_connection(dashboard)

    lock_key = f"duckdb_fill_{dashboard.id}_{qualified_table_name}"
    if not cache.add(lock_key, "1", timeout=_INIT_LOCK_TIMEOUT):
        return

    try:
        con = duckdb.connect(path)
        try:
            esc_q = qualified_table_name.replace("'", "''")
            row = con.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_name = '{esc_q}'"
            ).fetchone()
            table_exists = bool(row and row[0] > 0)

            if table_exists:
                row = con.execute(f'SELECT COUNT(*) FROM "{qualified_table_name}"').fetchone()
                if row and row[0] > 0:
                    return

            row = con.execute(
                f"SELECT original FROM {_META} WHERE qualified = '{esc_q}'"
            ).fetchone()
            if not row:
                return

            connector = dashboard.data_source.get_connector()
            if not isinstance(connector, DataFrameBackedConnector):
                return

            df = connector.fetch_dataframe(row[0])
            if df.shape[1] == 0:
                return

            if not table_exists:
                cols = ', '.join(f'"{c}" VARCHAR' for c in df.columns)
                con.execute(f'CREATE TABLE "{qualified_table_name}" ({cols})')

            con.register("_df", df)
            con.execute(f'INSERT INTO "{qualified_table_name}" SELECT * FROM _df')
            con.execute("DROP VIEW IF EXISTS _df")
        finally:
            con.close()
    finally:
        cache.delete(lock_key)


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
