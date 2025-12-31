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
    path('<int:pk>/pdf/', views.student_detail_pdf, name='student_detail_pdf'),
    path('<int:pk>/create-account/', views.student_create_account, name='student_create_account'),

    # Student Guardian Management
    path('<int:pk>/guardians/add/', views.student_add_guardian, name='student_add_guardian'),
    path('<int:pk>/guardians/<int:guardian_pk>/remove/', views.student_remove_guardian, name='student_remove_guardian'),
    path('<int:pk>/guardians/<int:guardian_pk>/set-primary/', views.student_set_primary_guardian, name='student_set_primary_guardian'),
    path('<int:pk>/guardians/<int:guardian_pk>/update-relationship/', views.student_update_guardian_relationship, name='student_update_guardian_relationship'),

    # Guardian CRUD
    path('guardians/', views.guardian_index, name='guardian_index'),
    path('guardians/create/', views.guardian_create, name='guardian_create'),
    path('guardians/<int:pk>/edit/', views.guardian_edit, name='guardian_edit'),
    path('guardians/<int:pk>/delete/', views.guardian_delete, name='guardian_delete'),
    path('guardians/search/', views.guardian_search, name='guardian_search'),

    # Bulk import
    path('import/', views.bulk_import, name='bulk_import'),
    path('import/confirm/', views.bulk_import_confirm, name='bulk_import_confirm'),
    path('import/template/', views.bulk_import_template, name='bulk_import_template'),

    # Promotion
    path('promotion/', views.promotion, name='promotion'),
    path('promotion/process/', views.promotion_process, name='promotion_process'),
]
