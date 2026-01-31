"""Timetable management views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages

from ..models import Class, ClassSubject, TimetableEntry, Period
from ..forms import TimetableEntryForm, BulkTimetableEntryForm, CopyTimetableForm
from .base import admin_required


@login_required
@admin_required
def timetable_index(request):
    """Timetable overview - select a class to view/edit."""
    classes = Class.objects.filter(is_active=True).order_by('level_number', 'name')
    periods_count = Period.objects.filter(is_active=True).count()

    context = {
        'classes': classes,
        'periods_count': periods_count,
        'active_tab': 'timetable',
    }

    if request.headers.get('HX-Request'):
        return render(request, 'academics/partials/timetable_index_content.html', context)
    return render(request, 'academics/timetable_index.html', context)


@login_required
@admin_required
def class_timetable(request, class_id):
    """View and manage timetable for a specific class."""
    from core.models import SchoolSettings, Term

    class_obj = get_object_or_404(Class, pk=class_id)
    periods_list = list(Period.objects.filter(is_active=True).order_by('order'))
    weekdays = TimetableEntry.Weekday.choices

    # Get all timetable entries for this class
    entries = TimetableEntry.objects.filter(
        class_subject__class_assigned=class_obj
    ).select_related('class_subject__subject', 'class_subject__teacher', 'period', 'classroom')

    # Build timetable grid: {weekday: {period_id: [entries]}}
    # Supports multiple entries per slot for combined/split lessons (e.g., Gov/Hist)
    # Also track which slots are occupied by double periods from previous period
    timetable_grid = {}
    double_period_slots = {}  # {weekday: {period_id: [entries]}} - slots occupied by double periods

    # Create period order lookup for finding next period
    period_order_map = {p.pk: i for i, p in enumerate(periods_list)}

    for entry in entries:
        if entry.weekday not in timetable_grid:
            timetable_grid[entry.weekday] = {}
            double_period_slots[entry.weekday] = {}

        # Store entries as a list to support combined lessons (e.g., Gov/Hist)
        if entry.period_id not in timetable_grid[entry.weekday]:
            timetable_grid[entry.weekday][entry.period_id] = []
        timetable_grid[entry.weekday][entry.period_id].append(entry)

        # If it's a double period, mark the next period slot as occupied
        if entry.is_double:
            current_idx = period_order_map.get(entry.period_id, -1)
            if current_idx >= 0 and current_idx + 1 < len(periods_list):
                next_period = periods_list[current_idx + 1]
                # Only mark if next period is not a break
                if not next_period.is_break:
                    if next_period.pk not in double_period_slots[entry.weekday]:
                        double_period_slots[entry.weekday][next_period.pk] = []
                    double_period_slots[entry.weekday][next_period.pk].append(entry)

    # Get class subjects for the add entry form
    class_subjects = ClassSubject.objects.filter(
        class_assigned=class_obj
    ).select_related('subject', 'teacher')

    # Calculate scheduled periods per subject from timetable entries
    scheduled_periods = {}
    for entry in entries:
        subject_id = entry.class_subject.subject_id
        # Double periods count as 2
        periods = 2 if entry.is_double else 1
        scheduled_periods[subject_id] = scheduled_periods.get(subject_id, 0) + periods

    # Add scheduled count to class_subjects
    class_subjects_with_scheduled = []
    for cs in class_subjects:
        cs.scheduled_periods = scheduled_periods.get(cs.subject_id, 0)
        class_subjects_with_scheduled.append(cs)

    # Calculate stats for the timetable page
    timetable_entries_count = entries.count()
    teachers_count = class_subjects.exclude(teacher__isnull=True).values('teacher').distinct().count()
    teaching_periods_count = sum(1 for p in periods_list if not p.is_break)

    # Get school settings and current term for print header
    school = SchoolSettings.load()
    current_term = Term.get_current()

    context = {
        'class_obj': class_obj,
        'periods': periods_list,
        'weekdays': weekdays,
        'timetable_grid': timetable_grid,
        'double_period_slots': double_period_slots,
        'class_subjects': class_subjects_with_scheduled,
        'timetable_entries_count': timetable_entries_count,
        'teachers_count': teachers_count,
        'teaching_periods_count': teaching_periods_count,
        'active_tab': 'timetable',
        'school': school,
        'current_term': current_term,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'academics/partials/class_timetable_content.html', context)
    return render(request, 'academics/class_timetable.html', context)


@login_required
@admin_required
def timetable_entry_create(request, class_id):
    """Create a new timetable entry for a class."""
    class_obj = get_object_or_404(Class, pk=class_id)

    # Get selected period and day for display
    selected_period = None
    selected_day_name = None
    weekday_choices = dict(TimetableEntry.Weekday.choices)

    if request.method == 'POST':
        form = TimetableEntryForm(request.POST, class_instance=class_obj)

        # Get period and day for error display
        if 'period' in request.POST:
            selected_period = Period.objects.filter(pk=request.POST['period']).first()
        if 'weekday' in request.POST:
            selected_day_name = weekday_choices.get(int(request.POST['weekday']), '')

        # Check for existing entries to determine if this is a combined lesson slot
        existing_is_double = None
        if selected_period and 'weekday' in request.POST:
            existing_entry = TimetableEntry.objects.filter(
                class_subject__class_assigned=class_obj,
                period=selected_period,
                weekday=request.POST['weekday']
            ).first()
            if existing_entry:
                existing_is_double = existing_entry.is_double

        if form.is_valid():
            entry = form.save()
            messages.success(request, f'Timetable entry added: {entry.class_subject.subject.name} on {entry.get_weekday_display()}')

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'timetableChanged'
                return response
            return redirect('academics:class_timetable', class_id=class_id)
        else:
            # Return form with errors
            if request.headers.get('HX-Request'):
                context = {
                    'form': form,
                    'class_obj': class_obj,
                    'weekdays': TimetableEntry.Weekday.choices,
                    'selected_period': selected_period,
                    'selected_day_name': selected_day_name,
                    'existing_is_double': existing_is_double,
                }
                return render(request, 'academics/partials/modal_timetable_entry_form.html', context)
    else:
        # Pre-fill from query params if provided
        initial = {}
        existing_is_double = None  # Track if slot has existing entries

        if 'weekday' in request.GET:
            initial['weekday'] = request.GET['weekday']
            selected_day_name = weekday_choices.get(int(request.GET['weekday']), '')
        if 'period' in request.GET:
            initial['period'] = request.GET['period']
            selected_period = Period.objects.filter(pk=request.GET['period']).first()

            # Check if there are existing entries in this slot
            if 'weekday' in request.GET and selected_period:
                existing_entry = TimetableEntry.objects.filter(
                    class_subject__class_assigned=class_obj,
                    period=selected_period,
                    weekday=request.GET['weekday']
                ).first()
                if existing_entry:
                    # Auto-set is_double to match existing entries
                    initial['is_double'] = existing_entry.is_double
                    existing_is_double = existing_entry.is_double

        form = TimetableEntryForm(class_instance=class_obj, initial=initial)

    context = {
        'form': form,
        'class_obj': class_obj,
        'weekdays': TimetableEntry.Weekday.choices,
        'selected_period': selected_period,
        'selected_day_name': selected_day_name,
        'existing_is_double': existing_is_double,  # None if empty slot, True/False if has entries
    }

    if request.headers.get('HX-Request'):
        return render(request, 'academics/partials/modal_timetable_entry_form.html', context)
    return render(request, 'academics/timetable_entry_form.html', context)


@login_required
@admin_required
def bulk_timetable_entry(request, class_id):
    """
    Add multiple timetable entries at once.
    Select subject, teacher, and multiple days for the same period.
    """
    class_obj = get_object_or_404(Class, pk=class_id)

    if request.method == 'POST':
        form = BulkTimetableEntryForm(request.POST, class_instance=class_obj)

        if form.is_valid():
            created_count = form.save()
            messages.success(request, f'{created_count} timetable entries added.')

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'timetableChanged'
                return response
            return redirect('academics:class_timetable', class_id=class_id)
    else:
        form = BulkTimetableEntryForm(class_instance=class_obj)

    context = {
        'form': form,
        'class_obj': class_obj,
    }

    return render(request, 'academics/partials/modal_bulk_timetable_form.html', context)


@login_required
@admin_required
def copy_timetable(request, class_id):
    """
    Copy timetable from another class.
    Useful for parallel classes (e.g., Form 1A -> Form 1B).
    """
    class_obj = get_object_or_404(Class, pk=class_id)

    if request.method == 'POST':
        form = CopyTimetableForm(request.POST, target_class=class_obj)

        if form.is_valid():
            created_count, skipped_count = form.save()
            source = form.cleaned_data['source_class']

            if created_count > 0:
                msg = f'Copied {created_count} entries from {source.name}.'
                if skipped_count > 0:
                    msg += f' ({skipped_count} skipped due to conflicts)'
                messages.success(request, msg)
            else:
                messages.warning(request, 'No entries were copied (all slots had conflicts).')

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'timetableChanged'
                return response
            return redirect('academics:class_timetable', pk=class_id)
    else:
        form = CopyTimetableForm(target_class=class_obj)

    # Check if there are any classes with timetables to copy from
    has_sources = form.fields['source_class'].queryset.exists()

    context = {
        'form': form,
        'class_obj': class_obj,
        'has_sources': has_sources,
    }

    return render(request, 'academics/partials/modal_copy_timetable.html', context)


@login_required
@admin_required
def timetable_entry_edit(request, pk):
    """Edit an existing timetable entry."""
    entry = get_object_or_404(
        TimetableEntry.objects.select_related(
            'class_subject__class_assigned',
            'class_subject__subject',
            'class_subject__teacher',
            'period',
            'classroom'
        ),
        pk=pk
    )
    class_obj = entry.class_subject.class_assigned
    weekday_choices = dict(TimetableEntry.Weekday.choices)

    if request.method == 'POST':
        form = TimetableEntryForm(request.POST, instance=entry, class_instance=class_obj)

        if form.is_valid():
            form.save()
            messages.success(request, f'Updated {entry.class_subject.subject.name} on {entry.get_weekday_display()}')

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'timetableChanged'
                return response
            return redirect('academics:class_timetable', class_id=class_obj.pk)
        else:
            # Return form with errors
            if request.headers.get('HX-Request'):
                context = {
                    'form': form,
                    'entry': entry,
                    'class_obj': class_obj,
                    'weekdays': TimetableEntry.Weekday.choices,
                    'selected_period': entry.period,
                    'selected_day_name': weekday_choices.get(entry.weekday, ''),
                    'is_edit': True,
                }
                return render(request, 'academics/partials/modal_timetable_entry_form.html', context)
    else:
        form = TimetableEntryForm(instance=entry, class_instance=class_obj)

    context = {
        'form': form,
        'entry': entry,
        'class_obj': class_obj,
        'weekdays': TimetableEntry.Weekday.choices,
        'selected_period': entry.period,
        'selected_day_name': weekday_choices.get(entry.weekday, ''),
        'is_edit': True,
    }

    if request.headers.get('HX-Request'):
        return render(request, 'academics/partials/modal_timetable_entry_form.html', context)
    return render(request, 'academics/timetable_entry_form.html', context)


@login_required
@admin_required
def timetable_entry_delete(request, pk):
    """Delete a timetable entry."""
    entry = get_object_or_404(TimetableEntry, pk=pk)
    class_id = entry.class_subject.class_assigned_id

    if request.method == 'POST':
        subject_name = entry.class_subject.subject.name
        day_name = entry.get_weekday_display()
        entry.delete()
        messages.success(request, f'Removed {subject_name} from {day_name}')

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'timetableChanged'
            return response
        return redirect('academics:class_timetable', class_id=class_id)

    return HttpResponse(status=405)


@login_required
@admin_required
def teacher_schedule_preview(request):
    """
    Return a compact preview of teacher's schedule for the day.
    Used via HTMX when selecting a teacher in timetable entry form.
    """
    from teachers.models import Teacher

    teacher_id = request.GET.get('teacher')
    weekday = request.GET.get('weekday')

    if not teacher_id:
        return HttpResponse('')

    teacher = get_object_or_404(Teacher, pk=teacher_id)

    if weekday is None:
        return HttpResponse('<div class="text-xs text-base-content/50">Select a day to see schedule</div>')

    weekday = int(weekday)
    weekday_name = dict(TimetableEntry.Weekday.choices).get(weekday, '')

    # Get teacher's entries for this day
    entries = TimetableEntry.objects.filter(
        class_subject__teacher=teacher,
        weekday=weekday
    ).select_related(
        'class_subject__class_assigned',
        'class_subject__subject',
        'period'
    ).order_by('period__order')

    context = {
        'teacher': teacher,
        'entries': entries,
        'weekday_name': weekday_name,
    }

    return render(request, 'academics/partials/teacher_schedule_preview.html', context)
