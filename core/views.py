from functools import wraps
from decimal import Decimal
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, FileResponse, JsonResponse
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET
from django.db import connection
from .models import SchoolSettings, AcademicYear, Term
from .forms import (
    SchoolBasicInfoForm,
    SchoolBrandingForm,
    SchoolContactForm,
    SchoolAdminForm,
    AcademicSettingsForm,
    AcademicYearForm,
    TermForm,
    SMSSettingsForm,
)
from finance.models import PaymentGateway, PaymentGatewayConfig


# ============================================
# PWA / Offline Support Views
# ============================================

def offline(request):
    """Offline fallback page for service worker."""
    return render(request, 'core/offline.html')


@require_GET
@cache_control(max_age=0, no_cache=True, no_store=True, must_revalidate=True)
def service_worker(request):
    """Serve service worker from root scope."""
    import os
    sw_path = os.path.join(settings.BASE_DIR, 'core', 'static', 'core', 'sw.js')
    return FileResponse(
        open(sw_path, 'rb'),
        content_type='application/javascript',
        headers={'Service-Worker-Allowed': '/'}
    )


@require_GET
def manifest(request):
    """Generate PWA manifest with school-specific branding."""
    # Get school settings for current tenant
    try:
        school = SchoolSettings.objects.first()
        school_name = school.display_name if school else connection.tenant.name
        short_name = school.short_name if school and school.short_name else school_name[:12]
        theme_color = school.primary_color if school and school.primary_color else '#570df8'
        background_color = '#f2f2f2'

        # Build icon URLs
        icons = []
        if school and school.logo:
            icons.append({
                'src': school.logo.url,
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any maskable'
            })
            icons.append({
                'src': school.logo.url,
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any maskable'
            })
        else:
            # Default icons if no school logo
            icons = [
                {
                    'src': '/static/core/icons/icon-192.svg',
                    'sizes': '192x192',
                    'type': 'image/svg+xml',
                    'purpose': 'any'
                },
                {
                    'src': '/static/core/icons/icon-512.svg',
                    'sizes': '512x512',
                    'type': 'image/svg+xml',
                    'purpose': 'any'
                }
            ]
    except Exception:
        school_name = 'School Management'
        short_name = 'School'
        theme_color = '#570df8'
        background_color = '#f2f2f2'
        icons = [
            {
                'src': '/static/core/icons/icon-192.svg',
                'sizes': '192x192',
                'type': 'image/svg+xml',
                'purpose': 'any'
            },
            {
                'src': '/static/core/icons/icon-512.svg',
                'sizes': '512x512',
                'type': 'image/svg+xml',
                'purpose': 'any'
            }
        ]

    manifest_data = {
        'name': school_name,
        'short_name': short_name,
        'description': f'{school_name} - School Management System',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait-primary',
        'theme_color': theme_color,
        'background_color': background_color,
        'icons': icons,
        'categories': ['education', 'productivity'],
        'shortcuts': [
            {
                'name': 'Dashboard',
                'short_name': 'Home',
                'url': '/',
                'icons': [{'src': '/static/core/icons/home.svg', 'sizes': '96x96', 'type': 'image/svg+xml'}]
            },
            {
                'name': 'Take Attendance',
                'short_name': 'Attendance',
                'url': '/my-attendance/',
                'icons': [{'src': '/static/core/icons/attendance.svg', 'sizes': '96x96', 'type': 'image/svg+xml'}]
            }
        ]
    }

    return JsonResponse(manifest_data, content_type='application/manifest+json')


def is_school_admin(user):
    """Check if user is a school admin or superuser."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or getattr(user, 'is_school_admin', False)


def admin_required(view_func):
    """Decorator to require school admin or superuser access."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not is_school_admin(request.user):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:index')
        return view_func(request, *args, **kwargs)
    return wrapper



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
@admin_required
def students_list(request):
    context = {}
    return htmx_render(request, 'core/students/list.html', 'core/students/partials/list_content.html', context)


@admin_required
def teachers_list(request):
    context = {}
    return htmx_render(request, 'core/teachers/list.html', 'core/teachers/partials/list_content.html', context)


@admin_required
def finance_overview(request):
    context = {}
    return htmx_render(request, 'core/finance/overview.html', 'core/finance/partials/overview_content.html', context)


@admin_required
def invoices(request):
    context = {}
    return htmx_render(request, 'core/finance/invoices.html', 'core/finance/partials/invoices_content.html', context)


@admin_required
def payments(request):
    context = {}
    return htmx_render(request, 'core/finance/payments.html', 'core/finance/partials/payments_content.html', context)


@admin_required
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

    # SMS settings - derive sender ID from school name
    derived_sender_id = ''
    if school_settings.display_name:
        derived_sender_id = ''.join(c for c in school_settings.display_name if c.isalnum())[:11]
    elif tenant.name:
        derived_sender_id = ''.join(c for c in tenant.name if c.isalnum())[:11]
    derived_sender_id = derived_sender_id or 'SchoolSMS'

    # Payment gateway settings
    available_gateways = PaymentGateway.objects.filter(is_active=True)
    gateway_configs = PaymentGatewayConfig.objects.select_related('gateway').all()
    primary_gateway = gateway_configs.filter(is_primary=True, is_active=True).first()

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
        'derived_sender_id': derived_sender_id,
        # Payment gateway context
        'available_gateways': available_gateways,
        'gateway_configs': gateway_configs,
        'primary_gateway': primary_gateway,
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


@login_required
def settings_update_sms(request):
    """Update SMS configuration settings."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    school_settings = SchoolSettings.load()

    # Handle checkbox - if not in POST, it's unchecked
    sms_enabled = request.POST.get('sms_enabled') == 'on'
    sms_backend = request.POST.get('sms_backend', 'console')
    sms_api_key = request.POST.get('sms_api_key', '').strip()
    sms_sender_id = request.POST.get('sms_sender_id', '').strip()

    # Update settings
    school_settings.sms_enabled = sms_enabled
    school_settings.sms_backend = sms_backend
    school_settings.sms_sender_id = sms_sender_id

    # Only update API key if a new one was provided (not placeholder)
    if sms_api_key and not sms_api_key.startswith('••'):
        school_settings.sms_api_key = sms_api_key

    school_settings.save()

    if not request.htmx:
        return redirect('core:settings')

    context = {
        'school_settings': school_settings,
        'success': 'SMS settings updated successfully',
    }
    return render(request, 'core/settings/partials/card_sms.html', context)


@login_required
def settings_update_email(request):
    """Update email configuration settings."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    school_settings = SchoolSettings.load()

    # Update email settings
    school_settings.email_enabled = request.POST.get('email_enabled') == 'on'
    school_settings.email_backend = request.POST.get('email_backend', 'console')
    school_settings.email_host = request.POST.get('email_host', '').strip()

    # Handle port with default
    try:
        school_settings.email_port = int(request.POST.get('email_port', 587))
    except (ValueError, TypeError):
        school_settings.email_port = 587

    school_settings.email_use_tls = request.POST.get('email_use_tls') == 'on'
    school_settings.email_use_ssl = request.POST.get('email_use_ssl') == 'on'
    school_settings.email_host_user = request.POST.get('email_host_user', '').strip()
    school_settings.email_from_address = request.POST.get('email_from_address', '').strip()
    school_settings.email_from_name = request.POST.get('email_from_name', '').strip()

    # Only update password if a new one was provided (not placeholder)
    password = request.POST.get('email_host_password', '').strip()
    if password and not password.startswith('••'):
        school_settings.email_host_password = password

    school_settings.save()

    if not request.htmx:
        return redirect('core:settings')

    context = {
        'school_settings': school_settings,
        'success': 'Email settings updated successfully',
    }
    return render(request, 'core/settings/partials/card_email.html', context)


@login_required
def settings_test_email(request):
    """Send a test email to verify email configuration."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    from django.core.mail import send_mail

    recipient = request.POST.get('test_email', '').strip()
    if not recipient:
        recipient = request.user.email

    if not recipient:
        return HttpResponse(
            '<div class="alert alert-error text-sm py-2">'
            '<i class="fa-solid fa-circle-xmark"></i> No recipient email address'
            '</div>'
        )

    school_settings = SchoolSettings.load()
    from_email = school_settings.email_from_address or None

    try:
        send_mail(
            subject='Test Email - School Management System',
            message=(
                'This is a test email to verify your email configuration is working correctly.\n\n'
                'If you received this email, your email settings are configured properly.'
            ),
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return HttpResponse(
            '<div class="alert alert-success text-sm py-2">'
            f'<i class="fa-solid fa-circle-check"></i> Test email sent to {recipient}'
            '</div>'
        )
    except Exception as e:
        error_msg = str(e)
        # Truncate long error messages
        if len(error_msg) > 100:
            error_msg = error_msg[:100] + '...'
        return HttpResponse(
            f'<div class="alert alert-error text-sm py-2">'
            f'<i class="fa-solid fa-circle-xmark"></i> Failed: {error_msg}'
            f'</div>'
        )


@login_required
def settings_update_payment(request):
    """Update payment gateway configuration."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    gateway_id = request.POST.get('gateway_id')
    if not gateway_id:
        return HttpResponse("Gateway ID required", status=400)

    gateway = get_object_or_404(PaymentGateway, pk=gateway_id)

    # Get or create the configuration for this gateway
    config, created = PaymentGatewayConfig.objects.get_or_create(
        gateway=gateway,
        defaults={'secret_key': '', 'configured_by': request.user}
    )

    # Update credentials (only if new values provided)
    secret_key = request.POST.get('secret_key', '').strip()
    public_key = request.POST.get('public_key', '').strip()
    webhook_secret = request.POST.get('webhook_secret', '').strip()
    merchant_id = request.POST.get('merchant_id', '').strip()
    encryption_key = request.POST.get('encryption_key', '').strip()
    merchant_account = request.POST.get('merchant_account', '').strip()

    # Only update if new value provided (not placeholder)
    if secret_key and not secret_key.startswith('••'):
        config.secret_key = secret_key
    if public_key and not public_key.startswith('••'):
        config.public_key = public_key
    if webhook_secret and not webhook_secret.startswith('••'):
        config.webhook_secret = webhook_secret
    if merchant_id:
        config.merchant_id = merchant_id
    if encryption_key and not encryption_key.startswith('••'):
        config.encryption_key = encryption_key
    if merchant_account:
        config.merchant_account = merchant_account

    # Update settings
    config.is_active = request.POST.get('is_active') == 'on'
    config.is_test_mode = request.POST.get('is_test_mode') == 'on'
    config.is_primary = request.POST.get('is_primary') == 'on'

    # Update transaction charges
    charge_percentage = request.POST.get('charge_percentage', '').strip()
    charge_fixed = request.POST.get('charge_fixed', '').strip()
    who_bears_charge = request.POST.get('who_bears_charge', 'SCHOOL')

    if charge_percentage:
        config.transaction_charge_percentage = Decimal(charge_percentage)
    if charge_fixed:
        config.transaction_charge_fixed = Decimal(charge_fixed)
    config.who_bears_charge = who_bears_charge

    config.configured_by = request.user
    config.verification_status = 'PENDING'  # Reset verification status
    config.save()

    if not request.htmx:
        return redirect('core:settings')

    # Get updated context for the card
    gateway_configs = PaymentGatewayConfig.objects.select_related('gateway').all()
    primary_gateway = gateway_configs.filter(is_primary=True, is_active=True).first()

    context = {
        'gateway_configs': gateway_configs,
        'primary_gateway': primary_gateway,
        'payment_success': f'{gateway.display_name} configured successfully',
    }
    return render(request, 'core/settings/partials/card_payment.html', context)


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
    """Teacher view of their assigned classes."""
    from academics.models import Class, ClassSubject
    from students.models import Student
    from teachers.models import Teacher

    user = request.user

    # Verify user is a teacher
    if not getattr(user, 'is_teacher', False):
        messages.error(request, 'This page is only accessible to teachers.')
        return redirect('core:index')

    teacher = getattr(user, 'teacher_profile', None)
    if not teacher:
        messages.error(request, 'No teacher profile linked to your account.')
        return redirect('core:index')

    # Get current term
    current_term = Term.get_current()

    # Get homeroom classes (where teacher is class teacher)
    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    ).prefetch_related('students').order_by('level_number', 'name')

    # Get subject assignments
    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name', 'subject__name'
    )

    # Build class data with student counts
    classes_data = []
    seen_classes = set()

    # Add homeroom classes
    for cls in homeroom_classes:
        student_count = cls.students.filter(status='active').count()
        # Get all subjects offered by this class
        class_subjects = ClassSubject.objects.filter(
            class_assigned=cls
        ).select_related('subject', 'teacher').order_by('-subject__is_core', 'subject__name')

        classes_data.append({
            'class': cls,
            'is_homeroom': True,
            'subjects': [],  # Subjects this teacher teaches
            'class_subjects': list(class_subjects),  # All subjects offered
            'student_count': student_count,
        })
        seen_classes.add(cls.id)

    # Add classes from subject assignments
    for assignment in subject_assignments:
        cls = assignment.class_assigned
        if cls.id not in seen_classes:
            student_count = cls.students.filter(status='active').count()
            # Get all subjects offered by this class
            class_subjects = ClassSubject.objects.filter(
                class_assigned=cls
            ).select_related('subject', 'teacher').order_by('-subject__is_core', 'subject__name')

            classes_data.append({
                'class': cls,
                'is_homeroom': False,
                'subjects': [assignment.subject],  # Subjects this teacher teaches
                'class_subjects': list(class_subjects),  # All subjects offered
                'student_count': student_count,
            })
            seen_classes.add(cls.id)
        else:
            # Add subject to existing class entry
            for data in classes_data:
                if data['class'].id == cls.id:
                    if assignment.subject not in data['subjects']:
                        data['subjects'].append(assignment.subject)
                    break

    # Separate homeroom and subject-only classes
    homeroom_classes_list = [c for c in classes_data if c['is_homeroom']]
    subject_classes_list = [c for c in classes_data if not c['is_homeroom']]

    # Calculate totals
    total_students = sum(c['student_count'] for c in classes_data)

    # Get all unique subjects teacher teaches
    all_subjects = list({subj for c in classes_data for subj in c['subjects']})
    all_subjects.sort(key=lambda s: s.name)

    context = {
        'teacher': teacher,
        'current_term': current_term,
        'classes_data': classes_data,
        'homeroom_classes': homeroom_classes_list,
        'subject_classes': subject_classes_list,
        'total_classes': len(classes_data),
        'homeroom_count': len(homeroom_classes_list),
        'total_students': total_students,
        'total_subjects': len(all_subjects),
        'all_subjects': all_subjects,
    }

    return htmx_render(request, 'core/teacher/my_classes.html', 'core/teacher/partials/my_classes_content.html', context)


@login_required
def my_timetable(request):
    """Teacher's weekly timetable showing all their scheduled classes."""
    from academics.models import TimetableEntry, Period

    user = request.user

    # Verify user is a teacher
    if not getattr(user, 'is_teacher', False):
        messages.error(request, 'This page is only accessible to teachers.')
        return redirect('core:index')

    teacher = getattr(user, 'teacher_profile', None)
    if not teacher:
        messages.error(request, 'No teacher profile linked to your account.')
        return redirect('core:index')

    # Get all periods ordered by start time
    periods = Period.objects.filter(is_active=True).order_by('order', 'start_time')

    # Get all timetable entries for this teacher
    entries = TimetableEntry.objects.filter(
        class_subject__teacher=teacher
    ).select_related(
        'class_subject__class_assigned',
        'class_subject__subject',
        'period'
    ).order_by('weekday', 'period__order')

    # Build timetable grid: {weekday: {period_id: entry}}
    timetable = {day: {} for day in range(1, 6)}  # Monday=1 to Friday=5
    for entry in entries:
        timetable[entry.weekday][entry.period_id] = entry

    # Weekday labels
    weekdays = [
        (1, 'Monday'),
        (2, 'Tuesday'),
        (3, 'Wednesday'),
        (4, 'Thursday'),
        (5, 'Friday'),
    ]

    # Calculate stats
    total_lessons = entries.count()
    classes_taught = len(set(e.class_subject.class_assigned_id for e in entries))
    subjects_taught = len(set(e.class_subject.subject_id for e in entries))

    context = {
        'periods': periods,
        'timetable': timetable,
        'weekdays': weekdays,
        'entries': entries,
        'total_lessons': total_lessons,
        'classes_taught': classes_taught,
        'subjects_taught': subjects_taught,
    }

    return htmx_render(request, 'core/teacher/my_timetable.html', 'core/teacher/partials/my_timetable_content.html', context)


@login_required
def my_attendance(request):
    """Teacher's attendance dashboard - view and take attendance for assigned classes."""
    from django.db.models import Count, Q
    from datetime import timedelta
    from academics.models import Class, ClassSubject, AttendanceSession, AttendanceRecord
    from teachers.models import Teacher

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('core:index')

    teacher = user.teacher_profile

    # Get teacher's classes (homeroom + assigned)
    homeroom_classes = Class.objects.filter(class_teacher=teacher, is_active=True)
    assigned_class_ids = ClassSubject.objects.filter(teacher=teacher).values_list('class_assigned_id', flat=True)
    all_class_ids = set(homeroom_classes.values_list('id', flat=True)) | set(assigned_class_ids)
    classes = Class.objects.filter(id__in=all_class_ids, is_active=True).order_by('level_number', 'name')

    # Get filter parameters
    class_filter = request.GET.get('class', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Default date range: last 30 days
    today = timezone.now().date()
    if not date_from:
        date_from = (today - timedelta(days=30)).isoformat()
    if not date_to:
        date_to = today.isoformat()

    # Get attendance records for teacher's classes
    records = AttendanceRecord.objects.filter(
        session__class_assigned_id__in=all_class_ids
    ).select_related('session', 'student', 'session__class_assigned')

    sessions = AttendanceSession.objects.filter(
        class_assigned_id__in=all_class_ids
    ).select_related('class_assigned')

    # Apply date filter
    if date_from:
        sessions = sessions.filter(date__gte=date_from)
        records = records.filter(session__date__gte=date_from)
    if date_to:
        sessions = sessions.filter(date__lte=date_to)
        records = records.filter(session__date__lte=date_to)

    # Apply class filter
    if class_filter:
        sessions = sessions.filter(class_assigned_id=class_filter)
        records = records.filter(session__class_assigned_id=class_filter)

    # Calculate summary stats
    total_sessions = sessions.count()
    total_records = records.count()
    present_count = records.filter(status__in=['P', 'L']).count()
    absent_count = records.filter(status='A').count()
    late_count = records.filter(status='L').count()

    attendance_rate = 0
    if total_records > 0:
        attendance_rate = round((present_count / total_records) * 100, 1)

    # Summary by class
    class_summary = []
    for cls in classes:
        cls_records = records.filter(session__class_assigned=cls)
        cls_total = cls_records.count()
        is_homeroom = cls in homeroom_classes

        # Check if attendance taken today
        has_today = AttendanceSession.objects.filter(
            class_assigned=cls,
            date=today
        ).exists()

        if cls_total > 0:
            cls_present = cls_records.filter(status__in=['P', 'L']).count()
            cls_absent = cls_records.filter(status='A').count()
            cls_rate = round((cls_present / cls_total) * 100, 1)
        else:
            cls_present = 0
            cls_absent = 0
            cls_rate = 0

        class_summary.append({
            'class': cls,
            'total': cls_total,
            'present': cls_present,
            'absent': cls_absent,
            'rate': cls_rate,
            'is_homeroom': is_homeroom,
            'has_today': has_today,
            'student_count': cls.students.filter(status='active').count(),
        })

    # Recent sessions (last 10)
    recent_sessions = sessions.order_by('-date')[:10]
    recent_data = []
    for session in recent_sessions:
        session_records = session.records.all()
        s_total = session_records.count()
        s_present = session_records.filter(status__in=['P', 'L']).count()
        s_absent = session_records.filter(status='A').count()
        recent_data.append({
            'session': session,
            'total': s_total,
            'present': s_present,
            'absent': s_absent,
            'rate': round((s_present / s_total) * 100, 1) if s_total > 0 else 0,
        })

    context = {
        'teacher': teacher,
        'classes': classes,
        'class_filter': class_filter,
        'date_from': date_from,
        'date_to': date_to,
        'today': today,
        'stats': {
            'total_sessions': total_sessions,
            'total_records': total_records,
            'present': present_count,
            'absent': absent_count,
            'late': late_count,
            'rate': attendance_rate,
        },
        'class_summary': class_summary,
        'recent_data': recent_data,
    }

    return htmx_render(request, 'core/teacher/my_attendance.html', 'core/teacher/partials/my_attendance_content.html', context)


@login_required
def take_attendance(request, class_id):
    """Teacher takes attendance for a specific class."""
    from academics.models import Class, ClassSubject, AttendanceSession, AttendanceRecord
    from students.models import Student
    from teachers.models import Teacher

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        messages.error(request, 'You do not have permission to take attendance.')
        return redirect('core:index')

    teacher = user.teacher_profile
    class_obj = get_object_or_404(Class, pk=class_id)

    # Check permission: must be class teacher or assigned to teach this class
    is_class_teacher = class_obj.class_teacher == teacher
    is_subject_teacher = ClassSubject.objects.filter(
        class_assigned=class_obj,
        teacher=teacher
    ).exists()

    if not is_class_teacher and not is_subject_teacher:
        messages.error(request, 'You are not assigned to this class.')
        return redirect('core:my_attendance')

    target_date = timezone.now().date()

    # Check if session exists
    session, created = AttendanceSession.objects.get_or_create(
        class_assigned=class_obj,
        date=target_date
    )

    if request.method == 'POST':
        students = Student.objects.filter(current_class=class_obj, status='active')

        for student in students:
            status_key = f"status_{student.id}"
            new_status = request.POST.get(status_key, AttendanceRecord.Status.PRESENT)

            AttendanceRecord.objects.update_or_create(
                session=session,
                student=student,
                defaults={'status': new_status}
            )

        messages.success(request, f'Attendance saved for {class_obj.name}.')

        if request.htmx:
            response = HttpResponse(status=204)
            response['HX-Redirect'] = reverse('core:my_attendance')
            return response

        return redirect('core:my_attendance')

    # GET: Prepare form data
    students = Student.objects.filter(current_class=class_obj, status='active').order_by('first_name', 'last_name')
    records = {r.student_id: r.status for r in session.records.all()}

    student_list = []
    for student in students:
        student_list.append({
            'obj': student,
            'status': records.get(student.id, 'P')
        })

    context = {
        'class': class_obj,
        'session': session,
        'student_list': student_list,
        'date': target_date,
        'is_homeroom': class_obj.class_teacher == teacher,
    }

    return htmx_render(request, 'core/teacher/take_attendance.html', 'core/teacher/partials/take_attendance_content.html', context)


@login_required
def my_grading(request):
    """Teacher's grading dashboard - view and enter scores for assigned classes."""
    from academics.models import Class, ClassSubject, Subject
    from gradebook.models import Assignment, Score, AssessmentCategory
    from teachers.models import Teacher

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('core:index')

    teacher = user.teacher_profile
    current_term = Term.get_current()

    # Get teacher's class-subject assignments (only active classes)
    assignments = ClassSubject.objects.filter(
        teacher=teacher,
        class_assigned__is_active=True
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name', 'subject__name'
    )

    # Build class data with progress info
    class_data = []
    for assignment in assignments:
        cls = assignment.class_assigned
        subject = assignment.subject

        # Count students
        student_count = cls.students.filter(status='active').count()

        # Count assignments and scores entered
        if current_term:
            term_assignments = Assignment.objects.filter(
                subject=subject,
                term=current_term
            ).count()

            if term_assignments > 0 and student_count > 0:
                total_possible = term_assignments * student_count
                scores_entered = Score.objects.filter(
                    assignment__subject=subject,
                    assignment__term=current_term,
                    student__current_class=cls
                ).count()
                progress = round((scores_entered / total_possible) * 100) if total_possible > 0 else 0
            else:
                scores_entered = 0
                progress = 0
        else:
            term_assignments = 0
            scores_entered = 0
            progress = 0

        class_data.append({
            'class': cls,
            'subject': subject,
            'student_count': student_count,
            'assignments': term_assignments,
            'scores_entered': scores_entered,
            'progress': progress,
        })

    # Get categories for reference
    categories = AssessmentCategory.objects.filter(is_active=True).order_by('order')

    context = {
        'teacher': teacher,
        'current_term': current_term,
        'class_data': class_data,
        'categories': categories,
        'total_classes': len(class_data),
    }

    return htmx_render(request, 'core/teacher/my_grading.html', 'core/teacher/partials/my_grading_content.html', context)


@login_required
def enter_scores(request, class_id, subject_id):
    """Teacher enters scores for a specific class/subject."""
    from academics.models import Class, ClassSubject, Subject
    from gradebook.models import Assignment, Score, AssessmentCategory
    from students.models import Student
    from teachers.models import Teacher
    from collections import defaultdict

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        messages.error(request, 'You do not have permission to enter scores.')
        return redirect('core:index')

    teacher = user.teacher_profile
    class_obj = get_object_or_404(Class, pk=class_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    current_term = Term.get_current()

    # Check permission: must be assigned to teach this subject in this class
    is_assigned = ClassSubject.objects.filter(
        class_assigned=class_obj,
        subject=subject,
        teacher=teacher
    ).exists()

    if not is_assigned:
        messages.error(request, 'You are not assigned to teach this subject in this class.')
        return redirect('core:my_grading')

    # Check if grades are locked
    grades_locked = current_term.grades_locked if current_term else True

    # Get students
    students = list(Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('last_name', 'first_name'))

    # Get assignments for this subject/term
    assignments_list = list(Assignment.objects.filter(
        subject=subject,
        term=current_term
    ).select_related('assessment_category').order_by('assessment_category__order', 'name'))

    # Get existing scores - build nested dict for O(1) lookup
    scores_dict = defaultdict(dict)
    if students and assignments_list:
        student_ids = [s.id for s in students]
        assignment_ids = [a.id for a in assignments_list]
        for score in Score.objects.filter(
            student_id__in=student_ids,
            assignment_id__in=assignment_ids
        ).only('student_id', 'assignment_id', 'points'):
            scores_dict[score.student_id][score.assignment_id] = score.points

    # Get categories
    categories = list(AssessmentCategory.objects.filter(is_active=True).order_by('order'))

    context = {
        'class_obj': class_obj,
        'subject': subject,
        'current_term': current_term,
        'students': students,
        'assignments': assignments_list,
        'categories': categories,
        'scores_dict': dict(scores_dict),
        'grades_locked': grades_locked,
        'can_edit': not grades_locked,
    }

    return htmx_render(request, 'core/teacher/enter_scores.html', 'core/teacher/partials/enter_scores_content.html', context)


@login_required
def export_scores(request, class_id, subject_id):
    """Export scores for a class/subject as CSV or Excel."""
    import csv
    from io import BytesIO
    from django.http import HttpResponse
    from academics.models import Class, ClassSubject, Subject
    from gradebook.models import Assignment, Score
    from students.models import Student
    from teachers.models import Teacher

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        messages.error(request, 'You do not have permission to export scores.')
        return redirect('core:index')

    teacher = user.teacher_profile
    class_obj = get_object_or_404(Class, pk=class_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    current_term = Term.get_current()

    # Check permission
    is_assigned = ClassSubject.objects.filter(
        class_assigned=class_obj,
        subject=subject,
        teacher=teacher
    ).exists()

    if not is_assigned:
        messages.error(request, 'You are not assigned to teach this subject.')
        return redirect('core:my_grading')

    # Get students
    students = Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('last_name', 'first_name')

    # Get assignments
    assignments = Assignment.objects.filter(
        subject=subject,
        term=current_term
    ).select_related('assessment_category').order_by('assessment_category__order', 'name')

    # Get existing scores
    scores_dict = {}
    if students and assignments:
        student_ids = [s.id for s in students]
        assignment_ids = [a.id for a in assignments]
        for score in Score.objects.filter(
            student_id__in=student_ids,
            assignment_id__in=assignment_ids
        ):
            if score.student_id not in scores_dict:
                scores_dict[score.student_id] = {}
            scores_dict[score.student_id][score.assignment_id] = score.points

    # Check format
    export_format = request.GET.get('format', 'csv')

    # Build headers
    headers = ['Admission No', 'Student Name']
    for assignment in assignments:
        headers.append(f"{assignment.name} ({assignment.assessment_category.short_name}) /{assignment.points_possible}")

    # Build rows
    rows = []
    for student in students:
        row = [student.admission_number, student.full_name]
        student_scores = scores_dict.get(student.id, {})
        for assignment in assignments:
            score = student_scores.get(assignment.id, '')
            row.append(score if score != '' else '')
        rows.append(row)

    filename = f"{class_obj.name}_{subject.name}_{current_term.name}_scores".replace(' ', '_')

    if export_format == 'xlsx':
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Scores"

            # Header style
            header_font = Font(bold=True)
            header_fill = PatternFill(start_color="DDEEFF", end_color="DDEEFF", fill_type="solid")

            # Write headers
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = header_font
                cell.fill = header_fill

            # Write data
            for row_idx, row in enumerate(rows, 2):
                for col_idx, value in enumerate(row, 1):
                    ws.cell(row=row_idx, column=col_idx, value=value)

            # Adjust column widths
            ws.column_dimensions['A'].width = 15
            ws.column_dimensions['B'].width = 25
            for col_idx in range(3, len(headers) + 1):
                ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = 12

            # Create response
            output = BytesIO()
            wb.save(output)
            output.seek(0)

            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
            return response

        except ImportError:
            export_format = 'csv'

    # CSV export
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'

    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)

    return response


@login_required
def import_scores(request, class_id, subject_id):
    """Import scores from CSV/Excel file - preview step."""
    import csv
    import json
    from io import TextIOWrapper
    from django.http import HttpResponse
    from academics.models import Class, ClassSubject, Subject
    from gradebook.models import Assignment, Score
    from students.models import Student
    from teachers.models import Teacher

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        return HttpResponse('<div class="alert alert-error">Permission denied.</div>')

    teacher = user.teacher_profile
    class_obj = get_object_or_404(Class, pk=class_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    current_term = Term.get_current()

    # Check permission
    is_assigned = ClassSubject.objects.filter(
        class_assigned=class_obj,
        subject=subject,
        teacher=teacher
    ).exists()

    if not is_assigned:
        return HttpResponse('<div class="alert alert-error">You are not assigned to teach this subject.</div>')

    # Check if grades locked
    if current_term and current_term.grades_locked:
        return HttpResponse('<div class="alert alert-warning">Grades are locked for this term.</div>')

    if request.method != 'POST':
        return HttpResponse('<div class="alert alert-error">Invalid request.</div>')

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return HttpResponse('<div class="alert alert-error">No file uploaded.</div>')

    # Get assignments for validation
    assignments = list(Assignment.objects.filter(
        subject=subject,
        term=current_term
    ).select_related('assessment_category').order_by('assessment_category__order', 'name'))

    # Get students for validation
    students = {s.admission_number: s for s in Student.objects.filter(
        current_class=class_obj,
        status='active'
    )}

    # Parse file
    rows = []
    filename = uploaded_file.name.lower()

    try:
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            try:
                import openpyxl
                from io import BytesIO

                wb = openpyxl.load_workbook(BytesIO(uploaded_file.read()))
                ws = wb.active

                for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
                    if row_idx == 0:
                        continue
                    if row and row[0]:
                        rows.append(list(row))
            except ImportError:
                return HttpResponse('<div class="alert alert-error">Excel support not available. Please use CSV format.</div>')
        else:
            decoded_file = TextIOWrapper(uploaded_file.file, encoding='utf-8-sig')
            reader = csv.reader(decoded_file)
            next(reader)
            for row in reader:
                if row and row[0]:
                    rows.append(row)
    except Exception as e:
        return HttpResponse(f'<div class="alert alert-error">Error reading file: {str(e)}</div>')

    # Validate and prepare preview data
    preview_data = []
    valid_count = 0
    error_count = 0

    for row_idx, row in enumerate(rows):
        if len(row) < 2:
            continue

        admission_no = str(row[0]).strip()
        student = students.get(admission_no)

        row_data = {
            'row_num': row_idx + 2,
            'admission_no': admission_no,
            'student_name': row[1] if len(row) > 1 else '',
            'student': student,
            'scores': [],
            'errors': []
        }

        if not student:
            row_data['errors'].append(f"Student not found: {admission_no}")
            error_count += 1
        else:
            for idx, assignment in enumerate(assignments):
                col_idx = idx + 2
                score_value = row[col_idx] if len(row) > col_idx else ''

                score_data = {
                    'assignment': assignment,
                    'value': score_value,
                    'valid': True,
                    'error': None
                }

                if score_value != '' and score_value is not None:
                    try:
                        score_float = float(score_value)
                        if score_float < 0:
                            score_data['valid'] = False
                            score_data['error'] = 'Negative value'
                        elif score_float > assignment.points_possible:
                            score_data['valid'] = False
                            score_data['error'] = f'Exceeds max ({assignment.points_possible})'
                    except (ValueError, TypeError):
                        score_data['valid'] = False
                        score_data['error'] = 'Invalid number'

                row_data['scores'].append(score_data)

                if not score_data['valid']:
                    error_count += 1

            if not row_data['errors'] and all(s['valid'] for s in row_data['scores']):
                valid_count += 1

        preview_data.append(row_data)

    # Store in session for confirmation
    session_data = []
    for row in preview_data:
        if row['student']:
            scores_to_save = []
            for score_data in row['scores']:
                if score_data['valid'] and score_data['value'] != '' and score_data['value'] is not None:
                    scores_to_save.append({
                        'assignment_id': str(score_data['assignment'].id),
                        'value': float(score_data['value'])
                    })
            session_data.append({
                'student_id': row['student'].id,
                'scores': scores_to_save
            })

    request.session[f'import_scores_{class_id}_{subject_id}'] = json.dumps(session_data)

    # Render preview
    from django.middleware.csrf import get_token
    csrf_token = get_token(request)

    html = f'''
    <div class="space-y-4">
        <div class="flex gap-4">
            <div class="stat bg-success/10 rounded-lg p-3">
                <div class="stat-title text-xs">Valid Rows</div>
                <div class="stat-value text-lg text-success">{valid_count}</div>
            </div>
            <div class="stat bg-error/10 rounded-lg p-3">
                <div class="stat-title text-xs">Errors</div>
                <div class="stat-value text-lg text-error">{error_count}</div>
            </div>
        </div>

        <div class="overflow-x-auto max-h-64">
            <table class="table table-xs">
                <thead>
                    <tr>
                        <th>Row</th>
                        <th>Admission No</th>
                        <th>Name</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
    '''

    for row in preview_data[:20]:
        status_class = 'text-success' if row['student'] and not row['errors'] else 'text-error'
        status_icon = 'fa-check' if row['student'] and not row['errors'] else 'fa-xmark'
        status_text = 'Valid' if row['student'] and not row['errors'] else (row['errors'][0] if row['errors'] else 'Has errors')

        html += f'''
            <tr>
                <td>{row['row_num']}</td>
                <td class="font-mono">{row['admission_no']}</td>
                <td>{row['student_name']}</td>
                <td class="{status_class}">
                    <i class="fa-solid {status_icon} mr-1"></i>{status_text}
                </td>
            </tr>
        '''

    if len(preview_data) > 20:
        html += f'<tr><td colspan="4" class="text-center text-base-content/60">... and {len(preview_data) - 20} more rows</td></tr>'

    html += '''
                </tbody>
            </table>
        </div>
    '''

    from django.urls import reverse
    confirm_url = reverse('core:import_scores_confirm', args=[class_id, subject_id])

    if valid_count > 0:
        html += f'''
        <form hx-post="{confirm_url}"
              hx-target="#import-content"
              hx-swap="innerHTML">
            <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}">
            <div class="modal-action">
                <button type="button" class="btn btn-ghost" onclick="modal_import.close()">Cancel</button>
                <button type="submit" class="btn btn-primary gap-2">
                    <i class="fa-solid fa-check"></i>
                    Import {valid_count} Rows
                </button>
            </div>
        </form>
        '''
    else:
        html += '''
        <div class="modal-action">
            <button type="button" class="btn btn-ghost" onclick="modal_import.close()">Close</button>
        </div>
        '''

    html += '</div>'

    return HttpResponse(html)


@login_required
def import_scores_confirm(request, class_id, subject_id):
    """Confirm and save imported scores."""
    import json
    from django.http import HttpResponse
    from academics.models import Class, ClassSubject, Subject
    from gradebook.models import Assignment, Score
    from students.models import Student
    from teachers.models import Teacher

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        return HttpResponse('<div class="alert alert-error">Permission denied.</div>')

    teacher = user.teacher_profile
    class_obj = get_object_or_404(Class, pk=class_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    current_term = Term.get_current()

    # Check permission
    is_assigned = ClassSubject.objects.filter(
        class_assigned=class_obj,
        subject=subject,
        teacher=teacher
    ).exists()

    if not is_assigned:
        return HttpResponse('<div class="alert alert-error">You are not assigned to teach this subject.</div>')

    # Check if grades locked
    if current_term and current_term.grades_locked:
        return HttpResponse('<div class="alert alert-warning">Grades are locked for this term.</div>')

    # Get session data
    session_key = f'import_scores_{class_id}_{subject_id}'
    session_data = request.session.get(session_key)

    if not session_data:
        return HttpResponse('<div class="alert alert-error">Session expired. Please upload the file again.</div>')

    try:
        import_data = json.loads(session_data)
    except json.JSONDecodeError:
        return HttpResponse('<div class="alert alert-error">Invalid session data.</div>')

    # Import scores
    saved_count = 0
    updated_count = 0

    for row in import_data:
        student_id = row['student_id']
        for score_data in row['scores']:
            assignment_id = score_data['assignment_id']
            value = score_data['value']

            score, created = Score.objects.update_or_create(
                student_id=student_id,
                assignment_id=assignment_id,
                defaults={'points': value}
            )

            if created:
                saved_count += 1
            else:
                updated_count += 1

    # Clear session
    del request.session[session_key]

    # Return success message
    html = f'''
    <div class="text-center py-8">
        <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-success/20 flex items-center justify-center">
            <i class="fa-solid fa-check text-success text-3xl"></i>
        </div>
        <h3 class="font-bold text-lg mb-2">Import Complete!</h3>
        <p class="text-base-content/60 mb-4">
            {saved_count} new scores added, {updated_count} scores updated.
        </p>
        <button type="button" class="btn btn-primary" onclick="modal_import.close(); location.reload();">
            Done
        </button>
    </div>
    '''

    return HttpResponse(html)


@login_required
def class_students(request, class_id):
    """Form teacher view to manage students in their homeroom class."""
    from academics.models import Class, ClassSubject, StudentSubjectEnrollment
    from students.models import Student
    from teachers.models import Teacher

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        messages.error(request, 'This page is only accessible to teachers.')
        return redirect('core:index')

    teacher = user.teacher_profile
    class_obj = get_object_or_404(Class, pk=class_id)

    # Must be the form teacher (class teacher) of this class
    if class_obj.class_teacher != teacher:
        messages.error(request, 'You are not the form teacher for this class.')
        return redirect('core:my_classes')

    current_term = Term.get_current()

    # Get students in this class
    students = Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('last_name', 'first_name')

    # Get class subjects (for elective enrollment)
    class_subjects = ClassSubject.objects.filter(
        class_assigned=class_obj
    ).select_related('subject', 'teacher').order_by('-subject__is_core', 'subject__name')

    core_subjects = [cs for cs in class_subjects if cs.subject.is_core]
    elective_subjects = [cs for cs in class_subjects if not cs.subject.is_core]

    # Get enrollment data for each student
    students_data = []
    for student in students:
        enrollments = StudentSubjectEnrollment.objects.filter(
            student=student,
            class_subject__class_assigned=class_obj,
            is_active=True
        ).select_related('class_subject__subject')

        enrolled_subjects = [e.class_subject.subject for e in enrollments]
        enrolled_electives = [e for e in enrollments if not e.class_subject.subject.is_core]
        enrolled_elective_ids = [e.class_subject_id for e in enrolled_electives]

        students_data.append({
            'student': student,
            'enrolled_subjects_count': len(enrolled_subjects),
            'enrolled_electives': [e.class_subject.subject for e in enrolled_electives],
            'enrolled_elective_ids': enrolled_elective_ids,
        })

    # Get students available for enrollment (not in any class)
    available_students = Student.objects.filter(
        status='active',
        current_class__isnull=True
    ).order_by('last_name', 'first_name')[:50]

    context = {
        'teacher': teacher,
        'class_obj': class_obj,
        'current_term': current_term,
        'students_data': students_data,
        'student_count': len(students_data),
        'core_subjects': core_subjects,
        'elective_subjects': elective_subjects,
        'available_students': available_students,
    }

    return htmx_render(
        request,
        'core/teacher/class_students.html',
        'core/teacher/partials/class_students_content.html',
        context
    )


@login_required
def enroll_student(request, class_id):
    """Enroll a student into a class (form teacher only)."""
    from academics.models import Class, ClassSubject, StudentSubjectEnrollment
    from students.models import Student
    from teachers.models import Teacher

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        return HttpResponse('<div class="alert alert-error">Permission denied.</div>', status=403)

    teacher = user.teacher_profile
    class_obj = get_object_or_404(Class, pk=class_id)

    # Must be the form teacher
    if class_obj.class_teacher != teacher:
        return HttpResponse('<div class="alert alert-error">You are not the form teacher for this class.</div>', status=403)

    if request.method != 'POST':
        return HttpResponse(status=405)

    student_id = request.POST.get('student_id')
    if not student_id:
        return HttpResponse('<div class="alert alert-error">No student selected.</div>', status=400)

    student = get_object_or_404(Student, pk=student_id)

    # Check if student already in a class
    if student.current_class:
        return HttpResponse(f'<div class="alert alert-warning">Student is already in {student.current_class.name}.</div>', status=400)

    # Enroll student in the class
    student.current_class = class_obj
    student.save()

    # Auto-enroll in core subjects
    StudentSubjectEnrollment.enroll_student_in_core_subjects(student, class_obj, enrolled_by=teacher)

    # Return success response with redirect trigger
    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'studentEnrolled'
    return response


@login_required
def remove_student(request, class_id, student_id):
    """Remove a student from a class (form teacher only)."""
    from academics.models import Class, StudentSubjectEnrollment
    from students.models import Student
    from teachers.models import Teacher

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        return HttpResponse('<div class="alert alert-error">Permission denied.</div>', status=403)

    teacher = user.teacher_profile
    class_obj = get_object_or_404(Class, pk=class_id)

    # Must be the form teacher
    if class_obj.class_teacher != teacher:
        return HttpResponse('<div class="alert alert-error">You are not the form teacher for this class.</div>', status=403)

    if request.method != 'POST':
        return HttpResponse(status=405)

    student = get_object_or_404(Student, pk=student_id)

    # Check if student is in this class
    if student.current_class != class_obj:
        return HttpResponse('<div class="alert alert-error">Student is not in this class.</div>', status=400)

    # Remove subject enrollments
    StudentSubjectEnrollment.objects.filter(
        student=student,
        class_subject__class_assigned=class_obj
    ).update(is_active=False)

    # Remove from class
    student.current_class = None
    student.save()

    # Return success response with refresh trigger
    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'studentRemoved'
    return response


@login_required
def update_student_electives(request, class_id, student_id):
    """Update elective subject enrollments for a student."""
    from academics.models import Class, ClassSubject, StudentSubjectEnrollment
    from students.models import Student
    from teachers.models import Teacher

    user = request.user

    # Must be a teacher
    if not getattr(user, 'is_teacher', False) or not hasattr(user, 'teacher_profile'):
        return HttpResponse('<div class="alert alert-error">Permission denied.</div>', status=403)

    teacher = user.teacher_profile
    class_obj = get_object_or_404(Class, pk=class_id)

    # Must be the form teacher
    if class_obj.class_teacher != teacher:
        return HttpResponse('<div class="alert alert-error">You are not the form teacher for this class.</div>', status=403)

    if request.method != 'POST':
        return HttpResponse(status=405)

    student = get_object_or_404(Student, pk=student_id)

    # Check if student is in this class
    if student.current_class != class_obj:
        return HttpResponse('<div class="alert alert-error">Student is not in this class.</div>', status=400)

    # Get selected elective IDs
    selected_elective_ids = request.POST.getlist('electives')

    # Get all elective class subjects for this class
    elective_class_subjects = ClassSubject.objects.filter(
        class_assigned=class_obj,
        subject__is_core=False
    )

    # Update enrollments
    for class_subject in elective_class_subjects:
        should_be_enrolled = str(class_subject.id) in selected_elective_ids

        if should_be_enrolled:
            # Create or reactivate enrollment
            enrollment, created = StudentSubjectEnrollment.objects.get_or_create(
                student=student,
                class_subject=class_subject,
                defaults={
                    'enrolled_by': teacher,
                    'is_active': True
                }
            )
            if not created and not enrollment.is_active:
                enrollment.is_active = True
                enrollment.save()
        else:
            # Deactivate enrollment
            StudentSubjectEnrollment.objects.filter(
                student=student,
                class_subject=class_subject
            ).update(is_active=False)

    # Return success response
    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'electivesUpdated'
    return response


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
    """Student's class timetable view."""
    from academics.models import TimetableEntry, Period

    user = request.user

    # Verify user is a student
    if not getattr(user, 'is_student', False):
        messages.error(request, 'This page is only accessible to students.')
        return redirect('core:index')

    student = getattr(user, 'student_profile', None)
    if not student:
        messages.error(request, 'No student profile linked to your account.')
        return redirect('core:index')

    # Get student's current class
    current_class = student.current_class
    if not current_class:
        context = {
            'no_class': True,
        }
        return htmx_render(request, 'core/student/timetable.html', 'core/student/partials/timetable_content.html', context)

    # Get all periods ordered by start time
    periods = Period.objects.filter(is_active=True).order_by('order', 'start_time')

    # Get all timetable entries for this class
    entries = TimetableEntry.objects.filter(
        class_subject__class_assigned=current_class
    ).select_related(
        'class_subject__subject',
        'class_subject__teacher__user',
        'period'
    ).order_by('weekday', 'period__order')

    # Build timetable grid: {weekday: {period_id: entry}}
    timetable = {day: {} for day in range(1, 6)}  # Monday=1 to Friday=5
    for entry in entries:
        timetable[entry.weekday][entry.period_id] = entry

    # Weekday labels
    weekdays = [
        (1, 'Monday'),
        (2, 'Tuesday'),
        (3, 'Wednesday'),
        (4, 'Thursday'),
        (5, 'Friday'),
    ]

    # Calculate stats
    total_lessons = entries.count()
    total_subjects = len(set(e.class_subject.subject_id for e in entries))

    context = {
        'student': student,
        'current_class': current_class,
        'periods': periods,
        'timetable': timetable,
        'weekdays': weekdays,
        'entries': entries,
        'total_lessons': total_lessons,
        'total_subjects': total_subjects,
    }

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


def verify_document(request, code):
    """
    Public view to verify document authenticity.
    No login required - anyone with the code can verify.
    """
    from .models import DocumentVerification

    verification = None
    try:
        verification = DocumentVerification.objects.get(verification_code=code.upper())
        verification.record_verification()
    except DocumentVerification.DoesNotExist:
        pass

    context = {
        'code': code,
        'verification': verification,
        'is_valid': verification is not None,
    }
    return render(request, 'core/verify_document.html', context)