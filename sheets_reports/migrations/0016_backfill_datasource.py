from django.db import migrations


def backfill_datasource(apps, schema_editor):
    """
    Crea una DataSource(source_type="google_sheets") por cada Dashboard existente que todavía
    no tenga data_source y tenga un source_url no vacío, y la asigna. Idempotente: se puede
    re-correr sin duplicar (guardada por data_source_id is None).
    """
    Dashboard = apps.get_model("sheets_reports", "Dashboard")
    DataSource = apps.get_model("sheets_reports", "DataSource")

    for dashboard in Dashboard.objects.filter(data_source__isnull=True).exclude(source_url=""):
        data_source = DataSource.objects.create(
            name=f"{dashboard.title} (Sheets)",
            source_type="google_sheets",
            config={"source_url": dashboard.source_url},
            owner_id=dashboard.user_id,
        )
        dashboard.data_source = data_source
        dashboard.save(update_fields=["data_source"])


def noop_reverse(apps, schema_editor):
    """No revertimos: borrar las DataSource creadas podría afectar tableros que ya las usen
    activamente para el momento en que alguien corra el reverse."""


class Migration(migrations.Migration):

    dependencies = [
        ("sheets_reports", "0015_alter_dashboard_source_url_datasource_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_datasource, noop_reverse),
    ]
