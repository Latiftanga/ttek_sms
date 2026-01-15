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

    # Invitation routes
    path('<uuid:pk>/send-invitation/', views.send_invitation, name='send_invitation'),
    path('<uuid:pk>/resend-invitation/', views.resend_invitation, name='resend_invitation'),
    path('<uuid:pk>/cancel-invitation/', views.cancel_invitation, name='cancel_invitation'),
    path('invite/<str:token>/', views.accept_invitation, name='accept_invitation'),

    path('import/', views.bulk_import, name='bulk_import'),
    path('import/confirm/', views.bulk_import_confirm, name='bulk_import_confirm'),
    path('import/template/', views.bulk_import_template, name='bulk_import_template'),
]