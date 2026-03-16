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

    # ========== Action Items ==========
    action_items = []
    today = timezone.localdate()

    if current_term:
        from academics.models import AttendanceSession
        from gradebook.models import Assignment, Score, TermReport

        # 1. Homeroom classes needing attendance today (daily classes only, school days only)
        from core.models import SchoolHoliday, SchoolSettings
        school_settings = SchoolSettings.load()
        homeroom_ids = [c.pk for c in homeroom_classes]
        today_weekday = today.isoweekday()
        is_school_day = school_settings.is_school_day(today_weekday)
        is_holiday = SchoolHoliday.is_holiday(today) if is_school_day else True
        if homeroom_ids and is_school_day and not is_holiday:
            # Only show action items for daily-attendance classes that have timetable today
            from academics.utils import should_use_lesson_attendance
            # Only daily-attendance homeroom classes (not per-lesson)
            daily_homeroom_ids = [
                cls.pk for cls in homeroom_classes
                if not should_use_lesson_attendance(cls)
            ]

            if daily_homeroom_ids:
                classes_with_attendance = set(
                    AttendanceSession.objects.filter(
                        class_assigned_id__in=daily_homeroom_ids,
                        date=today,
                        session_type='Daily',
                    ).values_list('class_assigned_id', flat=True)
                )
                for cls in homeroom_classes:
                    if (cls.pk in daily_homeroom_ids
                            and cls.pk not in classes_with_attendance
                            and cls.student_count > 0):
                        action_items.append({
                            'type': 'attendance',
                            'icon': 'fa-solid fa-clipboard-check',
                            'color': 'error',
                            'message': f'Take attendance for {cls.name}',
                            'url': f"/academics/attendance/take/{cls.pk}/",
                        })

        # 2. Score completion - subjects with < 100% scores entered
        term_assignments = Assignment.objects.filter(
            term=current_term,
            subject__classsubject__teacher=teacher,
        ).select_related('subject', 'assessment_category').distinct()

        if term_assignments.exists():
            # Get all assignment IDs and their class/student counts
            for sa in subject_assignments:
                sa_assignments = [a for a in term_assignments if a.subject_id == sa.subject_id]
                if not sa_assignments:
                    continue
                student_count = class_student_counts.get(sa.class_assigned_id, 0)
                if student_count == 0:
                    continue
                total_expected = student_count * len(sa_assignments)
                filled = Score.objects.filter(
                    assignment__in=sa_assignments,
                    student__current_class_id=sa.class_assigned_id,
                ).count()
                if filled < total_expected:
                    pct = round((filled / total_expected) * 100) if total_expected > 0 else 0
                    action_items.append({
                        'type': 'scores',
                        'icon': 'fa-solid fa-pen-to-square',
                        'color': 'warning' if pct > 50 else 'error',
                        'message': f'{sa.class_assigned.name} — {sa.subject.name}: {pct}% scores entered',
                        'url': f"/gradebook/scores/{sa.class_assigned_id}/{sa.subject_id}/",
                    })

        # 3. Unsigned remarks for homeroom classes
        if homeroom_ids:
            unsigned_count = TermReport.objects.filter(
                student__current_class_id__in=homeroom_ids,
                term=current_term,
                class_teacher_remark='',
            ).count()
            if unsigned_count > 0:
                first_homeroom = homeroom_classes[0]
                action_items.append({
                    'type': 'remarks',
                    'icon': 'fa-solid fa-comment-dots',
                    'color': 'warning',
                    'message': f'{unsigned_count} student(s) missing class teacher remarks',
                    'url': f"/gradebook/remarks/bulk/{first_homeroom.pk}/",
                })

    # ========== Homeroom Attendance Stats ==========
    homeroom_attendance = {}
    if current_term and homeroom_ids:
        from academics.models import AttendanceRecord

        for cls in homeroom_classes:
            sessions = AttendanceSession.objects.filter(
                class_assigned=cls,
                date__gte=current_term.start_date,
                date__lte=today,
                session_type='Daily',
            )
            total_days = sessions.values('date').distinct().count()
            if total_days == 0 or cls.student_count == 0:
                continue

            present = AttendanceRecord.objects.filter(
                session__in=sessions,
                status__in=['P', 'L'],
            ).values('student', 'session__date').distinct().count()

            total_possible = total_days * cls.student_count
            rate = round((present / total_possible) * 100, 1) if total_possible > 0 else 0
            homeroom_attendance[cls.pk] = {
                'rate': rate,
                'total_days': total_days,
                'color': 'success' if rate >= 90 else ('warning' if rate >= 75 else 'error'),
            }

    context = {
        'teacher': teacher,
        'current_term': current_term,
        'homeroom_classes': homeroom_classes,
        'classes_taught': classes_taught,
        'assignments_by_class': assignments_by_class,
        'action_items': action_items,
        'homeroom_attendance': homeroom_attendance,
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
