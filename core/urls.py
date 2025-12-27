from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Dashboard
    path('', views.index, name='index'),

    # School Admin routes
    path('finance/', views.finance_overview, name='finance'),
    path('finance/invoices/', views.invoices, name='invoices'),
    path('finance/payments/', views.payments, name='payments'),
    path('settings/', views.settings, name='settings'),

    # Settings update routes (modal POST handlers)
    path('settings/update/basic/', views.settings_update_basic, name='settings_update_basic'),
    path('settings/update/branding/', views.settings_update_branding, name='settings_update_branding'),
    path('settings/update/contact/', views.settings_update_contact, name='settings_update_contact'),
    path('settings/update/admin/', views.settings_update_admin, name='settings_update_admin'),
    path('settings/update/academic/', views.settings_update_academic, name='settings_update_academic'),

    # Academic Year routes
    path('settings/academic-year/create/', views.academic_year_create, name='academic_year_create'),
    path('settings/academic-year/<int:pk>/edit/', views.academic_year_edit, name='academic_year_edit'),
    path('settings/academic-year/<int:pk>/delete/', views.academic_year_delete, name='academic_year_delete'),
    path('settings/academic-year/<int:pk>/set-current/', views.academic_year_set_current, name='academic_year_set_current'),

    # Term routes
    path('settings/term/create/', views.term_create, name='term_create'),
    path('settings/term/<int:pk>/edit/', views.term_edit, name='term_edit'),
    path('settings/term/<int:pk>/delete/', views.term_delete, name='term_delete'),
    path('settings/term/<int:pk>/set-current/', views.term_set_current, name='term_set_current'),

    # Teacher routes
    path('my-classes/', views.my_classes, name='my_classes'),
    path('attendance/', views.attendance, name='attendance'),
    path('grading/', views.grading, name='grading'),

    # Student routes
    path('my-results/', views.my_results, name='my_results'),
    path('timetable/', views.timetable, name='timetable'),
    path('my-fees/', views.my_fees, name='my_fees'),

    # Parent routes
    path('my-wards/', views.my_wards, name='my_wards'),
    path('fee-payments/', views.fee_payments, name='fee_payments'),
]