from django.urls import path
from . import views

app_name = 'teachers'

urlpatterns = [
    path('', views.index, name='index'),
    path('create/', views.teacher_create, name='teacher_create'),
    path('<int:pk>/', views.teacher_detail, name='teacher_detail'),
    path('<int:pk>/edit/', views.teacher_edit, name='teacher_edit'),
    path('<int:pk>/delete/', views.teacher_delete, name='teacher_delete'),
    path('import/', views.bulk_import, name='bulk_import'),
    path('import/confirm/', views.bulk_import_confirm, name='bulk_import_confirm'),
    path('import/template/', views.bulk_import_template, name='bulk_import_template'),
]