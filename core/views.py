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
def profile(request):
    """Show profile based on user role."""
    user = request.user

    # Teacher profile
    if getattr(user, 'is_teacher', False):
        from academics.models import Class, ClassSubject
        from students.models import Student
        from teachers.models import Teacher

        teacher = getattr(user, 'teacher_profile', None)
        if not teacher:
            return render(request, 'core/profile_error.html', {
                'error': 'No teacher profile linked to your account.'
            })

        homeroom_classes = Class.objects.filter(
            class_teacher=teacher,
            is_active=True
        ).order_by('name')

        subject_assignments = ClassSubject.objects.filter(
            teacher=teacher
        ).select_related('class_assigned', 'subject').order_by(
            'class_assigned__level_number', 'class_assigned__name'
        )

        classes_taught = list({sa.class_assigned for sa in subject_assignments})
        total_students = Student.objects.filter(
            current_class_id__in=[c.id for c in classes_taught],
            status='active'
        ).count()

        context = {
            'teacher': teacher,
            'homeroom_classes': homeroom_classes,
            'subject_assignments': subject_assignments,
            'workload': {
                'classes_taught': len(classes_taught),
                'subjects_taught': subject_assignments.count(),
                'total_students': total_students,
                'homeroom_classes': homeroom_classes.count(),
            }
        }
        return htmx_render(
            request,
            'teachers/profile.html',
            'teachers/partials/profile_content.html',
            context
        )

    # Admin profile (placeholder)
    if user.is_superuser or getattr(user, 'is_school_admin', False):
        context = {'user': user}
        return htmx_render(
            request,
            'core/profile.html',
            'core/partials/profile_content.html',
            context
        )

    # Default - redirect to index
    return redirect('core:index')


@login_required
def schedule(request):
    """Schedule view - redirects to appropriate schedule based on user role."""
    user = request.user

    # Teacher schedule
    if getattr(user, 'is_teacher', False):
        from django.utils import timezone
        from academics.models import Period, TimetableEntry
        from teachers.models import Teacher

        teacher = getattr(user, 'teacher_profile', None)
        if not teacher:
            messages.warning(request, "No teacher profile linked to your account.")
            return redirect('core:index')

        today = timezone.now()
        weekday = today.isoweekday()

        periods = Period.objects.filter(is_active=True).order_by('order')
        entries = TimetableEntry.objects.filter(
            class_subject__teacher=teacher
        ).select_related(
            'class_subject__class_assigned',
            'class_subject__subject',
            'period'
        ).order_by('weekday', 'period__order')

        schedule_grid = {}
        for period in periods:
            schedule_grid[period.id] = {
                'period': period,
                'days': {1: None, 2: None, 3: None, 4: None, 5: None}
            }

        for entry in entries:
            if entry.period_id in schedule_grid:
                schedule_grid[entry.period_id]['days'][entry.weekday] = entry

        total_periods = entries.count()
        classes_taught = entries.values('class_subject__class_assigned').distinct().count()

        context = {
            'teacher': teacher,
            'periods': periods,
            'schedule_grid': schedule_grid,
            'weekdays': TimetableEntry.Weekday.choices,
            'weekday': weekday,
            'today': today,
            'stats': {
                'total_periods': total_periods,
                'classes_taught': classes_taught,
            }
        }

        return htmx_render(
            request,
            'teachers/schedule.html',
            'teachers/partials/schedule_content.html',
            context
        )

    # Default - redirect to index
    return redirect('core:index')


def teacher_dashboard(request):
    """Dashboard for logged-in teachers."""
    from django.utils import timezone
    from academics.models import Class, ClassSubject, Period, TimetableEntry
    from students.models import Student
    from teachers.models import Teacher

    teacher = getattr(request.user, 'teacher_profile', None)

    if not teacher:
        # Fallback if no teacher profile linked
        context = {
            'error': 'No teacher profile linked to your account.',
        }
        return htmx_render(request, 'core/index.html', 'core/partials/index_content.html', context)

    current_term = Term.get_current()
    today = timezone.now()
    weekday = today.isoweekday()  # 1=Monday, 7=Sunday

    # Homeroom classes (where teacher is class teacher)
    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    ).prefetch_related('students').order_by('name')

    # Subject assignments
    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name'
    )

    # Get unique classes taught
    classes_taught = list({sa.class_assigned for sa in subject_assignments})
    classes_taught.sort(key=lambda c: (c.level_number or 0, c.name))

    # Calculate stats
    total_students = Student.objects.filter(
        current_class_id__in=[c.id for c in classes_taught],
        status='active'
    ).count()

    homeroom_students = Student.objects.filter(
        current_class__in=homeroom_classes,
        status='active'
    ).count()

    # Group assignments by class for easy display
    assignments_by_class = {}
    for assignment in subject_assignments:
        class_name = assignment.class_assigned.name
        if class_name not in assignments_by_class:
            assignments_by_class[class_name] = {
                'class': assignment.class_assigned,
                'subjects': [],
                'student_count': Student.objects.filter(
                    current_class=assignment.class_assigned,
                    status='active'
                ).count()
            }
        assignments_by_class[class_name]['subjects'].append(assignment.subject)

    # Today's schedule
    todays_schedule = []
    if weekday <= 5:  # Only weekdays
        todays_entries = TimetableEntry.objects.filter(
            class_subject__teacher=teacher,
            weekday=weekday
        ).select_related(
            'class_subject__class_assigned',
            'class_subject__subject',
            'period'
        ).order_by('period__start_time')

        for entry in todays_entries:
            todays_schedule.append({
                'period': entry.period,
                'subject': entry.class_subject.subject,
                'class': entry.class_subject.class_assigned,
                'is_current': entry.period.start_time <= today.time() <= entry.period.end_time,
                'is_past': entry.period.end_time < today.time(),
            })

    # Get all periods for reference
    periods = Period.objects.filter(is_active=True).order_by('start_time')

    context = {
        'teacher': teacher,
        'current_term': current_term,
        'homeroom_classes': homeroom_classes,
        'classes_taught': classes_taught,
        'assignments_by_class': assignments_by_class,
        'todays_schedule': todays_schedule,
        'today': today,
        'weekday': weekday,
        'is_weekend': weekday > 5,
        'periods': periods,
        'stats': {
            'classes_count': len(classes_taught),
            'subjects_count': subject_assignments.count(),
            'total_students': total_students,
            'homeroom_students': homeroom_students,
            'periods_today': len(todays_schedule),
        }
    }

    return htmx_render(
        request,
        'teachers/dashboard.html',
        'teachers/partials/dashboard_content.html',
        context
    )


@login_required
def index(request):
    """Dashboard/index view - routes to appropriate dashboard based on user role."""
    from django.db.models import Count, Q
    from django.utils import timezone
    from students.models import Student, Enrollment
    from academics.models import Class, ClassSubject, AttendanceSession, AttendanceRecord
    from teachers.models import Teacher

    # Check if user is a teacher - show teacher dashboard
    if getattr(request.user, 'is_teacher', False):
        return teacher_dashboard(request)

    # Admin/other roles - show admin dashboard
    # Get current academic year and term
    current_year = AcademicYear.get_current()
    current_term = Term.get_current()
    today = timezone.now().date()

    # Get counts
    active_students = Student.objects.filter(status='active')
    student_count = active_students.count()
    male_count = active_students.filter(gender='M').count()
    female_count = active_students.filter(gender='F').count()

    teacher_count = Teacher.objects.filter(status='active').count()
    class_count = Class.objects.filter(is_active=True).count()

    # Get recent students (last 5 added)
    recent_students = Student.objects.select_related('current_class').order_by('-created_at')[:5]

    # Get active enrollments for current year
    active_enrollments = 0
    if current_year:
        active_enrollments = Enrollment.objects.filter(
            academic_year=current_year,
            status='active'
        ).count()

    # Students by level
    students_by_level = {
        'kg': active_students.filter(current_class__level_type='kg').count(),
        'primary': active_students.filter(current_class__level_type='primary').count(),
        'jhs': active_students.filter(current_class__level_type='jhs').count(),
        'shs': active_students.filter(current_class__level_type='shs').count(),
        'unassigned': active_students.filter(current_class__isnull=True).count(),
    }

    # Today's attendance summary
    today_sessions = AttendanceSession.objects.filter(date=today)
    today_attendance = {
        'sessions_taken': today_sessions.count(),
        'total_classes': class_count,
        'present': AttendanceRecord.objects.filter(
            session__date=today, status__in=['P', 'L']
        ).count(),
        'absent': AttendanceRecord.objects.filter(
            session__date=today, status='A'
        ).count(),
    }

    # Classes needing attention (no attendance today)
    classes_without_attendance = Class.objects.filter(
        is_active=True
    ).exclude(
        attendance_sessions__date=today
    ).select_related('class_teacher')[:5]

    # Recent activity (enrollments, new students)
    recent_enrollments = []
    if current_year:
        recent_enrollments = Enrollment.objects.filter(
            academic_year=current_year
        ).select_related(
            'student', 'class_assigned'
        ).order_by('-created_at')[:5]

    context = {
        'student_count': student_count,
        'male_count': male_count,
        'female_count': female_count,
        'teacher_count': teacher_count,
        'class_count': class_count,
        'current_year': current_year,
        'current_term': current_term,
        'active_enrollments': active_enrollments,
        'recent_students': recent_students,
        'students_by_level': students_by_level,
        'today_attendance': today_attendance,
        'classes_without_attendance': classes_without_attendance,
        'recent_enrollments': recent_enrollments,
        'today': today,
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
    """Student view of their own grades and results."""
    from gradebook.models import SubjectTermGrade, TermReport, GradingSystem

    user = request.user
    student = getattr(user, 'student_profile', None)

    if not student:
        return redirect('core:index')

    current_term = Term.get_current()

    # Get all terms this student has results for
    available_terms = Term.objects.filter(
        subject_grades__student=student
    ).distinct().order_by('-academic_year__start_date', '-term_number')

    # Get selected term (default to current)
    selected_term_id = request.GET.get('term')
    if selected_term_id:
        try:
            selected_term = Term.objects.get(pk=selected_term_id)
        except Term.DoesNotExist:
            selected_term = current_term
    else:
        selected_term = current_term

    # Get subject grades for selected term
    subject_grades = []
    term_report = None
    grading_system = None
    grade_scales = []

    if selected_term:
        subject_grades = SubjectTermGrade.objects.filter(
            student=student,
            term=selected_term,
            total_score__isnull=False
        ).select_related('subject').order_by('subject__name')

        term_report = TermReport.objects.filter(
            student=student,
            term=selected_term
        ).first()

        # Get grading system for display
        if student.current_class:
            level_type = student.current_class.level_type
            grading_level = 'SHS' if level_type == 'shs' else 'BASIC'
            grading_system = GradingSystem.objects.filter(
                level=grading_level,
                is_active=True
            ).first()
            if grading_system:
                grade_scales = grading_system.scales.all().order_by('order')

    # Separate core and elective subjects
    core_grades = [g for g in subject_grades if g.subject.is_core]
    elective_grades = [g for g in subject_grades if not g.subject.is_core]

    context = {
        'student': student,
        'current_term': current_term,
        'selected_term': selected_term,
        'available_terms': available_terms,
        'subject_grades': subject_grades,
        'core_grades': core_grades,
        'elective_grades': elective_grades,
        'term_report': term_report,
        'grading_system': grading_system,
        'grade_scales': grade_scales,
    }
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
    """Parent view of their children (wards) with grades summary."""
    from gradebook.models import SubjectTermGrade, TermReport
    from students.models import Student

    user = request.user
    current_term = Term.get_current()

    # Get children linked to this parent
    # Assuming there's a parent_profile or guardian relationship
    # For now, we'll check if the user email matches any student's guardian_email
    wards = Student.objects.filter(
        guardian_email=user.email,
        status='active'
    ).select_related('current_class').order_by('first_name')

    # Get results for each ward
    wards_data = []
    for ward in wards:
        ward_data = {
            'student': ward,
            'term_report': None,
            'subject_count': 0,
        }

        if current_term:
            ward_data['term_report'] = TermReport.objects.filter(
                student=ward,
                term=current_term
            ).first()
            ward_data['subject_count'] = SubjectTermGrade.objects.filter(
                student=ward,
                term=current_term,
                total_score__isnull=False
            ).count()

        wards_data.append(ward_data)

    context = {
        'wards': wards_data,
        'current_term': current_term,
    }
    return htmx_render(request, 'core/parent/my_wards.html', 'core/parent/partials/my_wards_content.html', context)


@login_required
def fee_payments(request):
    context = {}
    return htmx_render(request, 'core/parent/fee_payments.html', 'core/parent/partials/fee_payments_content.html', context)