from django.contrib import admin

from sheets_reports.models import DataSource, Dashboard, WidgetInstance


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    """
    Único lugar para dar de alta un origen de datos por ahora (ej. una conexión Postgres):
    todavía no hay UI dedicada para esto en el front del dashboard. `config` es un JSONField
    sin encriptar (decisión explícita, ver plan) -- se lo excluye de list_display para no
    exponer credenciales en la vista de listado.
    """
    list_display = ["name", "source_type", "owner", "created_at"]
    list_filter = ["source_type", "created_at"]
    search_fields = ["name"]


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ["title", "data_source", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["title"]


@admin.register(WidgetInstance)
class WidgetInstanceAdmin(admin.ModelAdmin):
    list_display = ["title", "dashboard", "chart_type", "created_at"]
    list_filter = ["chart_type", "created_at"]
    search_fields = ["title"]
    fields = ["dashboard", "title", "chart_type", "properties"]
