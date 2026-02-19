import json
import io
from datetime import datetime

from django.shortcuts import render, redirect
from django.http import HttpResponse, FileResponse
from django.db import transaction
from django.contrib import messages
import pandas as pd

from accounts.models import User
from academics.models import Class
from core.models import AcademicYear
from gradebook.utils import get_school_context
from students.models import Student, Enrollment, Guardian, StudentGuardian, House
from .utils import (
    admin_required, parse_date, clean_value, generate_temp_password,
    normalize_phone_number,
)


BASE_COLUMNS = [
    'first_name', 'middle_name', 'last_name', 'date_of_birth', 'gender',
    'guardian_name', 'guardian_phone', 'guardian_email', 'guardian_relationship',
    'admission_number', 'admission_date', 'class_name',
    'student_email'  # Optional - if provided, creates a user account
]

# Additional columns for SHS schools
SHS_COLUMNS = ['house_name', 'residence_type']


def get_expected_columns(school=None):
    """Return expected columns based on school type."""
    columns = BASE_COLUMNS.copy()
    if school and school.education_system in ('shs', 'both'):
        # Insert SHS columns before student_email
        columns = columns[:-1] + SHS_COLUMNS + [columns[-1]]
    return columns


def is_shs_school(school=None):
    """Check if school has SHS students."""
    if school is None:
        school_ctx = get_school_context()
        school = school_ctx.get('school')
    return school and school.education_system in ('shs', 'both')


@admin_required
def bulk_import(request):
    """Handle bulk import of students from Excel/CSV."""
    school_ctx = get_school_context()
    school = school_ctx.get('school')
    expected_columns = get_expected_columns(school)
    shs_school = is_shs_school(school)

    if request.method == 'GET':
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': expected_columns,
            'is_shs_school': shs_school,
        })

    # POST - process file
    if 'file' not in request.FILES:
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': expected_columns,
            'is_shs_school': shs_school,
            'error': 'Please select a file to upload.',
        })

    file = request.FILES['file']
    ext = file.name.split('.')[-1].lower()

    if ext not in ['xlsx', 'csv']:
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': expected_columns,
            'is_shs_school': shs_school,
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
                'expected_columns': expected_columns,
                'is_shs_school': shs_school,
                'error': 'The file is empty.',
            })

        # Normalize column names
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

        # Build lookups - use values_list for memory efficiency
        # Store class info with level_type for SHS detection
        class_map = {c.name: {'pk': c.pk, 'level_type': c.level_type} for c in Class.objects.filter(is_active=True)}
        guardian_map = dict(Guardian.objects.values_list('phone_number', 'pk'))
        existing_admissions = set(Student.objects.values_list('admission_number', flat=True))
        existing_emails = set(User.objects.values_list('email', flat=True))

        # SHS-specific lookups (house map needed if school has any SHS classes)
        house_map = {}
        if shs_school:
            house_map = {h.name.lower(): h.pk for h in House.objects.all()}

        # Process rows
        all_errors = []
        valid_rows = []

        for idx, row in df.iterrows():
            row_num = idx + 2  # Excel row number
            errors = []

            # Extract and clean values
            first_name = clean_value(row.get('first_name', ''))
            middle_name = clean_value(row.get('middle_name', ''))
            last_name = clean_value(row.get('last_name', ''))
            gender = clean_value(row.get('gender', '')).upper()
            guardian_name = clean_value(row.get('guardian_name', ''))
            guardian_phone = clean_value(row.get('guardian_phone', ''))
            guardian_relationship = clean_value(row.get('guardian_relationship', 'guardian')).lower()
            admission_number = clean_value(row.get('admission_number', ''))
            class_name = clean_value(row.get('class_name', ''))
            student_email = clean_value(row.get('student_email', '')).lower()

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
            # Validate guardian phone
            phone_valid, normalized_phone, phone_error = normalize_phone_number(guardian_phone)
            if not phone_valid:
                errors.append(phone_error)
            else:
                guardian_phone = normalized_phone  # Use normalized phone number
            if not admission_number:
                errors.append('Admission number is required')
            elif admission_number in existing_admissions:
                errors.append(f'Admission number "{admission_number}" already exists')
            if not admission_date:
                errors.append('Admission date is required or invalid')

            # Validate class
            class_pk = None
            class_is_shs = False
            if class_name and class_name in class_map:
                class_info = class_map[class_name]
                class_pk = class_info['pk']
                class_is_shs = class_info['level_type'] == 'shs'
            elif class_name:
                errors.append(f'Class "{class_name}" not found')

            # SHS-specific fields - only process if class is SHS level
            house_pk = None
            residence_type = ''
            if shs_school and class_is_shs:
                house_name = clean_value(row.get('house_name', '')).lower()
                residence_type = clean_value(row.get('residence_type', '')).lower()

                # Validate house (optional)
                if house_name:
                    if house_name in house_map:
                        house_pk = house_map[house_name]
                    else:
                        errors.append(f'House "{house_name}" not found')

                # Normalize residence_type (optional)
                if residence_type:
                    if residence_type in ['day', 'd']:
                        residence_type = 'day'
                    elif residence_type in ['boarding', 'b', 'boarder']:
                        residence_type = 'boarding'
                    else:
                        errors.append('Residence type must be "day" or "boarding"')

            # Validate student email (optional - for account creation)
            if student_email:
                if student_email in existing_emails:
                    errors.append(f'Email "{student_email}" already exists')
                elif '@' not in student_email:
                    errors.append(f'Invalid email format: "{student_email}"')
                else:
                    existing_emails.add(student_email)  # Track to prevent duplicates in same import

            # Look up existing guardian (defer creation to confirm step)
            guardian_pk = None
            if guardian_phone in guardian_map:
                guardian_pk = guardian_map[guardian_phone]

            if errors:
                all_errors.append({'row': row_num, 'errors': errors})
            else:
                row_data = {
                    'row_num': row_num,
                    'first_name': first_name,
                    'middle_name': middle_name,
                    'last_name': last_name,
                    'date_of_birth': str(date_of_birth),
                    'gender': gender,
                    'admission_number': admission_number,
                    'admission_date': str(admission_date),
                    'class_name': class_name,
                    'class_pk': class_pk,
                    'guardian_pk': guardian_pk,
                    'guardian_name': guardian_name,
                    'guardian_phone': guardian_phone,
                    'guardian_relationship': guardian_relationship,
                    'student_email': student_email,  # Optional - for account creation
                }
                # Add SHS fields only if class is SHS level
                if class_is_shs:
                    row_data['house_pk'] = house_pk
                    row_data['residence_type'] = residence_type

                valid_rows.append(row_data)
                existing_admissions.add(admission_number)

        request.session['bulk_import_data'] = json.dumps(valid_rows)
        request.session['bulk_import_is_shs'] = shs_school

        return render(request, 'students/partials/modal_bulk_preview.html', {
            'valid_rows': valid_rows,
            'all_errors': all_errors,
            'total_rows': len(df),
            'valid_count': len(valid_rows),
            'error_count': len(all_errors),
            'is_shs_school': shs_school,
        })

    except Exception as e:
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': expected_columns,
            'is_shs_school': shs_school,
            'error': f'Error reading file: {str(e)}',
        })


@admin_required
def bulk_import_confirm(request):
    """Confirm and process the bulk import."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    school_ctx = get_school_context()
    school = school_ctx.get('school')
    expected_columns = get_expected_columns(school)
    shs_school = request.session.get('bulk_import_is_shs', False)

    data = request.session.get('bulk_import_data')
    if not data:
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': expected_columns,
            'is_shs_school': shs_school,
            'error': 'Session expired. Please upload the file again.',
        })

    try:
        rows = json.loads(data)
    except json.JSONDecodeError:
        return render(request, 'students/partials/modal_bulk_import.html', {
            'expected_columns': expected_columns,
            'is_shs_school': shs_school,
            'error': 'Invalid session data. Please upload the file again.',
        })

    created_count = 0
    accounts_created = 0
    errors = []

    # Create guardians for rows that don't have one yet (deferred from preview)
    guardian_phone_map = {}  # phone -> guardian pk (for dedup)
    for row in rows:
        if not row.get('guardian_pk') and row.get('guardian_phone') and row.get('guardian_name'):
            phone = row['guardian_phone']
            if phone not in guardian_phone_map:
                guardian, _ = Guardian.objects.get_or_create(
                    phone_number=phone,
                    defaults={'full_name': row['guardian_name']}
                )
                guardian_phone_map[phone] = guardian.pk
            row['guardian_pk'] = guardian_phone_map[phone]

    # Collect all guardian, class, and house PKs for bulk fetching
    guardian_pks = [row['guardian_pk'] for row in rows if row.get('guardian_pk')]
    class_pks = [row['class_pk'] for row in rows if row.get('class_pk')]
    house_pks = [row['house_pk'] for row in rows if row.get('house_pk')]

    # Bulk fetch guardians, classes, and houses
    guardians_dict = {
        g.pk: g for g in Guardian.objects.filter(pk__in=guardian_pks)
    }
    classes_dict = {
        c.pk: c for c in Class.objects.filter(pk__in=class_pks)
    }
    houses_dict = {
        h.pk: h for h in House.objects.filter(pk__in=house_pks)
    } if house_pks else {}

    # Get current academic year once
    current_year = AcademicYear.get_current()

    students_to_create = []
    student_guardian_data = []  # Store (row_index, guardian_pk, relationship) for later
    student_account_data = []  # Store (row_index, email) for account creation

    for idx, row in enumerate(rows):
        try:
            current_class = classes_dict.get(row['class_pk']) if row.get('class_pk') else None
            house = houses_dict.get(row.get('house_pk')) if row.get('house_pk') else None

            students_to_create.append(Student(
                first_name=row['first_name'],
                middle_name=row.get('middle_name', ''),
                last_name=row['last_name'],
                date_of_birth=datetime.strptime(row['date_of_birth'], '%Y-%m-%d').date(),
                gender=row['gender'],
                admission_number=row['admission_number'],
                admission_date=datetime.strptime(row['admission_date'], '%Y-%m-%d').date(),
                current_class=current_class,
                house=house,
                residence_type=row.get('residence_type', ''),
                status='active',
            ))

            # Store guardian info for linking after student creation
            if row.get('guardian_pk'):
                # Get relationship from row or default to 'guardian'
                relationship = row.get('guardian_relationship', Guardian.Relationship.GUARDIAN)
                student_guardian_data.append((idx, row['guardian_pk'], relationship))

            # Store email for account creation
            if row.get('student_email'):
                student_account_data.append((idx, row['student_email'], row['first_name'], row['last_name']))

        except Exception as e:
            errors.append(f"Row {row.get('row_num', '?')}: Error preparing data - {str(e)}")

    if not errors:
        try:
            # Wrap all database operations in a transaction
            with transaction.atomic():
                # Bulk create students
                created_students = Student.objects.bulk_create(students_to_create)

                # Bulk create student-guardian relationships
                if student_guardian_data:
                    student_guardians_to_create = []
                    for idx, guardian_pk, relationship in student_guardian_data:
                        guardian = guardians_dict.get(guardian_pk)
                        if guardian and idx < len(created_students):
                            student_guardians_to_create.append(StudentGuardian(
                                student=created_students[idx],
                                guardian=guardian,
                                relationship=relationship,
                                is_primary=True,  # First guardian is primary
                                is_emergency_contact=True,
                            ))
                    if student_guardians_to_create:
                        StudentGuardian.objects.bulk_create(student_guardians_to_create)

                # Bulk create enrollments for students with a class assigned
                if current_year:
                    enrollments_to_create = [
                        Enrollment(
                            student=student,
                            academic_year=current_year,
                            class_assigned=student.current_class,
                            status=Enrollment.Status.ACTIVE,
                        )
                        for student in created_students
                        if student.current_class
                    ]
                    if enrollments_to_create:
                        Enrollment.objects.bulk_create(enrollments_to_create)

                # Create user accounts for students with emails
                if student_account_data:
                    for idx, email, first_name, last_name in student_account_data:
                        if idx < len(created_students):
                            student = created_students[idx]
                            temp_password = generate_temp_password()
                            user = User.objects.create_user(
                                email=email,
                                password=temp_password,
                                first_name=first_name,
                                last_name=last_name,
                                is_student=True,
                                must_change_password=True,
                            )
                            student.user = user
                            student.save(update_fields=['user'])
                            accounts_created += 1

                created_count = len(created_students)
        except Exception as e:
            errors.append(f"Error during bulk creation: {str(e)}")

    # Clear session
    request.session.pop('bulk_import_data', None)

    if errors:
        messages.warning(request, f"Some errors occurred: {'; '.join(errors)}")
    else:
        msg = f"{created_count} student(s) imported successfully."
        if accounts_created:
            msg += f" {accounts_created} user account(s) created."
        messages.success(request, msg)

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response

    return redirect('students:index')


@admin_required
def bulk_import_template(request):
    """Download a sample import template based on school type."""
    school_ctx = get_school_context()
    school = school_ctx.get('school')
    shs_school = is_shs_school(school)
    is_both = school and school.education_system == 'both'

    # Build sample data based on school type
    if is_both:
        # School has both Basic and SHS - show mixed examples
        sample_data = {
            'first_name': ['John', 'Jane', 'Kofi'],
            'middle_name': ['', 'Marie', ''],
            'last_name': ['Doe', 'Smith', 'Mensah'],
            'date_of_birth': ['2010-05-15', '2008-08-22', '2015-03-10'],
            'gender': ['M', 'F', 'M'],
            'guardian_name': ['James Doe', 'Mary Smith', 'Ama Mensah'],
            'guardian_phone': ['0241234567', '0551234567', '0201234567'],
            'guardian_email': ['james@email.com', '', 'ama@email.com'],
            'guardian_relationship': ['father', 'mother', 'mother'],
            'admission_number': ['STU-2024-001', 'STU-2024-002', 'STU-2024-003'],
            'admission_date': ['2024-09-01', '2024-09-01', '2024-09-01'],
            'class_name': ['1SCI-A', 'B3-A', 'B1-B'],  # SHS, Basic, Basic
            # SHS fields - only filled for SHS class (first row)
            'house_name': ['Red House', '', ''],  # Only for SHS
            'residence_type': ['boarding', '', ''],  # Only for SHS
            'student_email': ['john.doe@school.com', '', ''],
        }
    elif shs_school:
        # SHS-only school
        sample_data = {
            'first_name': ['John', 'Jane'],
            'middle_name': ['', 'Marie'],
            'last_name': ['Doe', 'Smith'],
            'date_of_birth': ['2008-05-15', '2007-08-22'],
            'gender': ['M', 'F'],
            'guardian_name': ['James Doe', 'Mary Smith'],
            'guardian_phone': ['0241234567', '0551234567'],
            'guardian_email': ['james@email.com', ''],
            'guardian_relationship': ['father', 'mother'],
            'admission_number': ['STU-2024-001', 'STU-2024-002'],
            'admission_date': ['2024-09-01', '2024-09-01'],
            'class_name': ['1SCI-A', '2BUS-B'],
            'house_name': ['Red House', 'Blue House'],
            'residence_type': ['boarding', 'day'],
            'student_email': ['john.doe@school.com', ''],
        }
    else:
        # Basic-only school
        sample_data = {
            'first_name': ['John', 'Jane'],
            'middle_name': ['', 'Marie'],
            'last_name': ['Doe', 'Smith'],
            'date_of_birth': ['2015-05-15', '2016-08-22'],
            'gender': ['M', 'F'],
            'guardian_name': ['James Doe', 'Mary Smith'],
            'guardian_phone': ['0241234567', '0551234567'],
            'guardian_email': ['james@email.com', ''],
            'guardian_relationship': ['father', 'mother'],
            'admission_number': ['STU-2024-001', 'STU-2024-002'],
            'admission_date': ['2024-09-01', '2024-09-01'],
            'class_name': ['B1-A', 'B2-A'],
            'student_email': ['', ''],
        }

    df = pd.DataFrame(sample_data)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students')

        # Add instructions sheet for schools with both levels
        if is_both:
            instructions = pd.DataFrame({
                'Instructions': [
                    'house_name and residence_type columns are ONLY for SHS classes.',
                    'Leave these columns empty for Basic/KG/Nursery students.',
                    'The system will automatically ignore these fields for non-SHS classes.',
                ]
            })
            instructions.to_excel(writer, index=False, sheet_name='Instructions')

    output.seek(0)

    # Dynamic filename based on school type
    filename = 'student_import_template.xlsx'

    return FileResponse(
        output,
        as_attachment=True,
        filename=filename,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@admin_required
def bulk_export(request):
    """Export students to Excel with current filters applied."""
    from django.db.models import Q, Prefetch

    # Get filter parameters (same as index view)
    search = request.GET.get('search', '').strip()
    class_filter = request.GET.get('class', '')
    status_filter = request.GET.get('status', '')

    # Build queryset with optimized prefetching
    students = Student.objects.select_related(
        'current_class', 'house'
    ).prefetch_related(
        Prefetch(
            'student_guardians',
            queryset=StudentGuardian.objects.filter(is_primary=True).select_related('guardian'),
            to_attr='primary_guardian_list'
        )
    )

    # Apply filters
    if search:
        students = students.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(middle_name__icontains=search) |
            Q(admission_number__icontains=search)
        )

    if class_filter:
        students = students.filter(current_class_id=class_filter)

    if status_filter:
        students = students.filter(status=status_filter)

    students = students.order_by('last_name', 'first_name')

    # Build export data
    export_data = []
    for student in students:
        # Get primary guardian info
        primary_guardian = None
        guardian_relationship = ''
        if hasattr(student, 'primary_guardian_list') and student.primary_guardian_list:
            sg = student.primary_guardian_list[0]
            primary_guardian = sg.guardian
            guardian_relationship = sg.get_relationship_display()

        export_data.append({
            'Admission Number': student.admission_number,
            'First Name': student.first_name,
            'Middle Name': student.middle_name or '',
            'Last Name': student.last_name,
            'Date of Birth': student.date_of_birth.strftime('%Y-%m-%d') if student.date_of_birth else '',
            'Gender': student.get_gender_display() if student.gender else '',
            'Phone': student.phone or '',
            'Address': student.address or '',
            'Current Class': student.current_class.name if student.current_class else '',
            'House': student.house.name if student.house else '',
            'Residence Type': student.get_residence_type_display() if student.residence_type else '',
            'Status': student.get_status_display(),
            'Admission Date': student.admission_date.strftime('%Y-%m-%d') if student.admission_date else '',
            'Guardian Name': primary_guardian.full_name if primary_guardian else '',
            'Guardian Phone': primary_guardian.phone_number if primary_guardian else '',
            'Guardian Email': primary_guardian.email or '' if primary_guardian else '',
            'Guardian Relationship': guardian_relationship,
        })

    # Create Excel file
    df = pd.DataFrame(export_data)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students')

        # Auto-adjust column widths
        worksheet = writer.sheets['Students']
        for idx, col in enumerate(df.columns):
            max_length = max(
                df[col].astype(str).map(len).max() if len(df) > 0 else 0,
                len(col)
            ) + 2
            from openpyxl.utils import get_column_letter
            worksheet.column_dimensions[get_column_letter(idx + 1)].width = min(max_length, 50)

    output.seek(0)

    # Generate filename with date
    filename = f"students_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return FileResponse(
        output,
        as_attachment=True,
        filename=filename,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
