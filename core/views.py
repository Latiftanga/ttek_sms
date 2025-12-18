from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse


def htmx_render(request, full_template, partial_template, context=None):
    """
    Render full template for regular requests, partial for HTMX requests.
    Progressive enhancement: works with or without JavaScript.
    """
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)


@login_required
def index(request):
    """Dashboard/index view."""
    context = {
        'student_count': 0,
        'teacher_count': 0,
        'class_count': 0,
        'parent_count': 0,
        'recent_activities': [],
    }
    return htmx_render(request, 'core/index.html', 'core/partials/index_content.html', context)


# School Admin views
@login_required
def students_list(request):
    context = {}
    return htmx_render(request, 'core/students/list.html', 'core/students/partials/list_content.html', context)


@login_required
def teachers_list(request):
    context = {}
    return htmx_render(request, 'core/teachers/list.html', 'core/teachers/partials/list_content.html', context)


@login_required
def finance_overview(request):
    context = {}
    return htmx_render(request, 'core/finance/overview.html', 'core/finance/partials/overview_content.html', context)


@login_required
def invoices(request):
    context = {}
    return htmx_render(request, 'core/finance/invoices.html', 'core/finance/partials/invoices_content.html', context)


@login_required
def payments(request):
    context = {}
    return htmx_render(request, 'core/finance/payments.html', 'core/finance/partials/payments_content.html', context)


@login_required
def communications(request):
    context = {}
    return htmx_render(request, 'core/communications/index.html', 'core/communications/partials/index_content.html', context)


@login_required
def settings(request):
    context = {}
    return htmx_render(request, 'core/settings/index.html', 'core/settings/partials/index_content.html', context)


# Settings HTMX views
@login_required
def settings_tab(request, tab_name):
    return render(request, f'core/settings/partials/tab_{tab_name}.html')


@login_required
def settings_update_basic(request):
    return HttpResponse('')


@login_required
def settings_update_branding(request):
    return HttpResponse('')


@login_required
def settings_update_contact(request):
    return HttpResponse('')


@login_required
def settings_update_admin(request):
    return HttpResponse('')


# Academic Year views
@login_required
def academic_year_create(request):
    return HttpResponse('')


@login_required
def academic_year_edit(request, pk):
    return HttpResponse('')


@login_required
def academic_year_delete(request, pk):
    return HttpResponse('')


@login_required
def academic_year_set_current(request, pk):
    return HttpResponse('')


# Term views
@login_required
def term_create(request):
    return HttpResponse('')


@login_required
def term_edit(request, pk):
    return HttpResponse('')


@login_required
def term_delete(request, pk):
    return HttpResponse('')


@login_required
def term_set_current(request, pk):
    return HttpResponse('')


# Teacher views
@login_required
def my_classes(request):
    context = {}
    return htmx_render(request, 'core/teacher/my_classes.html', 'core/teacher/partials/my_classes_content.html', context)


@login_required
def attendance(request):
    context = {}
    return htmx_render(request, 'core/teacher/attendance.html', 'core/teacher/partials/attendance_content.html', context)


@login_required
def grading(request):
    context = {}
    return htmx_render(request, 'core/teacher/grading.html', 'core/teacher/partials/grading_content.html', context)


# Student views
@login_required
def my_results(request):
    context = {}
    return htmx_render(request, 'core/student/my_results.html', 'core/student/partials/my_results_content.html', context)


@login_required
def timetable(request):
    context = {}
    return htmx_render(request, 'core/student/timetable.html', 'core/student/partials/timetable_content.html', context)


@login_required
def my_fees(request):
    context = {}
    return htmx_render(request, 'core/student/my_fees.html', 'core/student/partials/my_fees_content.html', context)


# Parent views
@login_required
def my_wards(request):
    context = {}
    return htmx_render(request, 'core/parent/my_wards.html', 'core/parent/partials/my_wards_content.html', context)


@login_required
def fee_payments(request):
    context = {}
    return htmx_render(request, 'core/parent/fee_payments.html', 'core/parent/partials/fee_payments_content.html', context)
