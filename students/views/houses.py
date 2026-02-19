"""House management views."""
import json
import logging
from io import BytesIO

from django.db.models import Count, Q, Prefetch
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone

from core.utils import requires_houses
from core.models import AcademicYear
from ..models import House, Student, HouseMaster, StudentGuardian
from ..forms import HouseForm
from .utils import admin_required, htmx_render

logger = logging.getLogger(__name__)


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
            housemaster_map.setdefault(assignment.house_id, []).append(assignment)

    # Attach housemasters to each house
    for house in houses:
        house.current_housemasters = housemaster_map.get(house.pk, [])

    # Get aggregate stats in a single query instead of iterating
    total_houses = houses.count()
    active_houses = houses.filter(is_active=True).count()
    total_students = Student.objects.filter(
        status='active', house__isnull=False
    ).count()

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

    return htmx_render(
        request,
        'students/houses.html',
        'students/partials/houses_content.html',
        context,
    )


@login_required
@admin_required
@requires_houses
def house_create(request):
    """Create a new house."""
    if request.method == 'POST':
        form = HouseForm(request.POST)
        if form.is_valid():
            house = form.save()

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = json.dumps({
                    'houseChanged': True,
                    'showToast': {'message': f'House "{house.name}" created', 'type': 'success'}
                })
                return response
            messages.success(request, f'House "{house.name}" created successfully.')
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

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = json.dumps({
                    'houseChanged': True,
                    'showToast': {'message': f'House "{house.name}" updated', 'type': 'success'}
                })
                return response
            messages.success(request, f'House "{house.name}" updated successfully.')
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
            error_msg = (
                f'Cannot delete "{house.name}": {student_count} active student(s) assigned. '
                'Reassign students first.'
            )
            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = json.dumps({
                    'showToast': {'message': error_msg, 'type': 'error'}
                })
                return response
            messages.error(request, error_msg)
        else:
            name = house.name
            house.delete()

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = json.dumps({
                    'houseChanged': True,
                    'showToast': {'message': f'House "{name}" deleted', 'type': 'success'}
                })
                return response
            messages.success(request, f'House "{name}" deleted.')

        return redirect('students:houses')

    return HttpResponse(status=405)


@login_required
@admin_required
@requires_houses
def house_assign_master(request, pk):
    """Assign a housemaster to a house."""
    house = get_object_or_404(House, pk=pk)
    current_year = AcademicYear.get_current()
    is_htmx = request.headers.get('HX-Request')

    if not current_year:
        error_msg = "No active academic year. Cannot assign housemaster."
        if is_htmx:
            response = HttpResponse(status=204)
            response['HX-Trigger'] = json.dumps({
                'showToast': {'message': error_msg, 'type': 'error'}
            })
            return response
        messages.error(request, error_msg)
        return redirect('students:houses')

    if request.method == 'POST':
        teacher_id = request.POST.get('teacher')
        is_senior = request.POST.get('is_senior') == 'true'
        toast_msg = None
        toast_type = 'success'

        if not teacher_id:
            toast_msg = "Please select a teacher."
            toast_type = 'error'
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
                toast_msg = f"{teacher.full_name} is already assigned to {existing.house.name}."
                toast_type = 'error'
            else:
                # Check if teacher already assigned to this house
                already_assigned = HouseMaster.objects.filter(
                    teacher=teacher,
                    house=house,
                    academic_year=current_year,
                    is_active=True
                ).exists()

                if already_assigned:
                    toast_msg = f"{teacher.full_name} is already assigned to {house.name}."
                    toast_type = 'error'
                else:
                    # Check if marking as senior when another senior exists
                    if is_senior:
                        existing_senior = HouseMaster.objects.filter(
                            academic_year=current_year,
                            is_senior=True,
                            is_active=True
                        ).first()
                        if existing_senior:
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
                    toast_msg = f"{teacher.full_name} assigned as {'senior ' if is_senior else ''}housemaster for {house.name}."

        if is_htmx:
            if toast_type == 'error':
                # Error: return 204 with toast only
                response = HttpResponse(status=204)
                response['HX-Trigger'] = json.dumps({
                    'showToast': {'message': toast_msg, 'type': toast_type}
                })
                return response

            # Success: re-render modal content so user can add more
            from teachers.models import Teacher
            teachers = Teacher.objects.filter(
                status='active'
            ).select_related('user').order_by('last_name', 'first_name')
            current_assignments = HouseMaster.objects.filter(
                house=house,
                academic_year=current_year,
                is_active=True
            ).select_related('teacher')
            context = {
                'house': house,
                'teachers': teachers,
                'current_assignments': current_assignments,
                'current_year': current_year,
                'toast_message': toast_msg,
            }
            response = render(request, 'students/partials/house_assign_master.html', context)
            response['HX-Trigger'] = json.dumps({
                'showToast': {'message': toast_msg, 'type': 'success'}
            })
            return response

        if toast_type == 'error':
            messages.error(request, toast_msg)
        else:
            messages.success(request, toast_msg)
        return redirect('students:houses')

    # GET request - show form
    from teachers.models import Teacher
    teachers = Teacher.objects.filter(
        status='active'
    ).select_related('user').order_by('last_name', 'first_name')

    # Get current assignments for this house
    current_assignments = HouseMaster.objects.filter(
        house=house,
        academic_year=current_year,
        is_active=True
    ).select_related('teacher')

    context = {
        'house': house,
        'teachers': teachers,
        'current_assignments': current_assignments,
        'current_year': current_year,
    }

    return render(request, 'students/partials/house_assign_master.html', context)


@login_required
@admin_required
@requires_houses
def house_remove_master(request, pk):
    """Remove a specific housemaster assignment."""
    assignment = get_object_or_404(
        HouseMaster.objects.select_related('teacher', 'house'), pk=pk
    )

    if request.method == 'POST':
        teacher_name = assignment.teacher.full_name
        house = assignment.house
        house_name = house.name
        current_year = assignment.academic_year
        assignment.delete()

        msg = f"{teacher_name} removed from {house_name}."

        if request.headers.get('HX-Request'):
            # Re-render the modal content so user can continue managing
            from teachers.models import Teacher
            teachers = Teacher.objects.filter(
                status='active'
            ).select_related('user').order_by('last_name', 'first_name')
            current_assignments = HouseMaster.objects.filter(
                house=house,
                academic_year=current_year,
                is_active=True
            ).select_related('teacher')
            context = {
                'house': house,
                'teachers': teachers,
                'current_assignments': current_assignments,
                'current_year': current_year,
            }
            response = render(request, 'students/partials/house_assign_master.html', context)
            response['HX-Trigger'] = json.dumps({
                'showToast': {'message': msg, 'type': 'success'}
            })
            response['HX-Retarget'] = '#modal-housemaster-content'
            response['HX-Reswap'] = 'innerHTML'
            return response

        messages.success(request, msg)
        return redirect('students:houses')

    return HttpResponse(status=405)


@login_required
@admin_required
@requires_houses
def house_students(request, pk):
    """View all students in a house."""
    house = get_object_or_404(House, pk=pk)

    students = Student.objects.filter(
        house=house,
        status='active'
    ).select_related('current_class').prefetch_related(
        Prefetch(
            'student_guardians',
            queryset=StudentGuardian.objects.filter(is_primary=True).select_related('guardian'),
            to_attr='primary_guardian_list'
        )
    ).order_by('last_name', 'first_name')

    # Get gender counts for stats
    gender_counts = students.aggregate(
        male_count=Count('id', filter=Q(gender='M')),
        female_count=Count('id', filter=Q(gender='F'))
    )

    # Get housemasters
    current_year = AcademicYear.get_current()
    housemasters = []
    if current_year:
        assignments = HouseMaster.objects.filter(
            house=house,
            academic_year=current_year,
            is_active=True
        ).select_related('teacher')
        housemasters = assignments

    context = {
        'house': house,
        'students': students,
        'housemasters': housemasters,
        'male_count': gender_counts['male_count'],
        'female_count': gender_counts['female_count'],
        'current_year': current_year,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Students', 'url': '/students/'},
            {'label': 'Houses', 'url': '/students/houses/'},
            {'label': house.name},
        ],
    }

    return htmx_render(
        request,
        'students/house_students.html',
        'students/partials/house_students_content.html',
        context,
    )


@login_required
@admin_required
@requires_houses
def house_students_pdf(request, pk):
    """Export house students list as PDF."""
    from django.template.loader import render_to_string
    from django.db import connection
    from weasyprint import HTML, CSS

    house = get_object_or_404(House, pk=pk)

    students = Student.objects.filter(
        house=house,
        status='active'
    ).select_related('current_class').prefetch_related(
        Prefetch(
            'student_guardians',
            queryset=StudentGuardian.objects.filter(is_primary=True).select_related('guardian'),
            to_attr='primary_guardian_list'
        )
    ).order_by('last_name', 'first_name')

    # Get school from tenant
    school = getattr(connection, 'tenant', None)
    current_year = AcademicYear.get_current()

    housemasters = []
    if current_year:
        assignments = HouseMaster.objects.filter(
            house=house,
            academic_year=current_year,
            is_active=True
        ).select_related('teacher')
        housemasters = assignments

    # Build absolute URL for logo
    logo_url = None
    if school and school.logo:
        logo_url = request.build_absolute_uri(school.logo.url)

    context = {
        'house': house,
        'students': students,
        'school': school,
        'logo_url': logo_url,
        'housemasters': housemasters,
        'current_year': current_year,
        'generated_at': timezone.now(),
        'generated_by': request.user,
        'total_students': students.count(),
    }

    html_string = render_to_string('students/reports/house_students_pdf.html', context)
    html = HTML(string=html_string)

    pdf_buffer = BytesIO()
    css = CSS(string='''
        @page { size: A4; margin: 1.5cm; }
        body { font-family: Arial, sans-serif; font-size: 10pt; }
        h1 { font-size: 16pt; margin-bottom: 5px; }
        h2 { font-size: 12pt; color: #666; margin-bottom: 15px; }
        .header { text-align: center; margin-bottom: 20px; border-bottom: 2px solid #333; padding-bottom: 10px; }
        .info-row { margin-bottom: 10px; font-size: 9pt; color: #666; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
        th { background-color: #f5f5f5; font-weight: bold; font-size: 9pt; }
        td { font-size: 9pt; }
        tr:nth-child(even) { background-color: #fafafa; }
        .footer { margin-top: 20px; font-size: 8pt; color: #666; text-align: center; }
        .badge { padding: 2px 6px; border-radius: 3px; font-size: 8pt; background: #e5e7eb; }
    ''')

    html.write_pdf(pdf_buffer, stylesheets=[css])
    pdf_buffer.seek(0)

    filename = f"{house.name.replace(' ', '_')}_students_{timezone.now().strftime('%Y%m%d')}.pdf"

    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@admin_required
@requires_houses
def house_students_excel(request, pk):
    """Export house students list as Excel."""
    import pandas as pd

    house = get_object_or_404(House, pk=pk)

    students = Student.objects.filter(
        house=house,
        status='active'
    ).select_related('current_class').prefetch_related(
        'student_guardians__guardian'  # Prefetch guardians to avoid N+1
    ).order_by('last_name', 'first_name')

    # Set primary guardian on each student from prefetched data
    for student in students:
        student._cached_primary_guardian = None
        for sg in student.student_guardians.all():
            if sg.is_primary:
                student._cached_primary_guardian = sg.guardian
                break

    # Build data for Excel
    data = []
    for i, student in enumerate(students, 1):
        guardian = student._cached_primary_guardian
        data.append({
            'S/N': i,
            'Admission No': student.admission_number,
            'Name': student.full_name,
            'Gender': student.get_gender_display() if student.gender else '',
            'Class': student.current_class.name if student.current_class else '',
            'Date of Birth': student.date_of_birth.strftime('%Y-%m-%d') if student.date_of_birth else '',
            'Guardian': guardian.full_name if guardian else '',
            'Guardian Phone': guardian.phone_number if guardian else '',
        })

    df = pd.DataFrame(data)

    # Create Excel file
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f'{house.name} Students', index=False)

        # Auto-adjust column widths
        worksheet = writer.sheets[f'{house.name} Students']
        for idx, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            from openpyxl.utils import get_column_letter
            worksheet.column_dimensions[get_column_letter(idx + 1)].width = min(max_len, 40)

    buffer.seek(0)

    filename = f"{house.name.replace(' ', '_')}_students_{timezone.now().strftime('%Y%m%d')}.xlsx"

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
