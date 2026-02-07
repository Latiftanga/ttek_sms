from django.urls import path
from . import views

app_name = 'academics'

urlpatterns = [
    # Main page
    path('', views.index, name='index'),
    path('assignment-dashboard/', views.assignment_dashboard, name='assignment_dashboard'),

    # Programme routes (SHS only)
    path('programmes/create/', views.programme_create, name='programme_create'),
    path('programmes/<int:pk>/edit/', views.programme_edit, name='programme_edit'),
    path('programmes/<int:pk>/delete/', views.programme_delete, name='programme_delete'),

    # Bulk Subject Import
    path('subjects/import/', views.bulk_subject_import, name='bulk_subject_import'),
    path('subjects/import/confirm/', views.bulk_subject_import_confirm, name='bulk_subject_import_confirm'),
    path('subjects/import/template/', views.bulk_subject_import_template, name='bulk_subject_import_template'),

    # Class routes
    path('classes/', views.classes_list, name='classes'),
    path('classes/export/', views.classes_bulk_export, name='classes_bulk_export'),
    path('classes/create/', views.class_create, name='class_create'),
    path('classes/<int:pk>/', views.class_detail, name='class_detail'),
    path('classes/<int:pk>/edit/', views.class_edit, name='class_edit'),
    path('classes/<int:pk>/delete/', views.class_delete, name='class_delete'),
    path('classes/<int:pk>/subjects/', views.class_subjects, name='class_subjects'),
    path('classes/<int:pk>/subjects/add/', views.class_subject_create, name='class_subject_create'),
    path('classes/<int:pk>/subjects/copy/', views.copy_subjects, name='copy_subjects'),
    path('classes/<int:class_pk>/subjects/<int:pk>/delete/', views.class_subject_delete, name='class_subject_delete'),
    path('classes/<int:pk>/enroll/', views.class_student_enroll, name='class_student_enroll'),
    
    # Remove: classes/1/students/50/remove/
    path('classes/<int:class_pk>/students/<int:student_pk>/remove/', views.class_student_remove, name='class_student_remove'),
    path('classes/<int:class_pk>/students/<int:student_pk>/electives/', views.class_student_electives, name='class_student_electives'),
    path('classes/<int:pk>/students/bulk-electives/', views.class_bulk_electives, name='class_bulk_electives'),
    path('classes/<int:pk>/students/bulk-assign/', views.class_bulk_subject_assign, name='class_bulk_subject_assign'),
    path('classes/<int:pk>/register/', views.class_register, name='class_register'),
    path('classes/<int:pk>/subjects/modal/', views.class_subjects_modal, name='class_subjects_modal'),
    path('classes/<int:pk>/attendance/take/', views.class_attendance_take, name='class_attendance_take'),
    path('classes/<int:pk>/attendance/history/', views.class_attendance_history, name='class_attendance_history'),
    path('classes/<int:pk>/attendance/<int:session_pk>/edit/', views.class_attendance_edit, name='class_attendance_edit'),

    # Per-lesson attendance
    path('classes/<int:pk>/attendance/lessons/', views.lesson_attendance_list, name='lesson_attendance_list'),
    path('attendance/lesson/<int:timetable_entry_id>/', views.take_lesson_attendance, name='take_lesson_attendance'),
    path('classes/<int:pk>/attendance/weekly-report/', views.class_weekly_attendance_report, name='class_weekly_attendance_report'),
    path('classes/<int:pk>/promote/', views.class_promote, name='class_promote'),
    path('classes/<int:pk>/export/', views.class_export, name='class_export'),
    path('classes/<int:pk>/pdf/', views.class_detail_pdf, name='class_detail_pdf'),
    path('classes/<int:pk>/sync-subjects/', views.class_sync_subjects, name='class_sync_subjects'),

    # Attendance reports
    path('attendance/', views.attendance_reports, name='attendance_reports'),
    path('attendance/export/', views.attendance_export, name='attendance_export'),
    path('attendance/notify-parents/', views.notify_absent_parents, name='notify_absent_parents'),
    path('attendance/student/<int:student_id>/', views.student_attendance_detail, name='student_attendance_detail'),
    path('attendance/class/<int:pk>/weekly-register/', views.weekly_attendance_register_pdf, name='weekly_attendance_register_pdf'),

    # Subject routes
    path('subjects/create/', views.subject_create, name='subject_create'),
    path('subjects/<int:pk>/edit/', views.subject_edit, name='subject_edit'),
    path('subjects/<int:pk>/delete/', views.subject_delete, name='subject_delete'),

    # Subject Template routes
    path('templates/create/', views.template_create, name='template_create'),
    path('templates/<int:pk>/edit/', views.template_edit, name='template_edit'),
    path('templates/<int:pk>/delete/', views.template_delete, name='template_delete'),
    path('classes/<int:pk>/apply-template/', views.apply_template, name='apply_template'),

    # API endpoints
    path('api/class/<int:pk>/subjects/', views.api_class_subjects, name='api_class_subjects'),

    # Period Management (Timetable Setup)
    path('periods/', views.periods, name='periods'),
    path('periods/create/', views.period_create, name='period_create'),
    path('periods/<int:pk>/edit/', views.period_edit, name='period_edit'),
    path('periods/<int:pk>/delete/', views.period_delete, name='period_delete'),

    # Classroom Management
    path('classrooms/', views.classrooms, name='classrooms'),
    path('classrooms/create/', views.classroom_create, name='classroom_create'),
    path('classrooms/<int:pk>/edit/', views.classroom_edit, name='classroom_edit'),
    path('classrooms/<int:pk>/delete/', views.classroom_delete, name='classroom_delete'),

    # Timetable Management
    path('timetable/', views.timetable_index, name='timetable'),
    path('timetable/class/<int:class_id>/', views.class_timetable, name='class_timetable'),
    path('timetable/class/<int:class_id>/entry/create/', views.timetable_entry_create, name='timetable_entry_create'),
    path('timetable/class/<int:class_id>/entry/bulk/', views.bulk_timetable_entry, name='bulk_timetable_entry'),
    path('timetable/class/<int:class_id>/copy/', views.copy_timetable, name='copy_timetable'),
    path('timetable/entry/<int:pk>/edit/', views.timetable_entry_edit, name='timetable_entry_edit'),
    path('timetable/entry/<int:pk>/delete/', views.timetable_entry_delete, name='timetable_entry_delete'),
    path('timetable/teacher-schedule/', views.teacher_schedule_preview, name='teacher_schedule_preview'),
]
