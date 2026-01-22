"""House management views."""
import logging

from django.db.models import Count, Q, Sum
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse

from core.utils import requires_houses
from core.models import AcademicYear
from ..models import House, Student, HouseMaster
from ..forms import HouseForm, HouseMasterForm

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
    current_year = AcademicYear.get_current()

    # Annotate houses with student counts in a single query
    houses = House.objects.annotate(
        student_count_val=Count(
            'students',
            filter=Q(students__status='active')
        )
    ).order_by('name')

    # Get housemaster assignments for current year
    housemaster_map = {}
    if current_year:
        assignments = HouseMaster.objects.filter(
            academic_year=current_year,
            is_active=True
        ).select_related('teacher', 'house')
        for assignment in assignments:
            housemaster_map[assignment.house_id] = assignment

    # Attach housemaster to each house
    for house in houses:
        house.housemaster_assignment = housemaster_map.get(house.pk)

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

    # Get teachers for assignment dropdown
    from teachers.models import Teacher
    teachers = Teacher.objects.filter(
        status='active'
    ).select_related('user').order_by('last_name', 'first_name')

    context = {
        'houses': houses,
        'total_houses': total_houses,
        'active_houses': active_houses,
        'total_students': total_students,
        'avg_per_house': avg_per_house,
        'current_year': current_year,
        'teachers': teachers,
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


@login_required
@admin_required
@requires_houses
def house_assign_master(request, pk):
    """Assign a housemaster to a house."""
    house = get_object_or_404(House, pk=pk)
    current_year = AcademicYear.get_current()

    if not current_year:
        messages.error(request, "No active academic year. Cannot assign housemaster.")
        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'houseChanged'
            return response
        return redirect('students:houses')

    if request.method == 'POST':
        teacher_id = request.POST.get('teacher')
        is_senior = request.POST.get('is_senior') == 'true'

        if not teacher_id:
            messages.error(request, "Please select a teacher.")
        else:
            from teachers.models import Teacher
            teacher = get_object_or_404(Teacher, pk=teacher_id)

            # Check if teacher is already assigned to another house
            existing = HouseMaster.objects.filter(
                teacher=teacher,
                academic_year=current_year,
                is_active=True
            ).exclude(house=house).first()

            if existing:
                messages.error(
                    request,
                    f"{teacher.full_name} is already assigned to {existing.house.name}."
                )
            else:
                # Remove existing assignment for this house
                HouseMaster.objects.filter(
                    house=house,
                    academic_year=current_year
                ).delete()

                # Check if marking as senior when another senior exists
                if is_senior:
                    existing_senior = HouseMaster.objects.filter(
                        academic_year=current_year,
                        is_senior=True,
                        is_active=True
                    ).first()
                    if existing_senior:
                        messages.warning(
                            request,
                            f"Note: {existing_senior.teacher.full_name} was the senior housemaster. "
                            f"{teacher.full_name} is now the senior housemaster."
                        )
                        existing_senior.is_senior = False
                        existing_senior.save(update_fields=['is_senior'])

                # Create new assignment
                HouseMaster.objects.create(
                    teacher=teacher,
                    house=house,
                    academic_year=current_year,
                    is_senior=is_senior,
                    is_active=True
                )
                messages.success(
                    request,
                    f"{teacher.full_name} assigned as {'senior ' if is_senior else ''}housemaster for {house.name}."
                )

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'houseChanged'
            return response
        return redirect('students:houses')

    # GET request - show form
    from teachers.models import Teacher
    teachers = Teacher.objects.filter(
        status='active'
    ).select_related('user').order_by('last_name', 'first_name')

    # Get current assignment
    current_assignment = HouseMaster.objects.filter(
        house=house,
        academic_year=current_year,
        is_active=True
    ).select_related('teacher').first()

    context = {
        'house': house,
        'teachers': teachers,
        'current_assignment': current_assignment,
        'current_year': current_year,
    }

    return render(request, 'students/partials/house_assign_master.html', context)


@login_required
@admin_required
@requires_houses
def house_remove_master(request, pk):
    """Remove housemaster assignment from a house."""
    house = get_object_or_404(House, pk=pk)
    current_year = AcademicYear.get_current()

    if request.method == 'POST':
        deleted = HouseMaster.objects.filter(
            house=house,
            academic_year=current_year
        ).delete()[0]

        if deleted:
            messages.success(request, f"Housemaster removed from {house.name}.")
        else:
            messages.info(request, "No housemaster was assigned.")

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'houseChanged'
            return response
        return redirect('students:houses')

    return HttpResponse(status=405)
