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
    path('guardians/<int:pk>/', views.guardian_detail, name='guardian_detail'),
    path('guardians/<int:pk>/edit/', views.guardian_edit, name='guardian_edit'),
    path('guardians/<int:pk>/delete/', views.guardian_delete, name='guardian_delete'),
    path('guardians/search/', views.guardian_search, name='guardian_search'),

    # Guardian Portal Invitations
    path('guardians/<int:pk>/send-invitation/', views.guardian_send_invitation, name='guardian_send_invitation'),
    path('guardians/<int:pk>/resend-invitation/', views.guardian_resend_invitation, name='guardian_resend_invitation'),
    path('guardians/<int:pk>/cancel-invitation/', views.guardian_cancel_invitation, name='guardian_cancel_invitation'),
    path('guardians/<int:pk>/deactivate-account/', views.guardian_deactivate_account, name='guardian_deactivate_account'),
    path('guardians/<int:pk>/activate-account/', views.guardian_activate_account, name='guardian_activate_account'),
    path('guardians/invite/<str:token>/', views.guardian_accept_invitation, name='guardian_accept_invitation'),

    # Bulk import
    path('import/', views.bulk_import, name='bulk_import'),
    path('import/confirm/', views.bulk_import_confirm, name='bulk_import_confirm'),
    path('import/template/', views.bulk_import_template, name='bulk_import_template'),

    # Promotion
    path('promotion/', views.promotion, name='promotion'),
    path('promotion/process/', views.promotion_process, name='promotion_process'),

    # Houses
    path('houses/', views.house_index, name='houses'),
    path('houses/create/', views.house_create, name='house_create'),
    path('houses/<int:pk>/edit/', views.house_edit, name='house_edit'),
    path('houses/<int:pk>/delete/', views.house_delete, name='house_delete'),
]
