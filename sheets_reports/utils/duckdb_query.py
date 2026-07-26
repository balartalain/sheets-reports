"""
Lenguaje de consulta genérico para widgets: una conexión DuckDB con las tablas del origen de
datos del tablero ya registradas (Sheets, vía duckdb.register de un DataFrame) o adjuntadas
(Postgres, vía ATTACH con pushdown real), lista para correr SQL sin que el widget necesite
saber de qué tipo de origen se trata -- ver sheets_reports.connectors.DataConnector.register.

No cacheamos la conexión en sí (no es picklable: tiene sockets/handles abiertos). Lo que sí
se cachea, dentro de cada connector, es lo que realmente es costoso de recalcular: para
Sheets, el fetch a la API de Google (ver GoogleSheetsConnector.fetch_dataframe, que reutiliza
el lock+TTL de get_cached_df); para Postgres no hay nada que cachear -- el ATTACH no trae
datos, es un descriptor liviano que DuckDB usa para empujar la consulta al servidor.
"""
import duckdb

from .registry import util


@util(
    category="Datos",
    description=(
        "Conexión DuckDB con las tablas del origen de datos del tablero ya registradas/adjuntas, "
        "lista para correr SQL. Funciona para cualquier tipo de origen (Google Sheets, Postgres, "
        "...) -- las tablas de Sheets quedan como '<tipo>__<pestaña>' (ver DataFrameBackedConnector), "
        "las de Postgres como '<tipo>.<schema>.<tabla>' (catálogo adjuntado vía ATTACH)."
    ),
    example="con = get_query_connection(widget.dashboard); df = con.execute(\"SELECT * FROM postgres.public.ventas\").df()",
)
def get_query_connection(dashboard) -> duckdb.DuckDBPyConnection:
    if dashboard.data_source_id is None:
        raise ValueError(f"El tablero {dashboard.id} no tiene un origen de datos configurado (data_source).")

    con = duckdb.connect(":memory:")
    try:
        connector = dashboard.data_source.get_connector()
        connector.register(con, alias=dashboard.data_source.source_type)
    except Exception:
        con.close()
        raise
    return con
