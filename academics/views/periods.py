"""Period management views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import models
from django.contrib import messages

from ..models import Period
from ..forms import PeriodForm
from .base import admin_required, htmx_render


@login_required
@admin_required
def periods(request):
    """List all school periods."""
    periods_list = Period.objects.order_by('order', 'start_time')

    context = {
        'periods': periods_list,
        'active_tab': 'periods',
    }

    return htmx_render(request, 'academics/periods.html', 'academics/partials/periods_content.html', context)


@login_required
@admin_required
def period_create(request):
    """Create a new period."""
    if request.method == 'POST':
        form = PeriodForm(request.POST)
        if form.is_valid():
            period = form.save()
            messages.success(request, f'Period "{period.name}" created successfully.')

            if request.htmx:
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'periodChanged'
                return response
            return redirect('academics:periods')
    else:
        # Set default order to max + 1
        max_order = Period.objects.aggregate(max_order=models.Max('order'))['max_order'] or 0
        form = PeriodForm(initial={'order': max_order + 1})

    context = {'form': form, 'action': 'Create'}

    if request.htmx:
        return render(request, 'academics/partials/modal_period_form.html', context)
    return render(request, 'academics/period_form.html', context)


@login_required
@admin_required
def period_edit(request, pk):
    """Edit an existing period."""
    period = get_object_or_404(Period, pk=pk)

    if request.method == 'POST':
        form = PeriodForm(request.POST, instance=period)
        if form.is_valid():
            form.save()
            messages.success(request, f'Period "{period.name}" updated successfully.')

            if request.htmx:
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'periodChanged'
                return response
            return redirect('academics:periods')
    else:
        form = PeriodForm(instance=period)

    context = {'form': form, 'period': period, 'action': 'Edit'}

    if request.htmx:
        return render(request, 'academics/partials/modal_period_form.html', context)
    return render(request, 'academics/period_form.html', context)


@login_required
@admin_required
def period_delete(request, pk):
    """Delete a period."""
    period = get_object_or_404(Period, pk=pk)

    if request.method == 'POST':
        name = period.name
        # Check if period has timetable entries
        if period.timetable_entries.exists():
            messages.error(request, f'Cannot delete "{name}" - it has timetable entries. Remove them first.')
        else:
            period.delete()
            messages.success(request, f'Period "{name}" deleted successfully.')

        if request.htmx:
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'periodChanged'
            return response
        return redirect('academics:periods')

    return HttpResponse(status=405)
