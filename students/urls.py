from django.urls import path
from . import views

app_name = 'students'

urlpatterns = [
    # Main page
    path('', views.index, name='index'),

    # Student CRUD
    path('create/', views.student_create, name='student_create'),
    path('<int:pk>/', views.student_detail, name='student_detail'),
    path('<int:pk>/edit/', views.student_edit, name='student_edit'),
    path('<int:pk>/delete/', views.student_delete, name='student_delete'),

    # Bulk import
    path('import/', views.bulk_import, name='bulk_import'),
    path('import/confirm/', views.bulk_import_confirm, name='bulk_import_confirm'),
    path('import/template/', views.bulk_import_template, name='bulk_import_template'),

    # Promotion
    path('promotion/', views.promotion, name='promotion'),
    path('promotion/process/', views.promotion_process, name='promotion_process'),
]
