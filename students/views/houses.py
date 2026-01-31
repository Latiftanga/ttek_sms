"""House management views."""
import logging
from io import BytesIO

from django.db.models import Count, Q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone

from core.utils import requires_houses
from core.models import AcademicYear, SchoolSettings
from ..models import House, Student, HouseMaster
from ..forms import HouseForm
from .utils import admin_required

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


@login_required
@admin_required
@requires_houses
def house_students(request, pk):
    """View all students in a house."""
    house = get_object_or_404(House, pk=pk)

    students = Student.objects.filter(
        house=house,
        status='active'
    ).select_related('current_class').order_by('last_name', 'first_name')

    # Get gender counts for stats
    gender_counts = students.aggregate(
        male_count=Count('id', filter=Q(gender='M')),
        female_count=Count('id', filter=Q(gender='F'))
    )

    # Get housemaster
    current_year = AcademicYear.get_current()
    housemaster = None
    if current_year:
        assignment = HouseMaster.objects.filter(
            house=house,
            academic_year=current_year,
            is_active=True
        ).select_related('teacher').first()
        if assignment:
            housemaster = assignment.teacher

    context = {
        'house': house,
        'students': students,
        'housemaster': housemaster,
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

    if request.headers.get('HX-Request'):
        return render(request, 'students/partials/house_students_content.html', context)
    return render(request, 'students/house_students.html', context)


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
    ).select_related('current_class').order_by('last_name', 'first_name')

    # Get school settings and tenant info
    school = SchoolSettings.load()
    tenant = getattr(connection, 'tenant', None)
    current_year = AcademicYear.get_current()

    housemaster = None
    if current_year:
        assignment = HouseMaster.objects.filter(
            house=house,
            academic_year=current_year,
            is_active=True
        ).select_related('teacher').first()
        if assignment:
            housemaster = assignment.teacher

    # Build absolute URL for logo
    logo_url = None
    if school and school.logo:
        logo_url = request.build_absolute_uri(school.logo.url)

    context = {
        'house': house,
        'students': students,
        'school': school,
        'tenant': tenant,
        'logo_url': logo_url,
        'housemaster': housemaster,
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
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_len, 40)

    buffer.seek(0)

    filename = f"{house.name.replace(' ', '_')}_students_{timezone.now().strftime('%Y%m%d')}.xlsx"

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
