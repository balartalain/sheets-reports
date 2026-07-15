from django.db import migrations
from django.utils.text import slugify


def backfill_slugs(apps, schema_editor):
    Dashboard = apps.get_model('sheets_reports', 'Dashboard')
    for dashboard in Dashboard.objects.filter(slug__isnull=True).order_by('id'):
        base_slug = slugify(dashboard.title) or "tablero"
        slug = base_slug
        i = 2
        while Dashboard.objects.exclude(pk=dashboard.pk).filter(slug=slug).exists():
            slug = f"{base_slug}-{i}"
            i += 1
        dashboard.slug = slug
        dashboard.save(update_fields=['slug'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('sheets_reports', '0004_dashboard_slug_alter_widgetinstance_chart_type'),
    ]

    operations = [
        migrations.RunPython(backfill_slugs, noop),
    ]
