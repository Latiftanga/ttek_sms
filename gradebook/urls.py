from django.urls import path
from . import views

app_name = 'gradebook'

urlpatterns = [
    path('', views.index, name='index'),
    path('settings/', views.settings, name='settings'),

    # Grading System CRUD
    path('grading-systems/', views.grading_systems, name='grading_systems'),
    path('grading-systems/create/', views.grading_system_create, name='grading_system_create'),
    path('grading-systems/<int:pk>/edit/', views.grading_system_edit, name='grading_system_edit'),
    path('grading-systems/<int:pk>/delete/', views.grading_system_delete, name='grading_system_delete'),

    # Grade Scale CRUD
    path('grading-systems/<int:system_id>/scales/', views.grade_scales, name='grade_scales'),
    path('grading-systems/<int:system_id>/scales/create/', views.grade_scale_create, name='grade_scale_create'),
    path('grade-scales/<int:pk>/edit/', views.grade_scale_edit, name='grade_scale_edit'),
    path('grade-scales/<int:pk>/delete/', views.grade_scale_delete, name='grade_scale_delete'),

    # Assessment Category CRUD
    path('categories/', views.categories, name='categories'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),

    # Score Entry
    path('scores/', views.score_entry, name='score_entry'),
    path('scores/<int:class_id>/<int:subject_id>/', views.score_entry_form, name='score_entry_form'),
    path('scores/save/', views.score_save, name='score_save'),
    path('scores/audit/<int:student_id>/<int:assignment_id>/', views.score_audit_history, name='score_audit'),

    # Bulk Import
    path('scores/<int:class_id>/<int:subject_id>/import/template/', views.score_import_template, name='import_template'),
    path('scores/<int:class_id>/<int:subject_id>/import/upload/', views.score_import_upload, name='import_upload'),
    path('scores/<int:class_id>/<int:subject_id>/import/confirm/', views.score_import_confirm, name='import_confirm'),

    # Assignments
    path('assignments/<int:subject_id>/', views.assignments, name='assignments'),
    path('assignments/create/', views.assignment_create, name='assignment_create'),
    path('assignments/<int:pk>/delete/', views.assignment_delete, name='assignment_delete'),

    # Grade Calculation
    path('calculate/', views.calculate_grades, name='calculate'),
    path('calculate/<int:class_id>/', views.calculate_class_grades, name='calculate_class'),

    # Grade Locking
    path('lock/<int:term_id>/toggle/', views.toggle_grade_lock, name='toggle_lock'),
    path('lock/status/', views.grade_lock_status, name='lock_status'),

    # Report Cards
    path('reports/', views.report_cards, name='reports'),
    path('reports/<int:student_id>/', views.student_report, name='student_report'),
    path('reports/<int:student_id>/print/', views.report_card_print, name='report_card_print'),
    path('reports/<int:student_id>/remarks/', views.report_remarks_edit, name='report_remarks'),

    # Analytics
    path('analytics/', views.analytics, name='analytics'),
    path('analytics/overview/', views.analytics_overview, name='analytics_overview'),
    path('analytics/class/<int:class_id>/', views.analytics_class_data, name='analytics_class'),
    path('analytics/terms/', views.analytics_term_comparison, name='analytics_terms'),
]
