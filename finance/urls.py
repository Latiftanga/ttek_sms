from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Dashboard
    path('', views.index, name='index'),

    # Fee Structures
    path('fee-structures/', views.fee_structures, name='fee_structures'),
    path('fee-structures/create/', views.fee_structure_create, name='fee_structure_create'),
    path('fee-structures/<int:pk>/edit/', views.fee_structure_edit, name='fee_structure_edit'),
    path('fee-structures/<int:pk>/delete/', views.fee_structure_delete, name='fee_structure_delete'),

    # Scholarships
    path('scholarships/', views.scholarships, name='scholarships'),
    path('scholarships/create/', views.scholarship_create, name='scholarship_create'),
    path('scholarships/<int:pk>/edit/', views.scholarship_edit, name='scholarship_edit'),
    path('scholarships/<int:pk>/delete/', views.scholarship_delete, name='scholarship_delete'),
    path('scholarships/<int:pk>/assign/', views.scholarship_assign, name='scholarship_assign'),

    # Invoices
    path('invoices/', views.invoices, name='invoices'),
    path('invoices/generate/', views.invoice_generate, name='invoice_generate'),
    path('invoices/<uuid:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<uuid:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('invoices/<uuid:pk>/cancel/', views.invoice_cancel, name='invoice_cancel'),
    path('invoices/<uuid:pk>/print/', views.invoice_print, name='invoice_print'),

    # Payments
    path('payments/', views.payments, name='payments'),
    path('payments/record/', views.payment_record, name='payment_record'),
    path('payments/<uuid:pk>/', views.payment_detail, name='payment_detail'),
    path('payments/<uuid:pk>/receipt/', views.payment_receipt, name='payment_receipt'),

    # Online Payments
    path('pay/<uuid:invoice_pk>/', views.pay_online, name='pay_online'),
    path('pay/callback/', views.payment_callback, name='payment_callback'),
    path('pay/webhook/', views.payment_webhook, name='payment_webhook'),

    # Student Fees (student-specific views)
    path('students/<uuid:student_id>/fees/', views.student_fees, name='student_fees'),
    path('students/<uuid:student_id>/statement/', views.student_statement, name='student_statement'),

    # Reports
    path('reports/', views.reports, name='reports'),
    path('reports/collection/', views.collection_report, name='collection_report'),
    path('reports/outstanding/', views.outstanding_report, name='outstanding_report'),
    path('reports/export/', views.export_report, name='export_report'),

    # Payment Gateway Settings
    path('settings/', views.gateway_settings, name='gateway_settings'),
    path('settings/gateway/<int:pk>/configure/', views.gateway_configure, name='gateway_configure'),
    path('settings/gateway/<int:pk>/verify/', views.gateway_verify, name='gateway_verify'),

    # API endpoints for AJAX/HTMX
    path('api/student/<uuid:student_id>/balance/', views.api_student_balance, name='api_student_balance'),
    path('api/class/<int:class_id>/fees/', views.api_class_fees, name='api_class_fees'),
    path('api/students/search/', views.student_search, name='student_search'),
    path('api/invoices/search/', views.invoice_search, name='invoice_search'),

    # Notifications
    path('notifications/', views.notification_center, name='notification_center'),
    path('notifications/send/<uuid:pk>/', views.send_invoice_notification_view, name='send_notification'),
    path('notifications/bulk/', views.send_bulk_notifications_view, name='send_bulk_notifications'),
    path('notifications/history/', views.notification_history, name='notification_history'),
]
