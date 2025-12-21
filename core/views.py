from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from .models import SchoolSettings, AcademicYear, Term
from .forms import (
    SchoolBasicInfoForm,
    SchoolBrandingForm,
    SchoolContactForm,
    SchoolAdminForm,
    AcademicSettingsForm,
    AcademicYearForm,
    TermForm,
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
    from students.models import Student, Enrollment
    from academics.models import Class

    # Get current academic year and term
    current_year = AcademicYear.get_current()
    current_term = Term.get_current()

    # Get counts
    student_count = Student.objects.filter(status='active').count()
    class_count = Class.objects.count()

    # Get recent students (last 5 added)
    recent_students = Student.objects.order_by('-created_at')[:5]

    # Get active enrollments for current year
    active_enrollments = 0
    if current_year:
        active_enrollments = Enrollment.objects.filter(
            academic_year=current_year,
            status='active'
        ).count()

    context = {
        'student_count': student_count,
        'teacher_count': 0,  # TODO: Add when teachers app is ready
        'class_count': class_count,
        'parent_count': 0,  # TODO: Add when parents are tracked
        'current_year': current_year,
        'current_term': current_term,
        'active_enrollments': active_enrollments,
        'recent_students': recent_students,
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
    period_type = school_settings.academic_period_type

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

    # Academic settings and data
    academic_settings_form = AcademicSettingsForm(instance=school_settings)
    academic_years = AcademicYear.objects.prefetch_related('terms').all()
    academic_year_form = AcademicYearForm()
    term_form = TermForm(period_type=period_type)

    context = {
        'tenant': tenant,
        'school_settings': school_settings,
        'basic_form': basic_form,
        'branding_form': branding_form,
        'contact_form': contact_form,
        'admin_form': admin_form,
        'academic_settings_form': academic_settings_form,
        'academic_years': academic_years,
        'academic_year_form': academic_year_form,
        'term_form': term_form,
        'period_type': period_type,
        'period_label': school_settings.period_label,
        'period_label_plural': school_settings.period_label_plural,
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


def get_academic_card_context(success=None, errors=None):
    """Helper to get common context for academic card."""
    school_settings = SchoolSettings.load()
    period_type = school_settings.academic_period_type
    return {
        'academic_years': AcademicYear.objects.prefetch_related('terms').all(),
        'academic_year_form': AcademicYearForm(),
        'term_form': TermForm(period_type=period_type),
        'period_type': period_type,
        'period_label': school_settings.period_label,
        'period_label_plural': school_settings.period_label_plural,
        'school_settings': school_settings,
        'success': success,
        'errors': errors,
    }


@login_required
def settings_update_academic(request):
    """Update academic period settings."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    school_settings = SchoolSettings.load()
    form = AcademicSettingsForm(request.POST, instance=school_settings)

    if form.is_valid():
        form.save()
        if not request.htmx:
            return redirect('core:settings')
        return render(request, 'core/settings/partials/card_academic.html',
                      get_academic_card_context(success='Academic settings updated.'))

    return render(request, 'core/settings/partials/card_academic.html',
                  get_academic_card_context(errors=form.errors))


# Academic Year views
@login_required
def academic_year_create(request):
    """Create a new academic year."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = AcademicYearForm(request.POST)
    if form.is_valid():
        form.save()
        # Trigger full page refresh so navbar updates
        if request.htmx:
            response = HttpResponse(status=200)
            response['HX-Refresh'] = 'true'
            return response
        return redirect('core:settings')

    # Return form with errors - use 422 so modal doesn't close
    context = {
        'form': form,
        'is_create': True,
    }
    response = render(request, 'core/settings/partials/modal_academic_year_form.html', context)
    response.status_code = 422
    response['HX-Retarget'] = '#modal-academic-year-form'
    response['HX-Reswap'] = 'outerHTML'
    return response


@login_required
def academic_year_edit(request, pk):
    """Edit an academic year."""
    academic_year = get_object_or_404(AcademicYear, pk=pk)

    if request.method == 'GET':
        form = AcademicYearForm(instance=academic_year)
        return render(request, 'core/settings/partials/modal_academic_year_form.html', {
            'form': form,
            'is_create': False,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = AcademicYearForm(request.POST, instance=academic_year)
    if form.is_valid():
        form.save()
        if not request.htmx:
            return redirect('core:settings')
        # Trigger full page refresh so navbar updates
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response

    # Return form with errors - use 422 so modal doesn't close
    context = {
        'form': form,
        'is_create': False,
    }
    response = render(request, 'core/settings/partials/modal_academic_year_form.html', context)
    response.status_code = 422
    response['HX-Retarget'] = '#modal-academic-year-form'
    response['HX-Reswap'] = 'outerHTML'
    return response


@login_required
def academic_year_delete(request, pk):
    """Delete an academic year."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    academic_year = get_object_or_404(AcademicYear, pk=pk)
    academic_year.delete()

    if not request.htmx:
        return redirect('core:settings')

    return render(request, 'core/settings/partials/card_academic.html',
                  get_academic_card_context(success='Academic year deleted successfully.'))


@login_required
def academic_year_set_current(request, pk):
    """Set an academic year as current."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    academic_year = get_object_or_404(AcademicYear, pk=pk)
    academic_year.is_current = True
    academic_year.save()

    # Trigger full page refresh so navbar updates
    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('core:settings')


# Term views
@login_required
def term_create(request):
    """Create a new term/semester."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    school_settings = SchoolSettings.load()
    period_type = school_settings.academic_period_type

    form = TermForm(request.POST, period_type=period_type)
    if form.is_valid():
        form.save()
        # Trigger full page refresh so navbar updates
        if request.htmx:
            response = HttpResponse(status=200)
            response['HX-Refresh'] = 'true'
            return response
        return redirect('core:settings')

    # Return form with errors - use 422 so modal doesn't close
    context = {
        'form': form,
        'is_create': True,
        'period_label': school_settings.period_label,
    }
    response = render(request, 'core/settings/partials/modal_term_form.html', context)
    response.status_code = 422
    response['HX-Retarget'] = '#modal-term-form'
    response['HX-Reswap'] = 'outerHTML'
    return response


@login_required
def term_edit(request, pk):
    """Edit a term/semester."""
    term = get_object_or_404(Term, pk=pk)
    school_settings = SchoolSettings.load()
    period_type = school_settings.academic_period_type
    period_label = school_settings.period_label

    if request.method == 'GET':
        form = TermForm(instance=term, period_type=period_type)
        return render(request, 'core/settings/partials/modal_term_form.html', {
            'form': form,
            'is_create': False,
            'period_label': period_label,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = TermForm(request.POST, instance=term, period_type=period_type)
    if form.is_valid():
        form.save()
        if not request.htmx:
            return redirect('core:settings')
        # Trigger full page refresh so navbar updates
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response

    # Return form with errors - use 422 so modal doesn't close
    context = {
        'form': form,
        'is_create': False,
        'period_label': period_label,
    }
    response = render(request, 'core/settings/partials/modal_term_form.html', context)
    response.status_code = 422
    response['HX-Retarget'] = '#modal-term-form'
    response['HX-Reswap'] = 'outerHTML'
    return response


@login_required
def term_delete(request, pk):
    """Delete a term/semester."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    term = get_object_or_404(Term, pk=pk)
    term.delete()

    if not request.htmx:
        return redirect('core:settings')

    school_settings = SchoolSettings.load()
    return render(request, 'core/settings/partials/card_academic.html',
                  get_academic_card_context(success=f'{school_settings.period_label} deleted successfully.'))


@login_required
def term_set_current(request, pk):
    """Set a term/semester as current."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    term = get_object_or_404(Term, pk=pk)
    term.is_current = True
    term.save()

    # Trigger full page refresh so navbar updates
    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('core:settings')


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
