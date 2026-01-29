"""Programme management views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db.models import Count, Q

from core.utils import requires_programmes

from ..models import Programme
from ..forms import ProgrammeForm
from .base import admin_required


def get_programmes_list_context():
    """Get context for programmes list with stats."""
    programmes = Programme.objects.annotate(
        class_count=Count('classes', filter=Q(classes__is_active=True)),
        student_count=Count(
            'classes__students',
            filter=Q(classes__is_active=True, classes__students__status='active')
        )
    ).order_by('name')

    return {'programmes': programmes}


@admin_required
@requires_programmes
def programme_create(request):
    """Create a new programme."""
    if request.method == 'GET':
        # Return fresh form for modal
        form = ProgrammeForm()
        return render(request, 'academics/partials/modal_programme_form.html', {
            'form': form,
            'is_create': True,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ProgrammeForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/programmes_list.html', get_programmes_list_context())
            response['HX-Trigger'] = 'closeModal'
            response['HX-Reswap'] = 'outerHTML'
            response['HX-Retarget'] = '#programmes-container'
            return response
        return redirect('academics:index')

    # Validation error - show form with errors in modal
    if request.htmx:
        response = render(request, 'academics/partials/modal_programme_form.html', {
            'form': form,
            'is_create': True,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@admin_required
@requires_programmes
def programme_edit(request, pk):
    """Edit a programme."""
    programme = get_object_or_404(Programme, pk=pk)

    if request.method == 'GET':
        form = ProgrammeForm(instance=programme)
        return render(request, 'academics/partials/modal_programme_form.html', {
            'form': form,
            'programme': programme,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ProgrammeForm(request.POST, instance=programme)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/programmes_list.html', get_programmes_list_context())
            response['HX-Trigger'] = 'closeModal'
            response['HX-Reswap'] = 'outerHTML'
            response['HX-Retarget'] = '#programmes-container'
            return response
        return redirect('academics:index')

    # Validation error - show form with errors in modal
    if request.htmx:
        response = render(request, 'academics/partials/modal_programme_form.html', {
            'form': form,
            'programme': programme,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@admin_required
@requires_programmes
def programme_delete(request, pk):
    """Delete a programme."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    programme = get_object_or_404(Programme, pk=pk)
    programme.delete()

    if request.htmx:
        return render(request, 'academics/partials/programmes_list.html', get_programmes_list_context())
    return redirect('academics:index')
