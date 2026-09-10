"""
Lenguaje de consulta genérico para widgets: conexión DuckDB persistente por DataSource
(archivo en disco, uno por origen -- no por dashboard, para que varios dashboards que
apunten a la misma hoja/DB compartan el mismo archivo en vez de duplicar la carga), con
las tablas del origen de datos ya cargadas por completo (Sheets, vía CREATE TABLE + INSERT
de cada DataFrame) o adjuntadas (Postgres, vía ATTACH).

La base de datos se inicializa una sola vez y se reusa entre widgets, entre dashboards que
comparten origen, e incluso entre workers/gunicorn (archivo compartido). Cuando expira el
TTL del caché de DataFrames, el archivo .db se invalida y se reconstruye por completo en la
siguiente solicitud -- llenando TODAS las tablas de una vez (connector.fetch_all_dataframes),
sin escanear el código de cada widget para adivinar cuáles hacen falta.
"""
import logging
import os
import time
import duckdb

from django.core.cache import cache

from .cache import CACHE_TIMEOUT
from .registry import util
from sheets_reports.connectors.base import DataFrameBackedConnector

logger = logging.getLogger(__name__)

_DB_DIR = "/tmp"
_INIT_LOCK_TIMEOUT = 30
_SENTINEL = "__initialized__"


def _db_path(data_source_id: int) -> str:
    return os.path.join(_DB_DIR, f"duckdb_source_{data_source_id}.db")


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
        con = duckdb.connect(path, read_only=True)
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


def _apply_calculated_columns(con, data_source, qname: str) -> None:
    """
    Si `qname` tiene columnas calculadas activas, renombra la tabla física recién creada
    (sufijo "__base") y la reemplaza por una VIEW con el nombre original que agrega esas
    columnas -- así SELECT * FROM "{qname}" (sin calificar, tal como ya lo hace todo el
    código de widgets existente, incluido get_cached_df) las incluye automáticamente, sin
    que nadie tenga que llamar a ninguna función.

    Aislado en su propio try/except: una expresión rota en una columna calculada no debe
    tirar abajo la reconstrucción de TODO el origen de datos (lo comparten varios tableros).
    Si falla, la tabla queda como tabla física simple, sin la columna calculada rota.
    """
    calc_cols = list(data_source.calculated_columns.filter(table_name=qname, is_active=True))
    if not calc_cols:
        return
    try:
        base_name = f"{qname}__base"
        con.execute(f'ALTER TABLE "{qname}" RENAME TO "{base_name}"')
        extra_cols_sql = ", ".join(f'({cc.expression}) AS "{cc.column_name}"' for cc in calc_cols)
        con.execute(f'CREATE VIEW "{qname}" AS SELECT *, {extra_cols_sql} FROM "{base_name}"')
    except Exception:
        logger.exception(
            "No se pudieron aplicar las columnas calculadas de '%s' (data_source %s); "
            "la tabla queda sin ellas.", qname, data_source.id,
        )
        con.execute(f'ALTER TABLE IF EXISTS "{base_name}" RENAME TO "{qname}"')


def invalidate_database(data_source) -> None:
    """
    Borra el archivo DuckDB cacheado de este origen (si existe), sin reconstruirlo. La
    próxima llamada a get_query_connection/get_cached_df lo reconstruye perezosamente --
    mismo mecanismo que ya existe para cuando expira el TTL normal. Se usa al crear/editar/
    borrar una columna calculada, para que el cambio no espere hasta 5 minutos en aparecer,
    sin bloquear el request de guardado con una reconstrucción completa (que implica volver
    a leer la hoja de cálculo).
    """
    path = _db_path(data_source.id)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        logger.exception("No se pudo invalidar la caché DuckDB del origen %s", data_source.id)


def _init_database(data_source) -> str:
    """
    Crea el archivo DuckDB y carga TODAS las tablas del origen por completo (Sheets: una
    tabla física por pestaña, vía connector.fetch_all_dataframes -- un solo values_batch_get
    del lado de Google Sheets, sin importar cuántas pestañas tenga; Postgres: ATTACH, sin
    copiar datos).
    """
    path = _db_path(data_source.id)
    alias = data_source.source_type

    if os.path.exists(path):
        os.remove(path)

    con = duckdb.connect(path)
    try:
        connector = data_source.get_connector()

        if isinstance(connector, DataFrameBackedConnector):
            dataframes = connector.fetch_all_dataframes()
            for table in connector.list_tables():
                df = dataframes.get(table.name)
                if df is None or df.shape[1] == 0:
                    continue
                qname = connector.qualified_table_name(table, alias)
                con.register("_df", df)
                con.execute(f'CREATE TABLE "{qname}" AS SELECT * FROM _df')
                con.execute("DROP VIEW IF EXISTS _df")
                _apply_calculated_columns(con, data_source, qname)
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


def refresh_database(data_source) -> None:
    """
    Fuerza la reconstrucción completa del archivo DuckDB de este origen, sin importar si
    seguía fresco -- usado por el management command refresh_sheets_cache (cron cada 5 min)
    para que el archivo nunca llegue a expirar bajo uso normal del dashboard. Mismo lock
    distribuido que get_query_connection, para no chocar con un request en vivo que esté
    reconstruyendo el mismo origen en simultáneo.
    """
    lock_key = f"duckdb_init_{data_source.id}"
    if cache.add(lock_key, "1", timeout=_INIT_LOCK_TIMEOUT):
        try:
            _init_database(data_source)
        finally:
            cache.delete(lock_key)


@util(
    category="Datos",
    description=(
        "Conexión DuckDB con las tablas del origen de datos del tablero ya registradas/adjuntas, "
        "lista para correr SQL. Funciona para cualquier tipo de origen (Google Sheets, Postgres, "
        "...) -- las tablas de Sheets quedan como '<tipo>__<pestaña>' (ver DataFrameBackedConnector), "
        "las de Postgres como '<tipo>.<schema>.<tabla>' (catálogo adjuntado vía ATTACH). "
        "La conexión se reusa entre widgets del mismo tablero, e incluso entre dashboards "
        "distintos que compartan el mismo origen de datos (archivo DuckDB persistente por "
        "DataSource)."
    ),
    example="con = get_query_connection(widget.dashboard); df = con.execute(\"SELECT * FROM postgres.public.ventas\").df()",
)
def get_query_connection(dashboard) -> duckdb.DuckDBPyConnection:
    if dashboard.data_source_id is None:
        raise ValueError(f"El tablero {dashboard.id} no tiene un origen de datos configurado (data_source).")

    path = _db_path(dashboard.data_source_id)

    # 1. Intentar abrir existente y fresco
    if _is_fresh(path):
        return duckdb.connect(path, read_only=True)

    # 2. Inicializar (con lock distribuido entre workers Y entre dashboards que compartan
    # el mismo origen, para que no lo reconstruyan dos veces en simultáneo)
    lock_key = f"duckdb_init_{dashboard.data_source_id}"
    if cache.add(lock_key, "1", timeout=_INIT_LOCK_TIMEOUT):
        try:
            # Otro proceso pudo haber inicializado mientras esperábamos el lock
            if _is_fresh(path):
                return duckdb.connect(path, read_only=True)

            _init_database(dashboard.data_source)
        finally:
            cache.delete(lock_key)

        return duckdb.connect(path, read_only=True)

    # 3. Otro worker está inicializando — esperar a que termine
    deadline = time.monotonic() + _INIT_LOCK_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(0.2)
        if _is_fresh(path):
            return duckdb.connect(path, read_only=True)

    # Si el lock expiró sin éxito, reintentamos (recursión controlada)
    return get_query_connection(dashboard)
