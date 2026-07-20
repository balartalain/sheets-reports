from django.contrib import admin

from sheets_reports.models import Dashboard, WidgetInstance


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["title"]


@admin.register(WidgetInstance)
class WidgetInstanceAdmin(admin.ModelAdmin):
    list_display = ["title", "dashboard", "chart_type", "created_at"]
    list_filter = ["chart_type", "created_at"]
    search_fields = ["title"]
    fields = ["dashboard", "title", "chart_type", "properties"]
