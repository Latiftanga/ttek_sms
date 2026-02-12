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

    # Bulk import/export
    path('import/', views.bulk_import, name='bulk_import'),
    path('import/confirm/', views.bulk_import_confirm, name='bulk_import_confirm'),
    path('import/template/', views.bulk_import_template, name='bulk_import_template'),
    path('export/', views.bulk_export, name='bulk_export'),

    # Promotion
    path('promotion/', views.promotion, name='promotion'),
    path('promotion/<int:pk>/', views.promotion_detail, name='promotion_detail'),
    path('promotion/process/', views.promotion_process, name='promotion_process'),

    # Houses
    path('houses/', views.house_index, name='houses'),
    path('houses/create/', views.house_create, name='house_create'),
    path('houses/<int:pk>/', views.house_students, name='house_students'),
    path('houses/<int:pk>/edit/', views.house_edit, name='house_edit'),
    path('houses/<int:pk>/delete/', views.house_delete, name='house_delete'),
    path('houses/<int:pk>/assign-master/', views.house_assign_master, name='house_assign_master'),
    path('houses/remove-master/<int:pk>/', views.house_remove_master, name='house_remove_master'),
    path('houses/<int:pk>/students/pdf/', views.house_students_pdf, name='house_students_pdf'),
    path('houses/<int:pk>/students/excel/', views.house_students_excel, name='house_students_excel'),

    # Exeats
    path('exeats/verify/', views.exeat_verify, name='exeat_verify'),
    path('exeats/go/', views.exeat_landing, name='exeat_landing'),
    path('exeats/', views.exeat_index, name='exeat_index'),
    path('exeats/create/', views.exeat_create, name='exeat_create'),
    path('exeats/student-search/', views.exeat_student_search, name='exeat_student_search'),
    path('exeats/student/<int:pk>/guardian/', views.exeat_student_guardian, name='exeat_student_guardian'),
    path('exeats/report/', views.exeat_report, name='exeat_report'),
    path('exeats/report/pdf/', views.exeat_report_pdf, name='exeat_report_pdf'),
    path('exeats/report/excel/', views.exeat_report_excel, name='exeat_report_excel'),
    path('exeats/<uuid:pk>/', views.exeat_detail, name='exeat_detail'),
    path('exeats/<uuid:pk>/approve/', views.exeat_approve, name='exeat_approve'),
    path('exeats/<uuid:pk>/reject/', views.exeat_reject, name='exeat_reject'),
    path('exeats/<uuid:pk>/depart/', views.exeat_depart, name='exeat_depart'),
    path('exeats/<uuid:pk>/return/', views.exeat_return, name='exeat_return'),

    # Housemasters (Admin)
    path('housemasters/', views.housemaster_index, name='housemaster_index'),
    path('housemasters/assign/', views.housemaster_assign, name='housemaster_assign'),
    path('housemasters/<int:pk>/remove/', views.housemaster_remove, name='housemaster_remove'),
]
