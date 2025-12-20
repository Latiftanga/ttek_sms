from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from .models import SchoolSettings
from .forms import (
    SchoolBasicInfoForm,
    SchoolBrandingForm,
    SchoolContactForm,
    SchoolAdminForm,
)


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
    """School settings page with all configuration options."""
    tenant = request.tenant
    school_settings = SchoolSettings.load()

    # Initialize forms with current data
    basic_form = SchoolBasicInfoForm(initial={
        'name': tenant.name,
        'short_name': tenant.short_name,
        'display_name': school_settings.display_name,
        'motto': school_settings.motto,
    })

    branding_form = SchoolBrandingForm(instance=school_settings)

    contact_form = SchoolContactForm(initial={
        'email': tenant.email,
        'phone': tenant.phone,
        'address': tenant.address,
        'digital_address': tenant.digital_address,
        'city': tenant.city,
        'region': tenant.region,
    })

    admin_form = SchoolAdminForm(initial={
        'headmaster_name': tenant.headmaster_name,
        'headmaster_title': tenant.headmaster_title,
    })

    context = {
        'tenant': tenant,
        'school_settings': school_settings,
        'basic_form': basic_form,
        'branding_form': branding_form,
        'contact_form': contact_form,
        'admin_form': admin_form,
    }
    return htmx_render(request, 'core/settings/index.html', 'core/settings/partials/index_content.html', context)


@login_required
def settings_update_basic(request):
    """Update basic school information."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    tenant = request.tenant
    school_settings = SchoolSettings.load()
    form = SchoolBasicInfoForm(request.POST)

    if form.is_valid():
        tenant.name = form.cleaned_data['name']
        tenant.short_name = form.cleaned_data['short_name']
        tenant.save()

        school_settings.display_name = form.cleaned_data['display_name']
        school_settings.motto = form.cleaned_data['motto']
        school_settings.save()

        # For non-HTMX requests, redirect back to settings
        if not request.htmx:
            return redirect('core:settings')

        context = {'tenant': tenant, 'school_settings': school_settings, 'success': True}
    else:
        context = {'tenant': tenant, 'school_settings': school_settings, 'errors': form.errors}

    return render(request, 'core/settings/partials/card_basic.html', context)


@login_required
def settings_update_branding(request):
    """Update branding settings (logo, favicon, colors)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    school_settings = SchoolSettings.load()
    form = SchoolBrandingForm(request.POST, request.FILES, instance=school_settings)

    if form.is_valid():
        form.save()

        # Always redirect/refresh for branding changes since colors affect entire UI
        if request.htmx:
            # Trigger full page refresh so new colors apply globally
            response = HttpResponse(status=200)
            response['HX-Refresh'] = 'true'
            return response

        return redirect('core:settings')

    # On error, return the form with errors
    context = {'school_settings': school_settings, 'errors': form.errors}
    return render(request, 'core/settings/partials/card_branding.html', context)


@login_required
def settings_update_contact(request):
    """Update contact information."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    tenant = request.tenant
    form = SchoolContactForm(request.POST)

    if form.is_valid():
        tenant.email = form.cleaned_data['email']
        tenant.phone = form.cleaned_data['phone']
        tenant.address = form.cleaned_data['address']
        tenant.digital_address = form.cleaned_data['digital_address']
        tenant.city = form.cleaned_data['city']
        tenant.region = form.cleaned_data['region']
        tenant.save()

        if not request.htmx:
            return redirect('core:settings')

        context = {'tenant': tenant, 'success': True}
    else:
        context = {'tenant': tenant, 'errors': form.errors}

    return render(request, 'core/settings/partials/card_contact.html', context)


@login_required
def settings_update_admin(request):
    """Update administration details."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    tenant = request.tenant
    form = SchoolAdminForm(request.POST)

    if form.is_valid():
        tenant.headmaster_name = form.cleaned_data['headmaster_name']
        tenant.headmaster_title = form.cleaned_data['headmaster_title']
        tenant.save()

        if not request.htmx:
            return redirect('core:settings')

        context = {'tenant': tenant, 'success': True}
    else:
        context = {'tenant': tenant, 'errors': form.errors}

    return render(request, 'core/settings/partials/card_admin.html', context)


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
