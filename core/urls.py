from django.urls import path
from core import views

app_name = 'core'

urlpatterns = [
    path('', views.school_dashboard, name='dashboard'),
    path('about/', views.school_about, name='about'),
]