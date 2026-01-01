from django.urls import path
from . import views

app_name = 'academics'

urlpatterns = [
    # Main page
    path('', views.index, name='index'),
    path('classes/', views.classes_list, name='classes'),

    # Programme routes (SHS only)
    path('programmes/create/', views.programme_create, name='programme_create'),
    path('programmes/<int:pk>/edit/', views.programme_edit, name='programme_edit'),
    path('programmes/<int:pk>/delete/', views.programme_delete, name='programme_delete'),

    # Class routes
    path('classes/create/', views.class_create, name='class_create'),
    path('classes/<int:pk>/', views.class_detail, name='class_detail'),
    path('classes/<int:pk>/edit/', views.class_edit, name='class_edit'),
    path('classes/<int:pk>/delete/', views.class_delete, name='class_delete'),
    path('classes/<int:pk>/subjects/', views.class_subject_create, name='class_subjects'),
    path('classes/<int:pk>/subjects/add/', views.class_subject_create, name='class_subject_create'),
    path('classes/<int:class_pk>/subjects/<int:pk>/delete/', views.class_subject_delete, name='class_subject_delete'),
    path('classes/<int:pk>/enroll/', views.class_student_enroll, name='class_student_enroll'),
    
    # Remove: classes/1/students/50/remove/
    path('classes/<int:class_pk>/students/<int:student_pk>/remove/', views.class_student_remove, name='class_student_remove'),
    path('classes/<int:pk>/attendance/take/', views.class_attendance_take, name='class_attendance_take'),
    path('classes/<int:pk>/attendance/<int:session_pk>/edit/', views.class_attendance_edit, name='class_attendance_edit'),
    path('classes/<int:pk>/promote/', views.class_promote, name='class_promote'),
    path('classes/<int:pk>/export/', views.class_export, name='class_export'),

    # Attendance reports
    path('attendance/', views.attendance_reports, name='attendance_reports'),
    path('attendance/export/', views.attendance_export, name='attendance_export'),
    path('attendance/notify-parents/', views.notify_absent_parents, name='notify_absent_parents'),
    path('attendance/student/<int:student_id>/', views.student_attendance_detail, name='student_attendance_detail'),

    # Subject routes
    path('subjects/create/', views.subject_create, name='subject_create'),
    path('subjects/<int:pk>/edit/', views.subject_edit, name='subject_edit'),
    path('subjects/<int:pk>/delete/', views.subject_delete, name='subject_delete'),

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
    path('timetable/entry/<int:pk>/edit/', views.timetable_entry_edit, name='timetable_entry_edit'),
    path('timetable/entry/<int:pk>/delete/', views.timetable_entry_delete, name='timetable_entry_delete'),
]
