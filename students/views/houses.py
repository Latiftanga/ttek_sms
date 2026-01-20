"""House management views."""
import logging

from django.db.models import Count, Q, Sum
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse

from core.utils import requires_houses
from ..models import House, Student
from ..forms import HouseForm

logger = logging.getLogger(__name__)


def is_school_admin(user):
    """Check if user is a school admin or superuser."""
    return user.is_superuser or getattr(user, 'is_school_admin', False)


def admin_required(view_func):
    """Decorator to require school admin or superuser access."""
    from functools import wraps

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not is_school_admin(request.user):
            messages.error(request, "You don't have permission to access this page.")
            return redirect('core:index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@login_required
@admin_required
@requires_houses
def house_index(request):
    """List all houses with optimized queries."""
    # Annotate houses with student counts in a single query
    houses = House.objects.annotate(
        student_count_val=Count(
            'students',
            filter=Q(students__status='active')
        )
    ).order_by('name')

    # Get aggregate stats in a single query instead of iterating
    stats = House.objects.aggregate(
        total_houses=Count('id'),
        active_houses=Count('id', filter=Q(is_active=True)),
        total_students=Count('students', filter=Q(students__status='active'))
    )

    total_houses = stats['total_houses'] or 0
    active_houses = stats['active_houses'] or 0
    total_students = stats['total_students'] or 0
    avg_per_house = round(total_students / active_houses) if active_houses > 0 else 0

    context = {
        'houses': houses,
        'total_houses': total_houses,
        'active_houses': active_houses,
        'total_students': total_students,
        'avg_per_house': avg_per_house,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Students', 'url': '/students/'},
            {'label': 'Houses'},
        ],
        'back_url': '/students/',
    }

    if request.headers.get('HX-Request'):
        return render(request, 'students/partials/houses_content.html', context)
    return render(request, 'students/houses.html', context)


@login_required
@admin_required
@requires_houses
def house_create(request):
    """Create a new house."""
    if request.method == 'POST':
        form = HouseForm(request.POST)
        if form.is_valid():
            house = form.save()
            messages.success(request, f'House "{house.name}" created successfully.')

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'houseChanged'
                return response
            return redirect('students:houses')
    else:
        form = HouseForm()

    context = {
        'form': form,
        'action': 'Create',
    }

    if request.headers.get('HX-Request'):
        return render(request, 'students/partials/house_form.html', context)
    return render(request, 'students/house_form.html', context)


@login_required
@admin_required
@requires_houses
def house_edit(request, pk):
    """Edit an existing house."""
    house = get_object_or_404(House, pk=pk)

    if request.method == 'POST':
        form = HouseForm(request.POST, instance=house)
        if form.is_valid():
            form.save()
            messages.success(request, f'House "{house.name}" updated successfully.')

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'houseChanged'
                return response
            return redirect('students:houses')
    else:
        form = HouseForm(instance=house)

    context = {
        'form': form,
        'house': house,
        'action': 'Edit',
    }

    if request.headers.get('HX-Request'):
        return render(request, 'students/partials/house_form.html', context)
    return render(request, 'students/house_form.html', context)


@login_required
@admin_required
@requires_houses
def house_delete(request, pk):
    """Delete a house."""
    house = get_object_or_404(House, pk=pk)

    if request.method == 'POST':
        # Check if house has students
        student_count = house.students.filter(status='active').count()
        if student_count > 0:
            messages.error(
                request,
                f'Cannot delete "{house.name}": {student_count} active student(s) assigned. '
                'Reassign students first.'
            )
        else:
            name = house.name
            house.delete()
            messages.success(request, f'House "{name}" deleted.')

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'houseChanged'
            return response
        return redirect('students:houses')

    return HttpResponse(status=405)
