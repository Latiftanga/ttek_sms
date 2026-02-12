"""
Teacher Workload Analytics Views.

Provides workload metrics, comparisons with school averages,
and analytics visualizations.
"""
from collections import defaultdict

from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required

from teachers.models import Teacher
from academics.models import ClassSubject, TimetableEntry, Class
from students.models import Student
from .utils import admin_required, htmx_render


def calculate_teacher_workload(teacher):
    """
    Calculate workload metrics for a single teacher.

    Returns:
        dict with classes_taught, subjects_taught, periods_per_week,
        total_students, homeroom_classes
    """
    # Get assignments
    assignments = ClassSubject.objects.filter(teacher=teacher)
    class_ids = list(assignments.values_list('class_assigned_id', flat=True).distinct())

    # Calculate metrics
    classes_taught = len(set(class_ids))
    subjects_taught = assignments.values('subject_id').distinct().count()

    # Periods per week from timetable
    periods_per_week = TimetableEntry.objects.filter(
        class_subject__teacher=teacher
    ).count()

    # Total students across all classes
    total_students = Student.objects.filter(
        current_class_id__in=class_ids,
        status='active'
    ).count() if class_ids else 0

    # Homeroom classes
    homeroom_count = Class.objects.filter(class_teacher=teacher, is_active=True).count()

    return {
        'classes_taught': classes_taught,
        'subjects_taught': subjects_taught,
        'periods_per_week': periods_per_week,
        'total_students': total_students,
        'homeroom_classes': homeroom_count,
    }


def _bulk_workload_data():
    """
    Compute workload metrics for ALL active teachers with assignments
    using bulk queries (4 queries total instead of 4 per teacher).

    Returns:
        dict mapping teacher_id -> workload dict
    """
    # 1. Classes + subjects per teacher (1 query)
    assignment_stats = ClassSubject.objects.values('teacher_id').annotate(
        classes_taught=Count('class_assigned_id', distinct=True),
        subjects_taught=Count('subject_id', distinct=True),
    )
    stats_by_teacher = {
        row['teacher_id']: row for row in assignment_stats
    }

    if not stats_by_teacher:
        return {}

    # 2. Periods per week per teacher (1 query)
    period_stats = TimetableEntry.objects.values(
        'class_subject__teacher_id'
    ).annotate(
        periods=Count('id')
    )
    periods_by_teacher = {
        row['class_subject__teacher_id']: row['periods']
        for row in period_stats
    }

    # 3. Student counts per class, then map to teachers (2 queries)
    # First get teacher -> class_ids mapping
    teacher_classes = defaultdict(set)
    for row in ClassSubject.objects.values_list('teacher_id', 'class_assigned_id'):
        teacher_classes[row[0]].add(row[1])

    # Get student counts per class in one query
    all_class_ids = set()
    for cids in teacher_classes.values():
        all_class_ids.update(cids)

    students_per_class = {}
    if all_class_ids:
        students_per_class = dict(
            Student.objects.filter(
                current_class_id__in=all_class_ids,
                status='active'
            ).values('current_class_id').annotate(
                count=Count('id')
            ).values_list('current_class_id', 'count')
        )

    # 4. Homeroom counts per teacher (1 query)
    homeroom_stats = dict(
        Class.objects.filter(
            is_active=True,
            class_teacher_id__isnull=False
        ).values('class_teacher_id').annotate(
            count=Count('id')
        ).values_list('class_teacher_id', 'count')
    )

    # Build result
    result = {}
    for teacher_id, stats in stats_by_teacher.items():
        teacher_class_ids = teacher_classes.get(teacher_id, set())
        total_students = sum(
            students_per_class.get(cid, 0) for cid in teacher_class_ids
        )
        result[teacher_id] = {
            'classes_taught': stats['classes_taught'],
            'subjects_taught': stats['subjects_taught'],
            'periods_per_week': periods_by_teacher.get(teacher_id, 0),
            'total_students': total_students,
            'homeroom_classes': homeroom_stats.get(teacher_id, 0),
        }

    return result


def calculate_school_averages(bulk_data=None):
    """
    Calculate school-wide average workload across all active teachers
    with assignments.

    Args:
        bulk_data: Optional pre-computed bulk workload data from _bulk_workload_data().

    Returns:
        dict with avg_classes, avg_subjects, avg_periods, avg_students
    """
    if bulk_data is None:
        bulk_data = _bulk_workload_data()

    if not bulk_data:
        return {
            'avg_classes': 0,
            'avg_subjects': 0,
            'avg_periods': 0,
            'avg_students': 0,
            'teacher_count': 0,
        }

    count = len(bulk_data)
    total_classes = sum(w['classes_taught'] for w in bulk_data.values())
    total_subjects = sum(w['subjects_taught'] for w in bulk_data.values())
    total_periods = sum(w['periods_per_week'] for w in bulk_data.values())
    total_students = sum(w['total_students'] for w in bulk_data.values())

    return {
        'avg_classes': round(total_classes / count, 1),
        'avg_subjects': round(total_subjects / count, 1),
        'avg_periods': round(total_periods / count, 1),
        'avg_students': round(total_students / count, 1),
        'teacher_count': count,
    }


def get_class_breakdown(teacher):
    """
    Get detailed breakdown of workload by class.

    Returns list of dicts with class info, subjects, student counts, periods.
    """
    assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name'
    )

    # Collect unique class IDs first
    class_ids = set()
    for assignment in assignments:
        class_ids.add(assignment.class_assigned_id)

    if not class_ids:
        return []

    # Prefetch student counts for all classes in one query
    student_counts = dict(
        Student.objects.filter(
            current_class_id__in=class_ids,
            status='active'
        ).values('current_class_id').annotate(
            count=Count('id')
        ).values_list('current_class_id', 'count')
    )

    # Prefetch period counts for all classes in one query
    period_counts = dict(
        TimetableEntry.objects.filter(
            class_subject__teacher=teacher,
            class_subject__class_assigned_id__in=class_ids
        ).values('class_subject__class_assigned_id').annotate(
            count=Count('id')
        ).values_list('class_subject__class_assigned_id', 'count')
    )

    # Group by class using prefetched data
    class_data = {}
    for assignment in assignments:
        class_obj = assignment.class_assigned
        class_id = class_obj.pk

        if class_id not in class_data:
            class_data[class_id] = {
                'class': class_obj,
                'subjects': [],
                'student_count': student_counts.get(class_id, 0),
                'periods': period_counts.get(class_id, 0),
                'is_homeroom': class_obj.class_teacher_id == teacher.pk,
            }

        class_data[class_id]['subjects'].append(assignment.subject)

    return list(class_data.values())


@login_required
def my_workload(request):
    """
    Teacher self-service: View own workload analytics.
    """
    # Get teacher for logged-in user
    teacher = get_object_or_404(Teacher, user=request.user)

    # Calculate workload
    workload = calculate_teacher_workload(teacher)

    # Bulk-compute school averages (single set of queries for all teachers)
    bulk_data = _bulk_workload_data()
    school_averages = calculate_school_averages(bulk_data)

    class_breakdown = get_class_breakdown(teacher)

    # Calculate comparison percentages
    def calc_comparison(value, avg):
        if avg == 0:
            return 100 if value > 0 else 0
        return round((value / avg) * 100)

    comparisons = {
        'classes': calc_comparison(workload['classes_taught'], school_averages['avg_classes']),
        'subjects': calc_comparison(workload['subjects_taught'], school_averages['avg_subjects']),
        'periods': calc_comparison(workload['periods_per_week'], school_averages['avg_periods']),
        'students': calc_comparison(workload['total_students'], school_averages['avg_students']),
    }

    context = {
        'teacher': teacher,
        'workload': workload,
        'school_averages': school_averages,
        'comparisons': comparisons,
        'class_breakdown': class_breakdown,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'My Workload'},
        ],
        'back_url': '/',
    }

    return htmx_render(
        request,
        'teachers/my_workload.html',
        'teachers/partials/my_workload_content.html',
        context
    )


@admin_required
def school_workload_overview(request):
    """
    Admin view: Overview of all teachers' workload.
    Shows comparison table of all teachers with their metrics.
    """
    active_teachers = Teacher.objects.filter(
        status='active'
    ).order_by('first_name', 'last_name')

    # Single bulk computation for ALL teachers (replaces N+1 loop)
    bulk_data = _bulk_workload_data()

    # Build workload list from bulk data
    teacher_workloads = []
    for teacher in active_teachers:
        workload = bulk_data.get(teacher.pk)
        if workload and workload['classes_taught'] > 0:
            teacher_workloads.append({
                'teacher': teacher,
                **workload
            })

    # Reuse same bulk data for averages (no extra queries)
    school_averages = calculate_school_averages(bulk_data)

    context = {
        'teacher_workloads': teacher_workloads,
        'school_averages': school_averages,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Teachers', 'url': '/teachers/'},
            {'label': 'Workload Overview'},
        ],
        'back_url': '/teachers/',
    }

    return htmx_render(
        request,
        'teachers/workload_overview.html',
        'teachers/partials/workload_overview_content.html',
        context
    )
