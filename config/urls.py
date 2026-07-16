"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from sheets_reports import views
from sheets_reports import views_dashboard

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('tableros/<slug:board_slug>/edit/', views.board_editor, name='board_editor'),
    path('tableros/<slug:board_slug>/shared/', views.board_view, name='board_view'),
    path('api/dashboards/', views_dashboard.dashboard_list, name='dashboard_list'),
    path('api/dashboards/<int:dashboard_id>/', views_dashboard.dashboard_detail, name='dashboard_detail'),
    path('api/dashboard/<int:dashboard_id>/widgets/', views.dashboard_widgets, name='dashboard_widgets'),
    path('api/widget/<int:widget_id>/', views.widget_detail, name='widget_detail'),
    path('api/widget/<int:widget_id>/data/', views.widget_data, name='widget_data'),
    path('api/widget-functions/<slug:board_slug>/', views.widget_functions, name='widget_functions'),
    path('api/dashboard/<int:board_id>/filters/', views.dashboard_filters, name='dashboard_filters'),
]
