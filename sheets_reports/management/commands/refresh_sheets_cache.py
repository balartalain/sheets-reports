"""
Refresca en background el archivo DuckDB persistente de los orígenes DataFrame-backed
(Google Sheets) que estén en uso por al menos un Dashboard, para que las requests del
frontend siempre encuentren el archivo tibio y nunca necesiten golpear la API de Google
en línea ni esperar a que se reconstruya.

Pensado para dispararse periódicamente (cada 5 min) vía cron/systemd timer -- ver docs/connectors.md.
"""
from django.core.management.base import BaseCommand

from sheets_reports.connectors.base import DataFrameBackedConnector
from sheets_reports.models import DataSource
from sheets_reports.utils.duckdb_query import refresh_database


class Command(BaseCommand):
    help = "Refresca el archivo DuckDB de los orígenes de datos (Google Sheets) en uso por algún dashboard."

    def handle(self, *args, **options):
        sources = DataSource.objects.filter(
            source_type=DataSource.SourceType.GOOGLE_SHEETS,
            dashboards__isnull=False,
        ).distinct()

        if not sources:
            self.stdout.write("No hay orígenes Google Sheets en uso por ningún dashboard.")
            return

        for source in sources:
            connector = source.get_connector()
            if not isinstance(connector, DataFrameBackedConnector):
                continue
            try:
                refresh_database(source)
            except Exception as e:
                self.stderr.write(f"[{source.id}] {source.name}: error al refrescar -- {e}")
            else:
                self.stdout.write(f"[{source.id}] {source.name}: refrescado OK")
