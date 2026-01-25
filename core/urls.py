from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Dashboard
    path('', views.index, name='index'),
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('schedule/', views.schedule, name='schedule'),

    # Setup Wizard
    path('setup/', views.setup_wizard, name='setup_wizard'),
    path('setup/academic-year/', views.setup_wizard_academic_year, name='setup_wizard_academic_year'),
    path('setup/session-type/', views.setup_wizard_session_type, name='setup_wizard_session_type'),
    path('setup/terms/', views.setup_wizard_terms, name='setup_wizard_terms'),
    path('setup/classes/', views.setup_wizard_classes, name='setup_wizard_classes'),
    path('setup/classes/add/', views.setup_wizard_add_class, name='setup_wizard_add_class'),
    path('setup/classes/<int:pk>/remove/', views.setup_wizard_remove_class, name='setup_wizard_remove_class'),
    path('setup/classes/bulk/', views.setup_wizard_bulk_classes, name='setup_wizard_bulk_classes'),
    path('setup/classes/clear/', views.setup_wizard_clear_classes, name='setup_wizard_clear_classes'),
    path('setup/academic-year/clear/', views.setup_wizard_clear_academic_year, name='setup_wizard_clear_academic_year'),
    path('setup/terms/clear/', views.setup_wizard_clear_terms, name='setup_wizard_clear_terms'),
    path('setup/houses/', views.setup_wizard_houses, name='setup_wizard_houses'),
    path('setup/houses/clear/', views.setup_wizard_clear_houses, name='setup_wizard_clear_houses'),
    path('setup/houses/add/', views.setup_wizard_add_house, name='setup_wizard_add_house'),
    path('setup/houses/<int:pk>/remove/', views.setup_wizard_remove_house, name='setup_wizard_remove_house'),
    path('setup/seed/', views.setup_wizard_seed, name='setup_wizard_seed'),
    path('setup/complete/', views.setup_wizard_complete, name='setup_wizard_complete'),

    # Notifications
    path('notifications/', views.notifications_dropdown, name='notifications_dropdown'),
    path('notifications/badge/', views.notifications_badge, name='notifications_badge'),
    path('notifications/<int:pk>/read/', views.notification_mark_read, name='notification_mark_read'),
    path('notifications/mark-all-read/', views.notifications_mark_all_read, name='notifications_mark_all_read'),

    # School Admin routes
    path('settings/', views.settings_page, name='settings'),

    # Settings update routes (modal POST handlers)
    path('settings/update/basic/', views.settings_update_basic, name='settings_update_basic'),
    path('settings/update/branding/', views.settings_update_branding, name='settings_update_branding'),
    path('settings/update/contact/', views.settings_update_contact, name='settings_update_contact'),
    path('settings/update/admin/', views.settings_update_admin, name='settings_update_admin'),
    path('settings/update/academic/', views.settings_update_academic, name='settings_update_academic'),
    path('settings/update/sms/', views.settings_update_sms, name='settings_update_sms'),
    path('settings/update/email/', views.settings_update_email, name='settings_update_email'),
    path('settings/test-email/', views.settings_test_email, name='settings_test_email'),
    path('settings/test-sms/', views.settings_test_sms, name='settings_test_sms'),
    path('settings/test-payment/', views.settings_test_payment, name='settings_test_payment'),
    path('settings/update/payment/', views.settings_update_payment, name='settings_update_payment'),

    # Academic Year routes
    path('settings/academic-year/create/', views.academic_year_create, name='academic_year_create'),
    path('settings/academic-year/<uuid:pk>/edit/', views.academic_year_edit, name='academic_year_edit'),
    path('settings/academic-year/<uuid:pk>/delete/', views.academic_year_delete, name='academic_year_delete'),
    path('settings/academic-year/<uuid:pk>/set-current/', views.academic_year_set_current, name='academic_year_set_current'),

    # Term routes
    path('settings/term/create/', views.term_create, name='term_create'),
    path('settings/term/<uuid:pk>/edit/', views.term_edit, name='term_edit'),
    path('settings/term/<uuid:pk>/delete/', views.term_delete, name='term_delete'),
    path('settings/term/<uuid:pk>/set-current/', views.term_set_current, name='term_set_current'),

    # Teacher routes
    path('my-classes/', views.my_classes, name='my_classes'),
    path('my-classes/<int:class_id>/students/', views.class_students, name='class_students'),
    path('my-classes/<int:class_id>/students/enroll/', views.enroll_student, name='enroll_student'),
    path('my-classes/<int:class_id>/students/<int:student_id>/remove/', views.remove_student, name='remove_student'),
    path('my-classes/<int:class_id>/students/<int:student_id>/electives/', views.update_student_electives, name='update_student_electives'),
    path('my-classes/<int:class_id>/students/bulk-electives/', views.bulk_assign_electives, name='bulk_assign_electives'),
    path('my-attendance/', views.my_attendance, name='my_attendance'),
    path('my-attendance/take/<int:class_id>/', views.take_attendance, name='take_attendance'),
    path('my-grading/', views.my_grading, name='my_grading'),
    path('my-grading/<int:class_id>/<int:subject_id>/', views.enter_scores, name='enter_scores'),
    path('my-grading/<int:class_id>/<int:subject_id>/export/', views.export_scores, name='export_scores'),
    path('my-grading/<int:class_id>/<int:subject_id>/import/', views.import_scores, name='import_scores'),
    path('my-grading/<int:class_id>/<int:subject_id>/import/confirm/', views.import_scores_confirm, name='import_scores_confirm'),
    path('my-timetable/', views.my_timetable, name='my_timetable'),

    # Student routes
    path('my-results/', views.my_results, name='my_results'),
    path('timetable/', views.timetable, name='timetable'),
    path('my-fees/', views.my_fees, name='my_fees'),

    # Parent/Guardian routes
    path('my-wards/', views.my_wards, name='my_wards'),
    path('my-wards/<int:pk>/', views.ward_detail, name='ward_detail'),
    path('fee-payments/', views.fee_payments, name='fee_payments'),
    path('fee-payments/pay/<uuid:invoice_id>/', views.guardian_pay_invoice, name='guardian_pay_invoice'),
    path('fee-payments/callback/', views.guardian_payment_callback, name='guardian_payment_callback'),
    path('fee-payments/success/<uuid:payment_id>/', views.guardian_payment_success, name='guardian_payment_success'),
    path('fee-payments/failed/<uuid:payment_id>/', views.guardian_payment_failed, name='guardian_payment_failed'),

    # Document verification (public)
    path('verify/<str:code>/', views.verify_document, name='verify_document'),
]