from django.urls import path
from core import views
from auth.urls import app_name

app_name = 'core'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('developer/', views.developer_portal_view, name='developer_portal'),
    path('system/', views.system_overview_view, name='system_overview'),
    path('login/', views.school_login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('setup/', views.school_setup_view, name='school_setup'),
]