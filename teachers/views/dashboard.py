from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from teachers.models import Teacher
from academics.models import Class, ClassSubject, Period, TimetableEntry
from students.models import Student
from .utils import admin_required, htmx_render


@login_required
def profile(request):
    """View own teacher profile."""
    teacher = getattr(request.user, 'teacher_profile', None)

    if not teacher:
        messages.warning(request, "No teacher profile linked to your account.")
        return redirect('core:index')

    # Get class assignments
    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    ).order_by('name')

    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name'
    )

    # Calculate workload efficiently using database queries
    class_ids_taught = ClassSubject.objects.filter(
        teacher=teacher
    ).values_list('class_assigned_id', flat=True).distinct()

    total_students = Student.objects.filter(
        current_class_id__in=class_ids_taught,
        status='active'
    ).count()

    context = {
        'teacher': teacher,
        'homeroom_classes': homeroom_classes,
        'subject_assignments': subject_assignments,
        'workload': {
            'classes_taught': len(class_ids_taught),
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


@login_required
def dashboard(request):
    """Dashboard for logged-in teachers showing their classes and students."""
    teacher = getattr(request.user, 'teacher_profile', None)

    if not teacher:
        messages.warning(request, "No teacher profile linked to your account.")
        return redirect('core:index')

    # Get current term
    from core.models import Term
    current_term = Term.get_current()

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

    # Get unique class IDs taught efficiently
    class_ids_taught = ClassSubject.objects.filter(
        teacher=teacher
    ).values_list('class_assigned_id', flat=True).distinct()

    # Get class objects for display (sorted)
    classes_taught = list(Class.objects.filter(
        id__in=class_ids_taught
    ).order_by('level_number', 'name'))

    # Calculate stats efficiently
    total_students = Student.objects.filter(
        current_class_id__in=class_ids_taught,
        status='active'
    ).count()

    homeroom_students = Student.objects.filter(
        current_class_id__in=homeroom_classes.values_list('id', flat=True),
        status='active'
    ).count()

    # Group assignments by class for easy display
    assignments_by_class = {}
    for assignment in subject_assignments:
        class_name = assignment.class_assigned.name
        if class_name not in assignments_by_class:
            assignments_by_class[class_name] = {
                'class': assignment.class_assigned,
                'subjects': []
            }
        assignments_by_class[class_name]['subjects'].append(assignment.subject)

    context = {
        'teacher': teacher,
        'current_term': current_term,
        'homeroom_classes': homeroom_classes,
        'classes_taught': classes_taught,
        'assignments_by_class': assignments_by_class,
        'stats': {
            'classes_count': len(classes_taught),
            'subjects_count': subject_assignments.count(),
            'total_students': total_students,
            'homeroom_students': homeroom_students,
        }
    }

    return htmx_render(
        request,
        'teachers/dashboard.html',
        'teachers/partials/dashboard_content.html',
        context
    )


@login_required
def schedule(request):
    """Weekly schedule/timetable view for logged-in teachers."""
    teacher = getattr(request.user, 'teacher_profile', None)

    if not teacher:
        messages.warning(request, "No teacher profile linked to your account.")
        return redirect('core:index')

    today = timezone.now()
    weekday = today.isoweekday()  # 1=Monday, 7=Sunday

    # Get all periods (time slots)
    periods = Period.objects.filter(is_active=True).order_by('order')

    # Get all timetable entries for this teacher
    entries = TimetableEntry.objects.filter(
        class_subject__teacher=teacher
    ).select_related(
        'class_subject__class_assigned',
        'class_subject__subject',
        'period'
    ).order_by('weekday', 'period__order')

    # Organize entries into a grid: {period_id: {weekday: entry}}
    schedule_grid = {}
    for period in periods:
        schedule_grid[period.id] = {
            'period': period,
            'days': {1: None, 2: None, 3: None, 4: None, 5: None}
        }

    for entry in entries:
        if entry.period_id in schedule_grid:
            schedule_grid[entry.period_id]['days'][entry.weekday] = entry

    # Calculate stats
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


@admin_required
def teacher_schedule(request, pk):
    """View any teacher's schedule - Admin only."""
    teacher = get_object_or_404(Teacher, pk=pk)

    # Get all periods (time slots)
    periods = Period.objects.filter(is_active=True).order_by('order')

    # Get all timetable entries for this teacher
    entries = TimetableEntry.objects.filter(
        class_subject__teacher=teacher
    ).select_related(
        'class_subject__class_assigned',
        'class_subject__subject',
        'period'
    ).order_by('weekday', 'period__order')

    # Organize entries into a grid
    schedule_grid = {}
    for period in periods:
        schedule_grid[period.id] = {
            'period': period,
            'days': {1: None, 2: None, 3: None, 4: None, 5: None}
        }

    for entry in entries:
        if entry.period_id in schedule_grid:
            schedule_grid[entry.period_id]['days'][entry.weekday] = entry

    # Calculate stats
    total_periods = entries.count()

    context = {
        'teacher': teacher,
        'periods': periods,
        'schedule_grid': schedule_grid,
        'weekdays': TimetableEntry.Weekday.choices,
        'stats': {
            'total_periods': total_periods,
        }
    }

    return htmx_render(
        request,
        'teachers/schedule.html',
        'teachers/partials/schedule_content.html',
        context
    )
