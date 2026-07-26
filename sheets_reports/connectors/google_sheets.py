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
from sheets_reports.utils.google_sheets import fetch_sheet_as_dataframe, fetch_sheets_preview


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

    def _cache_key(self, kind: str, table_name: str | None = None) -> str:
        """El nombre de pestaña puede traer espacios, ':', '/' -- inválidos como cache key
        para backends tipo memcached. source_url también es largo y con caracteres reservados.
        Hasheamos ambos para tener una key corta y segura sin importar el backend de cache."""
        raw = f"{kind}:{self._cfg.source_url}:{table_name or ''}"
        return f"sheets_connector_{hashlib.md5(raw.encode()).hexdigest()}"

    def test_connection(self) -> None:
        try:
            fetch_sheets_preview(self._cfg.source_url, n_rows=1)
        except Exception as e:
            raise DataSourceConnectionError(str(e)) from e

    def list_tables(self) -> list[TableInfo]:
        # Cacheado (misma disciplina lock+TTL que fetch_dataframe, ver ahí el porqué): register()
        # llama a esto por cada tabla del spreadsheet cada vez que un widget abre una conexión
        # DuckDB (get_query_connection) -- sin cachear, cada ejecución de un widget dispara una
        # llamada nueva a la API de Sheets solo para enumerar las pestañas.
        def _fetch():
            try:
                preview = fetch_sheets_preview(self._cfg.source_url)
            except Exception as e:
                raise DataSourceConnectionError(str(e)) from e
            return [
                TableInfo(name=title, columns=info["columns"], sample_rows=info["sample_rows"])
                for title, info in preview.items()
            ]

        return fetch_with_lock(self._cache_key("tables"), CACHE_TIMEOUT, _fetch)

    def fetch_dataframe(self, table_name: str | None = None):
        # Cacheado: register() (llamado por get_query_connection en CADA ejecución de un
        # widget) trae, sin esto, el DataFrame completo de TODAS las pestañas del spreadsheet
        # desde cero cada vez -- con varias pestañas, alcanza la cuota de lectura de la API de
        # Sheets en minutos. Mismo mecanismo de lock+TTL que ya usaba get_cached_df, solo que
        # acá vive detrás del conector para que también cubra el camino de get_query_connection
        # (no solo el de get_cached_df).
        def _fetch():
            try:
                return fetch_sheet_as_dataframe(self._cfg.source_url, sheet_name=table_name)
            except Exception as e:
                raise DataSourceConnectionError(str(e)) from e

        return fetch_with_lock(self._cache_key("df", table_name), CACHE_TIMEOUT, _fetch)
