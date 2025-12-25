import json
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, FileResponse
from django.db.models import Q
from django.contrib import messages
import pandas as pd
import io

from academics.models import Class
from core.models import AcademicYear
from .models import Student, Enrollment
from .forms import StudentForm, BulkImportForm


def create_enrollment_for_student(student, class_assigned=None):
    """Create an enrollment record for a student in the current academic year."""
    current_year = AcademicYear.get_current()
    if not current_year:
        return None

    class_to_use = class_assigned or student.current_class
    if not class_to_use:
        return None

    enrollment, created = Enrollment.objects.get_or_create(
        student=student,
        academic_year=current_year,
        defaults={
            'class_assigned': class_to_use,
            'status': Enrollment.Status.ACTIVE,
        }
    )
    return enrollment


def htmx_render(request, full_template, partial_template, context=None):
    """Render full template for regular requests, partial for HTMX requests."""
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)


@login_required
def index(request):
    """Student list page with search and filter."""
    students = Student.objects.select_related('current_class').all()

    # Search
    search = request.GET.get('search', '').strip()
    if search:
        students = students.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(other_names__icontains=search) |
            Q(admission_number__icontains=search)
        )

    # Filter by class
    class_filter = request.GET.get('class', '')
    if class_filter:
        students = students.filter(current_class_id=class_filter)

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        students = students.filter(status=status_filter)

    context = {
        'students': students,
        'classes': Class.objects.filter(is_active=True),
        'status_choices': Student.Status.choices,
        'search': search,
        'class_filter': class_filter,
        'status_filter': status_filter,
        'form': StudentForm(),
    }

    return htmx_render(
        request,
        'students/index.html',
        'students/partials/index_content.html',
        context
    )


@login_required
def student_create(request):
    """Create a new student."""
    if request.method == 'GET':
        form = StudentForm()
        return htmx_render(
            request,
            'students/student_form.html',
            'students/partials/student_form_content.html',
            {'form': form}
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = StudentForm(request.POST, request.FILES)
    if form.is_valid():
        student = form.save()
        # Auto-create enrollment for current academic year
        create_enrollment_for_student(student)
        return redirect('students:index')

    return htmx_render(
        request,
        'students/student_form.html',
        'students/partials/student_form_content.html',
        {'form': form}
    )


@login_required
def student_edit(request, pk):
    """Edit a student."""
    student = get_object_or_404(Student, pk=pk)

    if request.method == 'GET':
        form = StudentForm(instance=student)
        return htmx_render(
            request,
            'students/student_form.html',
            'students/partials/student_form_content.html',
            {'form': form, 'student': student}
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = StudentForm(request.POST, request.FILES, instance=student)
    if form.is_valid():
        form.save()
        return redirect('students:index')

    return htmx_render(
        request,
        'students/student_form.html',
        'students/partials/student_form_content.html',
        {'form': form, 'student': student}
    )


@login_required
def student_delete(request, pk):
    """Delete a student."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    student = get_object_or_404(Student, pk=pk)
    student.delete()

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('students:index')


@login_required
def student_detail(request, pk):
    """View student details."""
    student = get_object_or_404(Student.objects.select_related('current_class', 'user'), pk=pk)
    enrollments = student.get_enrollment_history()
    return htmx_render(
        request,
        'students/student_detail.html',
        'students/partials/student_detail_content.html',
        {
            'student': student,
            'enrollments': enrollments,
        }
    )


# ============ BULK IMPORT VIEWS ============

EXPECTED_COLUMNS = [
    'first_name', 'last_name', 'other_names', 'date_of_birth', 'gender',
    'guardian_name', 'guardian_phone', 'guardian_email', 'guardian_relationship',
    'admission_number', 'admission_date', 'class_name'
]


def parse_date(value):
    """Parse date from various formats."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, 'date'):  # pandas Timestamp
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def clean_value(value):
    """Clean a cell value, handling NaN and empty strings."""
    if value is None:
        return ''
    if isinstance(value, float) and pd.isna(value):
        return ''
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


@login_required
def bulk_import(request):
    """Handle bulk import of students from Excel/CSV."""
    if request.method == 'GET':
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': EXPECTED_COLUMNS,
        })

    # POST - process file
    if 'file' not in request.FILES:
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': EXPECTED_COLUMNS,
            'error': 'Please select a file to upload.',
        })

    file = request.FILES['file']
    ext = file.name.split('.')[-1].lower()

    if ext not in ['xlsx', 'csv']:
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': EXPECTED_COLUMNS,
            'error': 'Only .xlsx and .csv files are supported.',
        })

    try:
        # Read file
        if ext == 'xlsx':
            df = pd.read_excel(file, engine='openpyxl')
        else:
            df = pd.read_csv(file)

        if df.empty:
            return render(request, 'students/partials/modal_bulk_import.html', {
                'expected_columns': EXPECTED_COLUMNS,
                'error': 'The file is empty.',
            })

        # Normalize column names
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

        # Build class lookup
        class_map = {c.name: c.pk for c in Class.objects.filter(is_active=True)}

        # Process rows
        all_errors = []
        valid_rows = []
        existing_admissions = set(Student.objects.values_list('admission_number', flat=True))

        for idx, row in df.iterrows():
            row_num = idx + 2  # Excel row number
            errors = []

            # Extract and clean values
            first_name = clean_value(row.get('first_name', ''))
            last_name = clean_value(row.get('last_name', ''))
            other_names = clean_value(row.get('other_names', ''))
            gender = clean_value(row.get('gender', '')).upper()
            guardian_name = clean_value(row.get('guardian_name', ''))
            guardian_phone = clean_value(row.get('guardian_phone', ''))
            guardian_email = clean_value(row.get('guardian_email', ''))
            guardian_relationship = clean_value(row.get('guardian_relationship', 'guardian')).lower()
            admission_number = clean_value(row.get('admission_number', ''))
            class_name = clean_value(row.get('class_name', ''))

            # Parse dates
            date_of_birth = parse_date(row.get('date_of_birth'))
            admission_date = parse_date(row.get('admission_date'))

            # Normalize gender
            if gender in ['M', 'MALE']:
                gender = 'M'
            elif gender in ['F', 'FEMALE']:
                gender = 'F'
            else:
                gender = ''

            # Validate required fields
            if not first_name:
                errors.append('First name is required')
            if not last_name:
                errors.append('Last name is required')
            if not date_of_birth:
                errors.append('Date of birth is required or invalid')
            if not gender:
                errors.append('Gender must be M or F')
            if not guardian_name:
                errors.append('Guardian name is required')
            if not guardian_phone:
                errors.append('Guardian phone is required')
            if not admission_number:
                errors.append('Admission number is required')
            elif admission_number in existing_admissions:
                errors.append(f'Admission number "{admission_number}" already exists')
            if not admission_date:
                errors.append('Admission date is required or invalid')

            # Validate class
            class_pk = None
            if class_name:
                if class_name in class_map:
                    class_pk = class_map[class_name]
                else:
                    errors.append(f'Class "{class_name}" not found')

            if errors:
                all_errors.append({
                    'row': row_num,
                    'errors': errors
                })
            else:
                valid_rows.append({
                    'row_num': row_num,
                    'first_name': first_name,
                    'last_name': last_name,
                    'other_names': other_names,
                    'date_of_birth': str(date_of_birth),
                    'gender': gender,
                    'guardian_name': guardian_name,
                    'guardian_phone': guardian_phone,
                    'guardian_email': guardian_email,
                    'guardian_relationship': guardian_relationship or 'guardian',
                    'admission_number': admission_number,
                    'admission_date': str(admission_date),
                    'class_name': class_name,
                    'class_pk': class_pk,
                })
                # Track this admission number to catch duplicates within the file
                existing_admissions.add(admission_number)

        # Store in session
        request.session['bulk_import_data'] = json.dumps(valid_rows)

        return render(request, 'students/partials/modal_bulk_preview.html', {
            'valid_rows': valid_rows,
            'all_errors': all_errors,
            'total_rows': len(df),
            'valid_count': len(valid_rows),
            'error_count': len(all_errors),
        })

    except Exception as e:
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': EXPECTED_COLUMNS,
            'error': f'Error reading file: {str(e)}',
        })


@login_required
def bulk_import_confirm(request):
    """Confirm and process the bulk import."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    data = request.session.get('bulk_import_data')
    if not data:
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': EXPECTED_COLUMNS,
            'error': 'Session expired. Please upload the file again.',
        })

    try:
        rows = json.loads(data)
    except json.JSONDecodeError:
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': EXPECTED_COLUMNS,
            'error': 'Invalid session data. Please upload the file again.',
        })

    created_count = 0
    errors = []

    for row in rows:
        try:
            # Parse dates
            dob = datetime.strptime(row['date_of_birth'], '%Y-%m-%d').date()
            admission_date = datetime.strptime(row['admission_date'], '%Y-%m-%d').date()

            # Get class if specified
            current_class = None
            if row.get('class_pk'):
                try:
                    current_class = Class.objects.get(pk=row['class_pk'])
                except Class.DoesNotExist:
                    pass

            # Create student
            student = Student.objects.create(
                first_name=row['first_name'],
                last_name=row['last_name'],
                other_names=row.get('other_names', ''),
                date_of_birth=dob,
                gender=row['gender'],
                guardian_name=row['guardian_name'],
                guardian_phone=row['guardian_phone'],
                guardian_email=row.get('guardian_email', ''),
                guardian_relationship=row.get('guardian_relationship', 'guardian'),
                admission_number=row['admission_number'],
                admission_date=admission_date,
                current_class=current_class,
                status='active',
                is_active=True,
            )
            # Auto-create enrollment for current academic year
            create_enrollment_for_student(student, current_class)
            created_count += 1
        except Exception as e:
            errors.append(f"Row {row.get('row_num', '?')}: {str(e)}")

    # Clear session
    request.session.pop('bulk_import_data', None)

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response

    return redirect('students:index')


@login_required
def bulk_import_template(request):
    """Download a sample import template."""
    sample_data = {
        'first_name': ['John', 'Jane'],
        'last_name': ['Doe', 'Smith'],
        'other_names': ['', 'Marie'],
        'date_of_birth': ['2010-05-15', '2011-08-22'],
        'gender': ['M', 'F'],
        'guardian_name': ['James Doe', 'Mary Smith'],
        'guardian_phone': ['0241234567', '0551234567'],
        'guardian_email': ['james@email.com', ''],
        'guardian_relationship': ['father', 'mother'],
        'admission_number': ['STU-2024-001', 'STU-2024-002'],
        'admission_date': ['2024-09-01', '2024-09-01'],
        'class_name': ['B1-A', 'B2-A'],
    }

    df = pd.DataFrame(sample_data)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students')

    output.seek(0)
    return FileResponse(
        output,
        as_attachment=True,
        filename='student_import_template.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# ============ PROMOTION VIEWS ============

@login_required
def promotion(request):
    """Show students grouped by class for promotion."""
    current_year = AcademicYear.get_current()
    if not current_year:
        return render(request, 'students/promotion.html', {
            'error': 'No current academic year set. Please configure the academic year first.',
        })

    # Get next academic year
    next_year = AcademicYear.objects.filter(
        start_date__gt=current_year.end_date
    ).order_by('start_date').first()

    # Get all active classes with their students
    classes = Class.objects.filter(is_active=True).prefetch_related(
        'enrollments__student'
    ).order_by('programme__name', 'level_number', 'name')

    # Group students by class (only active enrollments in current year)
    class_students = []
    for cls in classes:
        students = Student.objects.filter(
            enrollments__class_assigned=cls,
            enrollments__academic_year=current_year,
            enrollments__status=Enrollment.Status.ACTIVE,
            status=Student.Status.ACTIVE
        ).select_related('current_class').order_by('last_name', 'first_name')

        if students.exists():
            # Determine if this is a final-year class (graduation eligible)
            is_final_year = (
                cls.level_type == Class.LevelType.SHS and cls.level_number == 3
            )
            class_students.append({
                'class': cls,
                'students': students,
                'count': students.count(),
                'is_final_year': is_final_year,
            })

    # Get all classes for the target dropdown
    all_classes = Class.objects.filter(is_active=True).order_by(
        'programme__name', 'level_number', 'name'
    )

    return htmx_render(
        request,
        'students/promotion.html',
        'students/partials/promotion_content.html',
        {
            'current_year': current_year,
            'next_year': next_year,
            'class_students': class_students,
            'all_classes': all_classes,
        }
    )


@login_required
def promotion_process(request):
    """Process student promotions."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    current_year = AcademicYear.get_current()
    next_year_id = request.POST.get('next_year')

    if not next_year_id:
        messages.error(request, 'Please select a target academic year.')
        return redirect('students:promotion')

    try:
        next_year = AcademicYear.objects.get(pk=next_year_id)
    except AcademicYear.DoesNotExist:
        messages.error(request, 'Invalid academic year selected.')
        return redirect('students:promotion')

    promoted_count = 0
    repeated_count = 0
    graduated_count = 0
    errors = []

    # Get all student actions from the form
    for key, value in request.POST.items():
        if key.startswith('action_'):
            student_id = key.replace('action_', '')
            action = value  # 'promote', 'repeat', or 'skip'

            if action == 'skip':
                continue

            try:
                student = Student.objects.get(pk=student_id)
                current_enrollment = student.enrollments.filter(
                    academic_year=current_year,
                    status=Enrollment.Status.ACTIVE
                ).first()

                if not current_enrollment:
                    continue

                if action == 'promote':
                    # Get target class from form
                    target_class_id = request.POST.get(f'target_class_{student_id}')
                    if not target_class_id:
                        errors.append(f'{student.full_name}: No target class selected')
                        continue

                    try:
                        target_class = Class.objects.get(pk=target_class_id)
                    except Class.DoesNotExist:
                        errors.append(f'{student.full_name}: Invalid target class')
                        continue

                    # Mark current enrollment as promoted
                    current_enrollment.status = Enrollment.Status.PROMOTED
                    current_enrollment.save()

                    # Create new enrollment
                    new_enrollment = Enrollment.objects.create(
                        student=student,
                        academic_year=next_year,
                        class_assigned=target_class,
                        status=Enrollment.Status.ACTIVE,
                        promoted_from=current_enrollment,
                    )

                    # Update student's current class
                    student.current_class = target_class
                    student.save()

                    promoted_count += 1

                elif action == 'repeat':
                    # Mark current enrollment as repeated
                    current_enrollment.status = Enrollment.Status.REPEATED
                    current_enrollment.save()

                    # Create new enrollment in same class
                    Enrollment.objects.create(
                        student=student,
                        academic_year=next_year,
                        class_assigned=current_enrollment.class_assigned,
                        status=Enrollment.Status.ACTIVE,
                        promoted_from=current_enrollment,
                        remarks='Repeated year',
                    )

                    repeated_count += 1

                elif action == 'graduate':
                    # Mark current enrollment as graduated
                    current_enrollment.status = Enrollment.Status.GRADUATED
                    current_enrollment.save()

                    # Update student status to graduated and clear current class
                    student.status = Student.Status.GRADUATED
                    student.current_class = None
                    student.save()

                    graduated_count += 1

            except Student.DoesNotExist:
                errors.append(f'Student ID {student_id}: Not found')
            except Exception as e:
                errors.append(f'Error processing student {student_id}: {str(e)}')

    # Flash messages
    if promoted_count:
        messages.success(request, f'{promoted_count} student(s) promoted successfully.')
    if repeated_count:
        messages.info(request, f'{repeated_count} student(s) set to repeat.')
    if graduated_count:
        messages.success(request, f'{graduated_count} student(s) graduated successfully.')
    if errors:
        messages.warning(request, f'{len(errors)} error(s) occurred during promotion.')

    return redirect('students:promotion')
