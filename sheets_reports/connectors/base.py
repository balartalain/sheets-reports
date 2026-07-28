"""
Interfaz común para los orígenes de datos de un Dashboard (Google Sheets, Postgres, ...).

Un DataConnector se construye a partir de DataSource.config y sabe:
- validar/describir su propio config (config_schema)
- probar la conexión (test_connection)
- listar sus tablas/pestañas disponibles, para contexto de IA y para UI (list_tables)
- registrarse dentro de una conexión DuckDB para que sus datos sean consultables por SQL (register)

Hay dos formas fundamentalmente distintas de "registrarse" en DuckDB según si el origen
tiene motor SQL propio o no -- de ahí los dos mixins DataFrameBackedConnector /
SqlNativeConnector, que implementan register() cada uno a su manera. El resto del sistema
(duckdb_query.get_query_connection, cache.get_cached_df) solo conoce la interfaz de
DataConnector, nunca a cuál de los dos mixins pertenece una implementación concreta.
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb
    import pandas as pd
    from pydantic import BaseModel


class DataSourceConnectionError(Exception):
    """La conexión/consulta a un origen de datos falló (credenciales, red, config inválida, etc.)."""


@dataclass
class TableInfo:
    """Descripción de una tabla/pestaña consultable de un origen, para contexto de IA y UI."""
    name: str
    columns: list[str]
    sample_rows: list[dict] = field(default_factory=list)


class DataConnector(ABC):
    """Un DataConnector = una DataSource configurada, lista para ser consultada."""

    def __init__(self, config: dict):
        self.config = config

    @classmethod
    @abstractmethod
    def config_schema(cls) -> type["BaseModel"]:
        """Modelo pydantic usado para validar/coercionar DataSource.config de este tipo."""

    @abstractmethod
    def test_connection(self) -> None:
        """No retorna nada si la conexión es válida; levanta DataSourceConnectionError si no."""

    @abstractmethod
    def list_tables(self) -> list[TableInfo]:
        """Tablas/pestañas disponibles, con columnas y filas de ejemplo (para IA/UI)."""

    @abstractmethod
    def register(self, con: "duckdb.DuckDBPyConnection", alias: str) -> None:
        """Deja los datos de este origen consultables por SQL dentro de `con`, bajo `alias`."""

    @abstractmethod
    def qualified_table_name(self, table: TableInfo, alias: str) -> str:
        """
        Nombre EXACTO a usar en una consulta SQL (ej. en un FROM) contra la conexión que arma
        get_query_connection, una vez que este connector se registró bajo `alias` -- debe
        coincidir siempre con lo que register() efectivamente expone. `TableInfo.name` (de
        list_tables()) es el nombre "natural" de la tabla/pestaña (útil para mostrarlo a un
        humano o para funciones legacy como get_cached_df, que reciben ese nombre crudo);
        este método existe porque ese nombre natural casi nunca es, por sí solo, lo que hay
        que escribir en SQL -- separar ambos evita que la IA (o cualquier código) tenga que
        adivinar el esquema de nombres de cada tipo de conector.
        """


class DataFrameBackedConnector(DataConnector):
    """
    Orígenes sin motor SQL propio (Google Sheets, CSV, APIs...): los datos se traen enteros
    como pandas.DataFrame y se registran en DuckDB como vista virtual (duckdb.register), sin
    costo de copia. Cada tabla queda expuesta como "<alias>__<nombre_tabla_sanitizado>".
    """

    @abstractmethod
    def fetch_dataframe(self, table_name: str | None = None) -> "pd.DataFrame":
        """Trae los datos de una tabla/pestaña (o la default si table_name es None) como DataFrame."""

    def register(self, con: "duckdb.DuckDBPyConnection", alias: str) -> None:
        for table in self.list_tables():
            df = self.fetch_dataframe(table.name)
            if df.shape[1] == 0:
                continue
            con.register(self.qualified_table_name(table, alias), df)

    def qualified_table_name(self, table: TableInfo, alias: str) -> str:
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", table.name)
        safe_name = re.sub(r"_+", "_", safe_name).strip("_")
        return f"{alias}__{safe_name}"

    def fetch_all_dataframes(self) -> dict:
        """
        Trae TODAS las tablas de este origen de una vez, como { nombre_tabla: DataFrame } --
        usado por duckdb_query._init_database para llenar el archivo DuckDB persistente
        completo al (re)inicializarlo, en vez de ir tabla por tabla bajo demanda. Implementación
        genérica: un fetch_dataframe por tabla; subclases con una forma más barata de traer
        todo junto (ej. GoogleSheetsConnector, vía un solo batchGet) deben overridear este método.
        """
        return {table.name: self.fetch_dataframe(table.name) for table in self.list_tables()}


class SqlNativeConnector(DataConnector):
    """
    Orígenes con motor SQL propio (Postgres, MySQL...): DuckDB los federa directamente vía
    ATTACH, con pushdown real de la consulta al servidor -- nunca se traen los datos enteros
    a memoria como con DataFrameBackedConnector.
    """

    @abstractmethod
    def extension_name(self) -> str:
        """Nombre de la extensión DuckDB a instalar/cargar antes del ATTACH (ej. "postgres")."""

    @abstractmethod
    def attach_clause(self, alias: str) -> str:
        """Sentencia SQL de ATTACH que expone este origen bajo `alias`."""

    def register(self, con: "duckdb.DuckDBPyConnection", alias: str) -> None:
        ext = self.extension_name()
        con.execute(f"INSTALL {ext}; LOAD {ext};")
        con.execute(self.attach_clause(alias))

    def qualified_table_name(self, table: TableInfo, alias: str) -> str:
        return f"{alias}.{table.name}"
