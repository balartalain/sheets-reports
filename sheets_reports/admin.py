from django.contrib import admin

from sheets_reports.models import Dashboard, WidgetInstance


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ["title", "view_module", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["title", "view_module"]


@admin.register(WidgetInstance)
class WidgetInstanceAdmin(admin.ModelAdmin):
    list_display = ["title", "dashboard", "chart_type", "function_name", "created_at"]
    list_filter = ["chart_type", "created_at"]
    search_fields = ["title", "function_name"]
