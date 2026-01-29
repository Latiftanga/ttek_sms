"""Classroom management views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import models
from django.db.models import Count
from django.contrib import messages

from ..models import Classroom
from ..forms import ClassroomForm
from .base import admin_required


@login_required
@admin_required
def classrooms(request):
    """List all classrooms."""
    classrooms_list = Classroom.objects.all().order_by('name')

    # Calculate stats using single aggregate query
    stats = Classroom.objects.aggregate(
        total_classrooms=Count('id'),
        active_classrooms=Count('id', filter=models.Q(is_active=True)),
        labs_count=Count('id', filter=models.Q(room_type__in=['lab', 'computer'])),
        total_capacity=models.Sum('capacity', filter=models.Q(is_active=True))
    )
    total_classrooms = stats['total_classrooms'] or 0
    active_classrooms = stats['active_classrooms'] or 0
    labs_count = stats['labs_count'] or 0
    total_capacity = stats['total_capacity'] or 0

    context = {
        'classrooms': classrooms_list,
        'total_classrooms': total_classrooms,
        'active_classrooms': active_classrooms,
        'labs_count': labs_count,
        'total_capacity': total_capacity,
        'active_tab': 'classrooms',
    }

    if request.headers.get('HX-Request'):
        return render(request, 'academics/partials/classrooms_content.html', context)
    return render(request, 'academics/classrooms.html', context)


@login_required
@admin_required
def classroom_create(request):
    """Create a new classroom."""
    if request.method == 'POST':
        form = ClassroomForm(request.POST)
        if form.is_valid():
            classroom = form.save()
            messages.success(request, f'Classroom "{classroom.name}" created successfully.')

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'classroomChanged'
                return response
            return redirect('academics:classrooms')
    else:
        form = ClassroomForm()

    context = {'form': form, 'action': 'Create'}

    if request.headers.get('HX-Request'):
        return render(request, 'academics/partials/classroom_form.html', context)
    return render(request, 'academics/classroom_form.html', context)


@login_required
@admin_required
def classroom_edit(request, pk):
    """Edit an existing classroom."""
    classroom = get_object_or_404(Classroom, pk=pk)

    if request.method == 'POST':
        form = ClassroomForm(request.POST, instance=classroom)
        if form.is_valid():
            form.save()
            messages.success(request, f'Classroom "{classroom.name}" updated successfully.')

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'classroomChanged'
                return response
            return redirect('academics:classrooms')
    else:
        form = ClassroomForm(instance=classroom)

    context = {'form': form, 'action': 'Edit', 'classroom': classroom}

    if request.headers.get('HX-Request'):
        return render(request, 'academics/partials/classroom_form.html', context)
    return render(request, 'academics/classroom_form.html', context)


@login_required
@admin_required
def classroom_delete(request, pk):
    """Delete a classroom."""
    classroom = get_object_or_404(Classroom, pk=pk)

    if request.method == 'POST':
        name = classroom.name
        # Check if classroom has timetable entries
        if classroom.timetable_entries.exists():
            messages.error(request, f'Cannot delete "{name}" - it is used in timetable entries. Remove them first.')
        else:
            classroom.delete()
            messages.success(request, f'Classroom "{name}" deleted successfully.')

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'classroomChanged'
            return response
    return HttpResponse(status=405)
