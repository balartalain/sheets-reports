"""
Conector para PostgreSQL: DuckDB federa el servidor directamente vía su extensión `postgres`
(ATTACH ... TYPE postgres), con pushdown real de la consulta -- nunca se copian tablas
enteras a memoria como con el conector de Sheets.

READ_ONLY es fijo, no configurable: es la barrera de seguridad principal dado que el código
de los widgets corre en un exec() sandboxeado pero no totalmente confiable (ver
widget_dispatcher._build_exec_namespace). DuckDB rechaza cualquier INSERT/UPDATE/DDL contra
un attach read-only antes de que llegue a Postgres. Como defensa en profundidad, el rol de
Postgres usado en `config` debería tener permisos de solo lectura (GRANT SELECT) del lado
del servidor -- eso no lo puede forzar este código, queda documentado acá.
"""
import duckdb
import pydantic

from sheets_reports.connectors.base import (
    DataSourceConnectionError,
    SqlNativeConnector,
    TableInfo,
)
from sheets_reports.connectors.registry import connector


class PostgresConfig(pydantic.BaseModel):
    host: str
    port: int = 5432
    database: str
    user: str
    password: str
    sslmode: str = "prefer"


def _libpq_escape(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


@connector("postgres")
class PostgresConnector(SqlNativeConnector):

    def __init__(self, config: dict):
        super().__init__(config)
        self._cfg = PostgresConfig(**config)

    @classmethod
    def config_schema(cls) -> type[pydantic.BaseModel]:
        return PostgresConfig

    def extension_name(self) -> str:
        return "postgres"

    def _dsn(self) -> str:
        c = self._cfg
        return " ".join([
            f"host={_libpq_escape(c.host)}",
            f"port={c.port}",
            f"dbname={_libpq_escape(c.database)}",
            f"user={_libpq_escape(c.user)}",
            f"password={_libpq_escape(c.password)}",
            f"sslmode={_libpq_escape(c.sslmode)}",
        ])

    def attach_clause(self, alias: str) -> str:
        dsn_sql_literal = self._dsn().replace("'", "''")
        return f"ATTACH '{dsn_sql_literal}' AS {alias} (TYPE postgres, READ_ONLY)"

    def _connect_and_attach(self, alias: str = "pg") -> duckdb.DuckDBPyConnection:
        con = duckdb.connect(":memory:")
        try:
            self.register(con, alias)
        except Exception:
            con.close()
            raise
        return con

    def test_connection(self) -> None:
        try:
            con = self._connect_and_attach()
        except Exception as e:
            raise DataSourceConnectionError(str(e)) from e
        con.close()

    def list_tables(self) -> list[TableInfo]:
        alias = "pg"
        try:
            con = self._connect_and_attach(alias)
        except Exception as e:
            raise DataSourceConnectionError(str(e)) from e

        try:
            rows = con.execute(
                f"""
                SELECT table_schema, table_name, column_name
                FROM {alias}.information_schema.columns
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name, ordinal_position
                """
            ).fetchall()

            columns_by_table: dict[str, list[str]] = {}
            for schema, table, column in rows:
                key = f"{schema}.{table}"
                columns_by_table.setdefault(key, []).append(column)

            tables = []
            for qualified_name, columns in columns_by_table.items():
                try:
                    sample = con.execute(
                        f'SELECT * FROM {alias}.{qualified_name} LIMIT 3'
                    ).fetchdf().to_dict(orient="records")
                except Exception:
                    sample = []
                tables.append(TableInfo(name=qualified_name, columns=columns, sample_rows=sample))
            return tables
        except Exception as e:
            raise DataSourceConnectionError(str(e)) from e
        finally:
            con.close()
