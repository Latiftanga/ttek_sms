"""
URL configuration for dashboard app
"""
from django.urls import path
from dashboard import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='index'),
    path('stats/', views.quick_stats_view, name='quick_stats'),
]