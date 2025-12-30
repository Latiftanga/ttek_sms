from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Dashboard
    path('', views.index, name='index'),
    path('profile/', views.profile, name='profile'),
    path('schedule/', views.schedule, name='schedule'),

    # School Admin routes
    path('settings/', views.settings, name='settings'),

    # Settings update routes (modal POST handlers)
    path('settings/update/basic/', views.settings_update_basic, name='settings_update_basic'),
    path('settings/update/branding/', views.settings_update_branding, name='settings_update_branding'),
    path('settings/update/contact/', views.settings_update_contact, name='settings_update_contact'),
    path('settings/update/admin/', views.settings_update_admin, name='settings_update_admin'),
    path('settings/update/academic/', views.settings_update_academic, name='settings_update_academic'),
    path('settings/update/sms/', views.settings_update_sms, name='settings_update_sms'),
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

    # Parent routes
    path('my-wards/', views.my_wards, name='my_wards'),
    path('fee-payments/', views.fee_payments, name='fee_payments'),
]