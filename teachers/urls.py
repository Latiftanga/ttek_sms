from django.urls import path
from . import views

app_name = 'teachers'

urlpatterns = [
    # Admin routes (managing teachers)
    path('', views.index, name='index'),
    path('create/', views.teacher_create, name='teacher_create'),
    path('<uuid:pk>/', views.teacher_detail, name='teacher_detail'),
    path('<uuid:pk>/pdf/', views.teacher_detail_pdf, name='teacher_detail_pdf'),
    path('<uuid:pk>/edit/', views.teacher_edit, name='teacher_edit'),
    path('<uuid:pk>/delete/', views.teacher_delete, name='teacher_delete'),
    path('<uuid:pk>/schedule/', views.teacher_schedule, name='teacher_schedule'),
    path('<uuid:pk>/create-account/', views.create_account, name='create_account'),
    path('<uuid:pk>/deactivate-account/', views.deactivate_account, name='deactivate_account'),
    path('<uuid:pk>/reset-password/', views.reset_password, name='reset_password'),
    path('<uuid:pk>/toggle-admin/', views.toggle_school_admin, name='toggle_school_admin'),

    # Lesson assignment routes
    path('<uuid:pk>/assign-lesson/', views.assign_lesson, name='assign_lesson'),
    path('<uuid:pk>/unassign-lesson/<int:assignment_pk>/', views.unassign_lesson, name='unassign_lesson'),

    # Invitation routes
    path('<uuid:pk>/send-invitation/', views.send_invitation, name='send_invitation'),
    path('<uuid:pk>/resend-invitation/', views.resend_invitation, name='resend_invitation'),
    path('<uuid:pk>/cancel-invitation/', views.cancel_invitation, name='cancel_invitation'),
    path('invite/<str:token>/', views.accept_invitation, name='accept_invitation'),

    path('import/', views.bulk_import, name='bulk_import'),
    path('import/confirm/', views.bulk_import_confirm, name='bulk_import_confirm'),
    path('import/template/', views.bulk_import_template, name='bulk_import_template'),
    path('export/', views.bulk_export, name='bulk_export'),

    # Analytics routes
    path('workload/overview/', views.school_workload_overview, name='school_workload_overview'),

    # Promotion routes
    path('<uuid:pk>/promotions/', views.promotion_list, name='promotion_list'),
    path('<uuid:pk>/promotions/create/', views.promotion_create, name='promotion_create'),
    path('<uuid:pk>/promotions/<uuid:promo_pk>/edit/', views.promotion_edit, name='promotion_edit'),
    path('<uuid:pk>/promotions/<uuid:promo_pk>/delete/', views.promotion_delete, name='promotion_delete'),

    # Qualification routes
    path('<uuid:pk>/qualifications/', views.qualification_list, name='qualification_list'),
    path('<uuid:pk>/qualifications/create/', views.qualification_create, name='qualification_create'),
    path('<uuid:pk>/qualifications/<uuid:qual_pk>/edit/', views.qualification_edit, name='qualification_edit'),
    path('<uuid:pk>/qualifications/<uuid:qual_pk>/delete/', views.qualification_delete, name='qualification_delete'),
]