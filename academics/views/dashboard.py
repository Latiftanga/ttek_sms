"""Dashboard/index views for academics app."""
from datetime import timedelta

from django.db import models
from django.db.models import Count, Q
from django.utils import timezone

from core.utils import cache_page_per_tenant

from ..models import (
    Programme, Class, Subject, SubjectTemplate,
    AttendanceRecord, Period, TimetableEntry, Classroom
)
from ..forms import ProgrammeForm, SubjectForm
from .base import admin_required, htmx_render


@admin_required
@cache_page_per_tenant(timeout=300)  # Cache for 5 minutes
def index(request):
    """Academics dashboard page - Admin only. Cached for 5 minutes."""
    from core.models import Term
    from students.models import Student

    current_term = Term.get_current()

    # Get classes with student counts grouped by level
    classes = Class.objects.select_related('programme', 'class_teacher').annotate(
        student_count=Count('students', filter=models.Q(students__status='active'))
    ).filter(is_active=True).order_by('level_number', 'section')

    # Group classes by level type with stats
    classes_by_level = {
        'creche': {'label': 'Creche', 'classes': [], 'student_count': 0, 'icon': 'fa-baby-carriage', 'color': 'secondary'},
        'nursery': {'label': 'Nursery', 'classes': [], 'student_count': 0, 'icon': 'fa-face-smile', 'color': 'accent'},
        'kg': {'label': 'KG', 'classes': [], 'student_count': 0, 'icon': 'fa-baby', 'color': 'info'},
        'basic': {'label': 'Basic', 'classes': [], 'student_count': 0, 'icon': 'fa-child', 'color': 'success'},
        'shs': {'label': 'SHS', 'classes': [], 'student_count': 0, 'icon': 'fa-graduation-cap', 'color': 'primary'},
    }
    for cls in classes:
        if cls.level_type in classes_by_level:
            classes_by_level[cls.level_type]['classes'].append(cls)
            classes_by_level[cls.level_type]['student_count'] += cls.student_count

    # Programmes with stats
    programmes = Programme.objects.annotate(
        class_count=Count('classes', filter=Q(classes__is_active=True)),
        student_count=Count(
            'classes__students',
            filter=Q(classes__is_active=True, classes__students__status='active')
        )
    ).order_by('name')

    # Subjects with stats
    subjects = Subject.objects.prefetch_related('programmes').annotate(
        class_count=Count(
            'class_allocations',
            filter=Q(class_allocations__class_assigned__is_active=True)
        )
    ).order_by('-is_core', 'name')

    # Get totals using aggregate instead of Python loops
    class_stats = Class.objects.filter(is_active=True).aggregate(
        total_capacity=models.Sum('capacity')
    )
    total_students = Student.objects.filter(status='active').count()
    total_capacity = class_stats['total_capacity'] or 0

    # Recent attendance stats (last 7 days) - single aggregate query
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    attendance_stats = AttendanceRecord.objects.filter(
        session__date__gte=week_ago
    ).aggregate(
        total_records=Count('id'),
        present_count=Count('id', filter=models.Q(status__in=['P', 'L']))
    )
    total_records = attendance_stats['total_records'] or 0
    present_count = attendance_stats['present_count'] or 0
    attendance_rate = round((present_count / total_records) * 100, 1) if total_records > 0 else 0

    # Setup status for checklist
    periods_count = Period.objects.filter(is_active=True).count()
    classrooms_count = Classroom.objects.filter(is_active=True).count()
    timetable_entries_count = TimetableEntry.objects.count()

    # Subject templates
    templates = SubjectTemplate.objects.prefetch_related('subjects').filter(is_active=True)

    context = {
        'current_term': current_term,
        'programmes': programmes,
        'subjects': subjects,
        'templates': templates,
        'classes_by_level': classes_by_level,
        'stats': {
            'total_classes': classes.count(),
            'total_subjects': subjects.count(),
            'total_programmes': programmes.count(),
            'total_students': total_students,
            'total_capacity': total_capacity,
            'attendance_rate': attendance_rate,
        },
        'setup': {
            'periods': periods_count,
            'classrooms': classrooms_count,
            'timetable_entries': timetable_entries_count,
        },
        'programme_form': ProgrammeForm(),
        'subject_form': SubjectForm(),
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Academics'},
        ],
    }

    return htmx_render(
        request,
        'academics/index.html',
        'academics/partials/index_content.html',
        context
    )
