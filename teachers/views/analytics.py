"""
Teacher Workload Analytics Views.

Provides workload metrics, comparisons with school averages,
and analytics visualizations.
"""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required

from teachers.models import Teacher
from academics.models import ClassSubject, TimetableEntry, Class
from students.models import Student
from .utils import admin_required, htmx_render


def calculate_teacher_workload(teacher):
    """
    Calculate workload metrics for a teacher.

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


def calculate_school_averages():
    """
    Calculate school-wide average workload across all active teachers
    with assignments.

    Returns:
        dict with avg_classes, avg_subjects, avg_periods, avg_students
    """
    active_teachers = Teacher.objects.filter(status='active')

    total_classes = 0
    total_subjects = 0
    total_periods = 0
    total_students = 0
    count = 0

    for teacher in active_teachers:
        workload = calculate_teacher_workload(teacher)
        # Only count teachers with assignments
        if workload['classes_taught'] > 0:
            total_classes += workload['classes_taught']
            total_subjects += workload['subjects_taught']
            total_periods += workload['periods_per_week']
            total_students += workload['total_students']
            count += 1

    if count == 0:
        return {
            'avg_classes': 0,
            'avg_subjects': 0,
            'avg_periods': 0,
            'avg_students': 0,
            'teacher_count': 0,
        }

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

    # Group by class
    class_data = {}
    for assignment in assignments:
        class_obj = assignment.class_assigned
        class_id = class_obj.pk

        if class_id not in class_data:
            # Count students in this class
            student_count = Student.objects.filter(
                current_class=class_obj,
                status='active'
            ).count()

            # Count periods for this teacher in this class
            periods = TimetableEntry.objects.filter(
                class_subject__teacher=teacher,
                class_subject__class_assigned=class_obj
            ).count()

            # Check if homeroom
            is_homeroom = class_obj.class_teacher_id == teacher.pk

            class_data[class_id] = {
                'class': class_obj,
                'subjects': [],
                'student_count': student_count,
                'periods': periods,
                'is_homeroom': is_homeroom,
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
    school_averages = calculate_school_averages()
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
    active_teachers = Teacher.objects.filter(status='active').order_by('first_name', 'last_name')

    # Calculate workload for each teacher
    teacher_workloads = []
    for teacher in active_teachers:
        workload = calculate_teacher_workload(teacher)
        # Only include teachers with assignments
        if workload['classes_taught'] > 0:
            teacher_workloads.append({
                'teacher': teacher,
                **workload
            })

    school_averages = calculate_school_averages()

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
