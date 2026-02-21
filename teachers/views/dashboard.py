from django.db.models import Count, Q
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.vary import vary_on_headers

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

    # Get class assignments with student count annotation to avoid N+1
    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    ).annotate(
        student_count=Count('students', filter=Q(students__status='active'))
    ).order_by('name')

    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name'
    )

    # Calculate workload efficiently - reuse subject_assignments queryset
    class_ids_taught = list(subject_assignments.values_list('class_assigned_id', flat=True).distinct())

    total_students = Student.objects.filter(
        current_class_id__in=class_ids_taught,
        status='active'
    ).count() if class_ids_taught else 0

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
@cache_control(max_age=60, stale_while_revalidate=300)
@vary_on_headers('HX-Request')
def dashboard(request):
    """Dashboard for logged-in teachers showing their classes and students."""
    teacher = getattr(request.user, 'teacher_profile', None)

    if not teacher:
        messages.warning(request, "No teacher profile linked to your account.")
        return redirect('core:index')

    # Get current term
    from core.models import Term
    current_term = Term.get_current()

    # Homeroom classes with student count annotation to avoid N+1
    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    ).annotate(
        student_count=Count('students', filter=Q(students__status='active'))
    ).order_by('name')

    # Subject assignments - single query, reuse for all derived data
    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name'
    )

    # Extract unique classes from already-loaded assignments (no extra query)
    seen_class_ids = set()
    classes_taught = []
    for assignment in subject_assignments:
        if assignment.class_assigned_id not in seen_class_ids:
            classes_taught.append(assignment.class_assigned)
            seen_class_ids.add(assignment.class_assigned_id)

    # Calculate stats efficiently
    total_students = Student.objects.filter(
        current_class_id__in=seen_class_ids,
        status='active'
    ).count() if seen_class_ids else 0

    # Sum homeroom students from annotated count (no extra query)
    homeroom_students = sum(cls.student_count for cls in homeroom_classes)

    # Get student counts for all taught classes in one query
    class_student_counts = dict(
        Student.objects.filter(
            current_class_id__in=seen_class_ids,
            status='active'
        ).values('current_class_id').annotate(
            count=Count('id')
        ).values_list('current_class_id', 'count')
    ) if seen_class_ids else {}

    # Group assignments by class for easy display
    assignments_by_class = {}
    for assignment in subject_assignments:
        class_name = assignment.class_assigned.name
        if class_name not in assignments_by_class:
            assignments_by_class[class_name] = {
                'class': assignment.class_assigned,
                'subjects': [],
                'student_count': class_student_counts.get(assignment.class_assigned_id, 0),
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
