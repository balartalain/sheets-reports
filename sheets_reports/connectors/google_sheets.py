"""Conector para Google Sheets: envuelve sheets_reports.utils.google_sheets (gspread) detrás
de la interfaz DataConnector, sin reescribir esa lógica."""
import hashlib

import pydantic

from sheets_reports.connectors.base import (
    DataFrameBackedConnector,
    DataSourceConnectionError,
    TableInfo,
)
from sheets_reports.connectors.registry import connector
from sheets_reports.utils.cache import CACHE_TIMEOUT, fetch_with_lock
from sheets_reports.utils.google_sheets import (
    fetch_all_sheets_as_dataframes,
    fetch_sheet_as_dataframe,
    fetch_sheets_preview,
)


class GoogleSheetsConfig(pydantic.BaseModel):
    source_url: str


@connector("google_sheets")
class GoogleSheetsConnector(DataFrameBackedConnector):

    def __init__(self, config: dict):
        super().__init__(config)
        self._cfg = GoogleSheetsConfig(**config)

    @classmethod
    def config_schema(cls) -> type[pydantic.BaseModel]:
        return GoogleSheetsConfig

    def _tables_cache_key(self) -> str:
        """source_url es largo y con caracteres reservados -- inválido como cache key para
        backends tipo memcached. Hasheamos para tener una key corta y segura sin importar
        el backend de cache."""
        return f"sheets_connector_tables_{hashlib.md5(self._cfg.source_url.encode()).hexdigest()}"

    def test_connection(self) -> None:
        try:
            fetch_sheets_preview(self._cfg.source_url, n_rows=1)
        except Exception as e:
            raise DataSourceConnectionError(str(e)) from e

    def list_tables(self) -> list[TableInfo]:
        # Cacheado (metadata liviana: columnas + muestras, no el DataFrame completo): se llama
        # cada vez que un widget abre una conexión DuckDB (get_query_connection) -- sin cachear,
        # cada ejecución dispararía una llamada nueva a la API de Sheets solo para enumerar
        # las pestañas.
        def _fetch():
            try:
                preview = fetch_sheets_preview(self._cfg.source_url)
            except Exception as e:
                raise DataSourceConnectionError(str(e)) from e
            return [
                TableInfo(name=title, columns=info["columns"], sample_rows=info["sample_rows"])
                for title, info in preview.items()
            ]

        return fetch_with_lock(self._tables_cache_key(), CACHE_TIMEOUT, _fetch)

    def fetch_dataframe(self, table_name: str | None = None):
        try:
            return fetch_sheet_as_dataframe(self._cfg.source_url, sheet_name=table_name)
        except Exception as e:
            raise DataSourceConnectionError(str(e)) from e

    def fetch_all_dataframes(self) -> dict:
        """
        Trae TODAS las pestañas de una vez, en un solo values_batch_get (ver
        fetch_all_sheets_as_dataframes), sin importar cuántas pestañas tenga el spreadsheet.
        Usado por duckdb_query para llenar/refrescar el archivo DuckDB persistente completo --
        la decisión de CUÁNDO llamar a esto (¿sigue fresco el .db?) la toma duckdb_query
        (get_query_connection/_is_fresh), no hace falta un segundo nivel de cache acá: el
        archivo DuckDB ya es la única copia cacheada de estos datos.
        """
        try:
            return fetch_all_sheets_as_dataframes(self._cfg.source_url)
        except Exception as e:
            raise DataSourceConnectionError(str(e)) from e
