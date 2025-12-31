import json
import io
import secrets
import string
from datetime import datetime

from django.shortcuts import render, redirect
from django.http import HttpResponse, FileResponse
from django.db import transaction
from django.contrib import messages
import pandas as pd

from accounts.models import User
from academics.models import Class
from core.models import AcademicYear
from students.models import Student, Enrollment, Guardian, StudentGuardian
from .utils import admin_required, parse_date, clean_value


EXPECTED_COLUMNS = [
    'first_name', 'last_name', 'other_names', 'date_of_birth', 'gender',
    'guardian_name', 'guardian_phone', 'guardian_email', 'guardian_relationship',
    'admission_number', 'admission_date', 'class_name',
    'student_email'  # Optional - if provided, creates a user account
]


def generate_temp_password(length=10):
    """Generate a random temporary password."""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


@admin_required
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

        # Build lookups
        class_map = {c.name: c.pk for c in Class.objects.filter(is_active=True)}
        guardian_map = {g.phone_number: g.pk for g in Guardian.objects.all()}
        existing_admissions = set(Student.objects.values_list('admission_number', flat=True))
        existing_emails = set(User.objects.values_list('email', flat=True))

        # Process rows
        all_errors = []
        valid_rows = []

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
            if class_name and class_name in class_map:
                class_pk = class_map[class_name]
            elif class_name:
                errors.append(f'Class "{class_name}" not found')

            # Validate student email (optional - for account creation)
            if student_email:
                if student_email in existing_emails:
                    errors.append(f'Email "{student_email}" already exists')
                elif '@' not in student_email:
                    errors.append(f'Invalid email format: "{student_email}"')
                else:
                    existing_emails.add(student_email)  # Track to prevent duplicates in same import

            # Find or create guardian
            guardian_pk = None
            if guardian_phone in guardian_map:
                guardian_pk = guardian_map[guardian_phone]
            elif guardian_name and guardian_phone:
                guardian, created = Guardian.objects.get_or_create(
                    phone_number=guardian_phone,
                    defaults={'full_name': guardian_name}
                )
                guardian_pk = guardian.pk
                guardian_map[guardian_phone] = guardian_pk

            if errors:
                all_errors.append({'row': row_num, 'errors': errors})
            else:
                valid_rows.append({
                    'row_num': row_num,
                    'first_name': first_name,
                    'last_name': last_name,
                    'other_names': other_names,
                    'date_of_birth': str(date_of_birth),
                    'gender': gender,
                    'admission_number': admission_number,
                    'admission_date': str(admission_date),
                    'class_name': class_name,
                    'class_pk': class_pk,
                    'guardian_pk': guardian_pk,
                    'guardian_name': guardian_name,
                    'guardian_relationship': guardian_relationship,
                    'student_email': student_email,  # Optional - for account creation
                })
                existing_admissions.add(admission_number)

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


@admin_required
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
    accounts_created = 0
    errors = []

    # Collect all guardian and class PKs for bulk fetching
    guardian_pks = [row['guardian_pk'] for row in rows if row.get('guardian_pk')]
    class_pks = [row['class_pk'] for row in rows if row.get('class_pk')]

    # Bulk fetch guardians and classes (2 queries instead of N*2)
    guardians_dict = {
        g.pk: g for g in Guardian.objects.filter(pk__in=guardian_pks)
    }
    classes_dict = {
        c.pk: c for c in Class.objects.filter(pk__in=class_pks)
    }

    # Get current academic year once
    current_year = AcademicYear.get_current()

    students_to_create = []
    student_guardian_data = []  # Store (row_index, guardian_pk, relationship) for later
    student_account_data = []  # Store (row_index, email) for account creation

    for idx, row in enumerate(rows):
        try:
            current_class = classes_dict.get(row['class_pk']) if row.get('class_pk') else None

            students_to_create.append(Student(
                first_name=row['first_name'],
                last_name=row['last_name'],
                other_names=row.get('other_names', ''),
                date_of_birth=datetime.strptime(row['date_of_birth'], '%Y-%m-%d').date(),
                gender=row['gender'],
                admission_number=row['admission_number'],
                admission_date=datetime.strptime(row['admission_date'], '%Y-%m-%d').date(),
                current_class=current_class,
                status='active',
                is_active=True,
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
        'student_email': ['john.doe@school.com', ''],  # Optional - creates portal account if provided
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
