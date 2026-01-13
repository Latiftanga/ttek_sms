import json
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db.models import Q, Count
from django.contrib import messages

from students.models import Guardian
from students.forms import GuardianForm
from .utils import admin_required, htmx_render

logger = logging.getLogger(__name__)


@admin_required
def guardian_index(request):
    """Guardian list page with search."""
    # Annotate ward_count to avoid N+1 queries in template
    guardians = Guardian.objects.annotate(
        ward_count=Count('wards', filter=Q(wards__status='active'))
    )

    search = request.GET.get('search', '').strip()
    if search:
        guardians = guardians.filter(
            Q(full_name__icontains=search) |
            Q(phone_number__icontains=search) |
            Q(email__icontains=search)
        )

    context = {
        'guardians': guardians,
        'form': GuardianForm()
    }

    return htmx_render(
        request,
        'students/guardian_index.html',
        'students/partials/guardian_list.html',
        context
    )


@admin_required
def guardian_create(request):
    """Create a new guardian."""
    if request.method == 'POST':
        form = GuardianForm(request.POST)
        if form.is_valid():
            guardian = form.save()
            messages.success(request, f'Guardian "{guardian.full_name}" created successfully.')
            if request.htmx:
                response = HttpResponse(status=204)
                response['HX-Trigger'] = json.dumps({
                    "guardianChanged": True,
                    "guardian-created": {
                        "id": guardian.id,
                        "text": f"{guardian.full_name} ({guardian.phone_number})"
                    }
                })
                return response
            return redirect('students:guardian_index')
    else:
        form = GuardianForm()

    return render(request, 'students/partials/guardian_form_content.html', {'form': form})


@admin_required
def guardian_edit(request, pk):
    """Edit a guardian."""
    guardian = get_object_or_404(Guardian, pk=pk)
    if request.method == 'POST':
        form = GuardianForm(request.POST, instance=guardian)
        if form.is_valid():
            form.save()
            messages.success(request, f'Guardian "{guardian.full_name}" updated successfully.')
            if request.htmx:
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'guardianChanged'
                return response
            return redirect('students:guardian_index')
    else:
        form = GuardianForm(instance=guardian)

    return render(request, 'students/partials/guardian_form_content.html', {
        'form': form,
        'guardian': guardian
    })


@admin_required
def guardian_delete(request, pk):
    """Delete a guardian."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    # Use prefetch to avoid extra query for wards check
    guardian = get_object_or_404(
        Guardian.objects.prefetch_related('wards'),
        pk=pk
    )

    # Check if guardian is attached to any students
    if guardian.wards.exists():
        messages.error(request, "Cannot delete guardian with associated students. Remove them from students first.")
        if request.htmx:
            guardians = Guardian.objects.annotate(
                ward_count=Count('wards', filter=Q(wards__status='active'))
            )
            return htmx_render(
                request,
                'students/guardian_index.html',
                'students/partials/guardian_list.html',
                {'guardians': guardians}
            )
        return redirect('students:guardian_index')

    try:
        name = guardian.full_name
        guardian.delete()
        messages.success(request, f'Guardian "{name}" deleted.')
    except Exception as e:
        logger.error(f"Failed to delete guardian {pk}: {e}")
        messages.error(request, "An error occurred while deleting the guardian.")

    if request.htmx:
        guardians = Guardian.objects.annotate(
            ward_count=Count('wards', filter=Q(wards__status='active'))
        )
        return htmx_render(
            request,
            'students/guardian_index.html',
            'students/partials/guardian_list.html',
            {'guardians': guardians}
        )
    return redirect('students:guardian_index')


@admin_required
def guardian_search(request):
    """Search for guardians (AJAX endpoint)."""
    query = request.GET.get('q', '').strip()
    guardians = Guardian.objects.none()
    if len(query) > 2:
        guardians = Guardian.objects.filter(
            Q(full_name__icontains=query) |
            Q(phone_number__icontains=query)
        )[:10]
    return render(request, 'students/partials/guardian_search_results.html', {
        'guardians': guardians
    })
