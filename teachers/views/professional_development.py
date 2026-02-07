"""
Professional Development views for teachers.

Provides CRUD operations for PD activities, both admin and self-service.
"""
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum, Count
from django.utils import timezone
from django.template.loader import render_to_string

from teachers.models import Teacher, ProfessionalDevelopment
from teachers.forms import ProfessionalDevelopmentForm
from .utils import admin_required, htmx_render


def get_pd_stats(teacher):
    """Calculate PD statistics for a teacher."""
    activities = ProfessionalDevelopment.objects.filter(teacher=teacher)

    total_activities = activities.count()
    completed = activities.filter(status='completed')
    total_hours = completed.aggregate(total=Sum('hours'))['total'] or 0

    # Count by type
    by_type = completed.values('activity_type').annotate(
        count=Count('id')
    ).order_by('-count')

    # Expiring certifications (within 90 days)
    today = timezone.now().date()
    expiring_soon = activities.filter(
        certificate_expiry__isnull=False,
        certificate_expiry__gt=today,
        certificate_expiry__lte=today + timezone.timedelta(days=90),
        status='completed'
    ).count()

    expired = activities.filter(
        certificate_expiry__isnull=False,
        certificate_expiry__lt=today,
        status='completed'
    ).count()

    return {
        'total_activities': total_activities,
        'completed_count': completed.count(),
        'total_hours': total_hours,
        'by_type': list(by_type),
        'expiring_soon': expiring_soon,
        'expired': expired,
    }


@admin_required
def pd_list(request, pk):
    """Admin view: List all PD activities for a teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)

    activities = ProfessionalDevelopment.objects.filter(
        teacher=teacher
    ).order_by('-start_date')

    stats = get_pd_stats(teacher)

    context = {
        'teacher': teacher,
        'activities': activities,
        'stats': stats,
    }

    return htmx_render(
        request,
        'teachers/partials/tab_pd.html',
        'teachers/partials/tab_pd.html',
        context
    )


@admin_required
def pd_create(request, pk):
    """Admin view: Create a new PD activity for a teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)

    if request.method == 'POST':
        form = ProfessionalDevelopmentForm(request.POST, request.FILES)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.teacher = teacher
            activity.save()
            messages.success(request, f"Added: {activity.title}")

            # Return updated list for HTMX
            if request.htmx:
                activities = ProfessionalDevelopment.objects.filter(teacher=teacher).order_by('-start_date')
                stats = get_pd_stats(teacher)
                html = render_to_string(
                    'teachers/partials/tab_pd.html',
                    {'teacher': teacher, 'activities': activities, 'stats': stats},
                    request
                )
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('teachers:teacher_detail', pk=pk)
    else:
        form = ProfessionalDevelopmentForm()

    context = {
        'form': form,
        'teacher': teacher,
        'is_edit': False,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_pd_form.html',
        'teachers/partials/modal_pd_form.html',
        context
    )


@admin_required
def pd_edit(request, pk, pd_pk):
    """Admin view: Edit a PD activity."""
    teacher = get_object_or_404(Teacher, pk=pk)
    activity = get_object_or_404(ProfessionalDevelopment, pk=pd_pk, teacher=teacher)

    if request.method == 'POST':
        form = ProfessionalDevelopmentForm(request.POST, request.FILES, instance=activity)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated: {activity.title}")

            if request.htmx:
                activities = ProfessionalDevelopment.objects.filter(teacher=teacher).order_by('-start_date')
                stats = get_pd_stats(teacher)
                html = render_to_string(
                    'teachers/partials/tab_pd.html',
                    {'teacher': teacher, 'activities': activities, 'stats': stats},
                    request
                )
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('teachers:teacher_detail', pk=pk)
    else:
        form = ProfessionalDevelopmentForm(instance=activity)

    context = {
        'form': form,
        'teacher': teacher,
        'activity': activity,
        'is_edit': True,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_pd_form.html',
        'teachers/partials/modal_pd_form.html',
        context
    )


@admin_required
def pd_delete(request, pk, pd_pk):
    """Admin view: Delete a PD activity."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)
    activity = get_object_or_404(ProfessionalDevelopment, pk=pd_pk, teacher=teacher)

    title = activity.title
    activity.delete()
    messages.success(request, f"Deleted: {title}")

    if request.htmx:
        activities = ProfessionalDevelopment.objects.filter(teacher=teacher)
        stats = get_pd_stats(teacher)
        return htmx_render(
            request,
            'teachers/partials/tab_pd.html',
            'teachers/partials/tab_pd.html',
            {'teacher': teacher, 'activities': activities, 'stats': stats}
        )

    return redirect('teachers:teacher_detail', pk=pk)


# Teacher self-service views

@login_required
def my_pd(request):
    """Teacher self-service: View own PD activities."""
    teacher = get_object_or_404(Teacher, user=request.user)

    activities = ProfessionalDevelopment.objects.filter(
        teacher=teacher
    ).order_by('-start_date')

    stats = get_pd_stats(teacher)

    context = {
        'teacher': teacher,
        'activities': activities,
        'stats': stats,
        'is_self_service': True,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'My Professional Development'},
        ],
        'back_url': '/',
    }

    return htmx_render(
        request,
        'teachers/my_pd.html',
        'teachers/partials/my_pd_content.html',
        context
    )


@login_required
def my_pd_create(request):
    """Teacher self-service: Add a new PD activity."""
    teacher = get_object_or_404(Teacher, user=request.user)

    if request.method == 'POST':
        form = ProfessionalDevelopmentForm(request.POST, request.FILES)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.teacher = teacher
            activity.save()
            messages.success(request, f"Added: {activity.title}")

            if request.htmx:
                activities = ProfessionalDevelopment.objects.filter(teacher=teacher).order_by('-start_date')
                html = render_to_string('teachers/partials/my_pd_inner.html', {'activities': activities}, request)
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('core:my_pd')
    else:
        form = ProfessionalDevelopmentForm()

    context = {
        'form': form,
        'teacher': teacher,
        'is_edit': False,
        'is_self_service': True,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_pd_form.html',
        'teachers/partials/modal_pd_form.html',
        context
    )


@login_required
def my_pd_edit(request, pd_pk):
    """Teacher self-service: Edit own PD activity."""
    teacher = get_object_or_404(Teacher, user=request.user)
    activity = get_object_or_404(ProfessionalDevelopment, pk=pd_pk, teacher=teacher)

    if request.method == 'POST':
        form = ProfessionalDevelopmentForm(request.POST, request.FILES, instance=activity)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated: {activity.title}")

            if request.htmx:
                activities = ProfessionalDevelopment.objects.filter(teacher=teacher).order_by('-start_date')
                html = render_to_string('teachers/partials/my_pd_inner.html', {'activities': activities}, request)
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('core:my_pd')
    else:
        form = ProfessionalDevelopmentForm(instance=activity)

    context = {
        'form': form,
        'teacher': teacher,
        'activity': activity,
        'is_edit': True,
        'is_self_service': True,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_pd_form.html',
        'teachers/partials/modal_pd_form.html',
        context
    )


@login_required
def my_pd_delete(request, pd_pk):
    """Teacher self-service: Delete own PD activity."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, user=request.user)
    activity = get_object_or_404(ProfessionalDevelopment, pk=pd_pk, teacher=teacher)

    title = activity.title
    activity.delete()
    messages.success(request, f"Deleted: {title}")

    if request.htmx:
        activities = ProfessionalDevelopment.objects.filter(teacher=teacher).order_by('-start_date')
        return htmx_render(
            request,
            'teachers/partials/my_pd_inner.html',
            'teachers/partials/my_pd_inner.html',
            {'activities': activities}
        )

    return redirect('core:my_pd')
