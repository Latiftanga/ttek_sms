from django.shortcuts import get_object_or_404

from teachers.models import Teacher
from academics.models import Period, TimetableEntry
from .utils import admin_required, htmx_render


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
