from django.urls import path
from . import views

app_name = 'gradebook'

urlpatterns = [
    path('', views.index, name='index'),
    path('progress/<int:class_id>/', views.class_progress_detail, name='class_progress_detail'),
    path('settings/', views.gradebook_settings, name='settings'),

    # Grading System CRUD
    path('grading-systems/', views.grading_systems, name='grading_systems'),
    path('grading-systems/create/', views.grading_system_create, name='grading_system_create'),
    path('grading-systems/<uuid:pk>/edit/', views.grading_system_edit, name='grading_system_edit'),
    path('grading-systems/<uuid:pk>/delete/', views.grading_system_delete, name='grading_system_delete'),

    # Grade Scale CRUD
    path('grading-systems/<uuid:system_id>/scales/', views.grade_scales, name='grade_scales'),
    path('grading-systems/<uuid:system_id>/scales/create/', views.grade_scale_create, name='grade_scale_create'),
    path('grade-scales/<uuid:pk>/edit/', views.grade_scale_edit, name='grade_scale_edit'),
    path('grade-scales/<uuid:pk>/delete/', views.grade_scale_delete, name='grade_scale_delete'),

    # Assessment Category CRUD
    path('categories/', views.categories, name='categories'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<uuid:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<uuid:pk>/delete/', views.category_delete, name='category_delete'),

    # Score Entry
    path('scores/', views.score_entry, name='score_entry'),
    path('scores/<int:class_id>/<int:subject_id>/', views.score_entry_form, name='score_entry_form'),
    path('scores/<int:class_id>/<int:subject_id>/student/<int:student_id>/', views.score_entry_student, name='score_entry_student'),
    path('scores/save/', views.score_save, name='score_save'),
    path('scores/audit/<int:student_id>/<uuid:assignment_id>/', views.score_audit_history, name='score_audit'),
    path('scores/<int:class_id>/<int:subject_id>/changes/', views.score_changes_list, name='score_changes'),

    # Bulk Import
    path('scores/<int:class_id>/<int:subject_id>/import/template/', views.score_import_template, name='import_template'),
    path('scores/<int:class_id>/<int:subject_id>/import/upload/', views.score_import_upload, name='import_upload'),
    path('scores/<int:class_id>/<int:subject_id>/import/confirm/', views.score_import_confirm, name='import_confirm'),

    # Assignments
    path('assignments/<int:subject_id>/', views.assignments, name='assignments'),
    path('assignments/create/', views.assignment_create, name='assignment_create'),
    path('assignments/<uuid:pk>/edit/', views.assignment_edit, name='assignment_edit'),
    path('assignments/<uuid:pk>/delete/', views.assignment_delete, name='assignment_delete'),

    # Grade Calculation
    path('calculate/', views.calculate_grades, name='calculate'),
    path('calculate/<int:class_id>/', views.calculate_class_grades, name='calculate_class'),

    # Grade Locking
    path('lock/<uuid:term_id>/toggle/', views.toggle_grade_lock, name='toggle_lock'),
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

    # Bulk Remarks Entry
    path('remarks/bulk/<int:class_id>/', views.bulk_remarks_entry, name='bulk_remarks'),
    path('remarks/save/', views.bulk_remark_save, name='bulk_remark_save'),
    path('remarks/sign/<int:class_id>/', views.bulk_remarks_sign, name='bulk_remarks_sign'),

    # Remark Templates (Admin)
    path('remarks/templates/', views.remark_templates, name='remark_templates'),
    path('remarks/templates/create/', views.remark_template_create, name='remark_template_create'),
    path('remarks/templates/<uuid:pk>/edit/', views.remark_template_edit, name='remark_template_edit'),
    path('remarks/templates/<uuid:pk>/delete/', views.remark_template_delete, name='remark_template_delete'),

    # Report Distribution
    path('reports/distribute/<int:class_id>/', views.report_distribution, name='report_distribution'),
    path('reports/send/<int:student_id>/', views.send_single_report, name='send_single_report'),
    path('reports/send-bulk/<int:class_id>/', views.send_bulk_reports, name='send_bulk_reports'),
    path('reports/<int:student_id>/pdf/', views.download_report_pdf, name='download_report_pdf'),

    # Bulk PDF Export
    path('reports/export/<int:class_id>/', views.export_class_reports, name='export_class_reports'),
    path('reports/export/status/<str:task_id>/', views.check_export_status, name='check_export_status'),
    path('reports/export/download/<path:filename>/', views.download_class_reports, name='download_class_reports'),

    # Transcripts
    path('transcript/<int:student_id>/', views.transcript, name='transcript'),
    path('transcript/<int:student_id>/print/', views.transcript_print, name='transcript_print'),
    path('transcript/<int:student_id>/pdf/', views.download_transcript_pdf, name='download_transcript_pdf'),
]
