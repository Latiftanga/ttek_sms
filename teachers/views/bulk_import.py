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
from teachers.models import Teacher
from .utils import admin_required, clean_value, parse_date


EXPECTED_COLUMNS = [
    'title', 'first_name', 'last_name', 'middle_name', 'gender',
    'date_of_birth', 'staff_id', 'email', 'phone',
    'subject_specialization', 'employment_date', 'address',
    'create_account'  # Optional - if 'yes', creates user account with email
]


def generate_temp_password(length=10):
    """Generate a random temporary password."""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


@admin_required
def bulk_import(request):
    """Handle bulk import of teachers."""
    if request.method == 'GET':
        return render(request, 'teachers/partials/modal_bulk_import.html', {
            'expected_columns': EXPECTED_COLUMNS,
        })

    # POST - Process File
    if 'file' not in request.FILES:
        return render(request, 'teachers/partials/modal_bulk_import.html', {
            'expected_columns': EXPECTED_COLUMNS,
            'error': 'Please select a file to upload.',
        })

    file = request.FILES['file']
    ext = file.name.split('.')[-1].lower()

    if ext not in ['xlsx', 'csv']:
        return render(request, 'teachers/partials/modal_bulk_import.html', {
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
            return render(request, 'teachers/partials/modal_bulk_import.html', {
                'expected_columns': EXPECTED_COLUMNS,
                'error': 'The file is empty.',
            })

        # Normalize headers
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

        valid_rows = []
        all_errors = []

        # Pre-fetch existing unique fields
        existing_staff_ids = set(Teacher.objects.values_list('staff_id', flat=True))
        existing_emails = set(
            Teacher.objects.exclude(email__isnull=True)
            .exclude(email='')
            .values_list('email', flat=True)
        )
        existing_user_emails = set(User.objects.values_list('email', flat=True))

        for idx, row in df.iterrows():
            row_num = idx + 2
            errors = []

            # Extract Data
            title = clean_value(row.get('title', '')).capitalize()
            if title.endswith('.'):
                title = title[:-1]

            first_name = clean_value(row.get('first_name', ''))
            last_name = clean_value(row.get('last_name', ''))
            middle_name = clean_value(row.get('middle_name', ''))
            gender = clean_value(row.get('gender', '')).upper()
            staff_id = clean_value(row.get('staff_id', ''))
            email = clean_value(row.get('email', '')).lower()
            phone = clean_value(row.get('phone', ''))
            subject = clean_value(row.get('subject_specialization', ''))
            address = clean_value(row.get('address', ''))
            create_account = clean_value(row.get('create_account', '')).lower() in ['yes', 'true', '1', 'y']

            emp_date = parse_date(row.get('employment_date'))
            dob = parse_date(row.get('date_of_birth'))

            # Normalize gender
            if gender.startswith('M'):
                gender = 'M'
            elif gender.startswith('F'):
                gender = 'F'

            # Basic Validation
            if not first_name or not last_name:
                errors.append("Name is required")

            if not dob:
                errors.append("Date of Birth is required")

            if gender not in ['M', 'F']:
                errors.append("Gender must be M or F")

            if not staff_id:
                errors.append("Staff ID is required")
            elif staff_id in existing_staff_ids:
                errors.append(f"Staff ID '{staff_id}' already exists")

            if email:
                if email in existing_emails:
                    errors.append(f"Email '{email}' already exists in teachers")
                if create_account and email in existing_user_emails:
                    errors.append(f"User account with email '{email}' already exists")

            if create_account and not email:
                errors.append("Email is required when create_account is 'yes'")

            if errors:
                all_errors.append({'row': row_num, 'errors': errors})
            else:
                valid_rows.append({
                    'row_num': row_num,
                    'title': title or 'Mr',
                    'first_name': first_name,
                    'last_name': last_name,
                    'middle_name': middle_name,
                    'gender': gender,
                    'date_of_birth': str(dob),
                    'staff_id': staff_id,
                    'email': email,
                    'phone_number': phone,
                    'subject_specialization': subject or 'General',
                    'employment_date': str(emp_date) if emp_date else str(datetime.now().date()),
                    'address': address,
                    'create_account': create_account,
                })
                # Track to catch duplicates within the file
                existing_staff_ids.add(staff_id)
                if email:
                    existing_emails.add(email)
                    if create_account:
                        existing_user_emails.add(email)

        request.session['teacher_bulk_data'] = json.dumps(valid_rows)

        return render(request, 'teachers/partials/modal_bulk_preview.html', {
            'valid_rows': valid_rows,
            'all_errors': all_errors,
            'total_rows': len(df),
            'valid_count': len(valid_rows),
            'error_count': len(all_errors),
        })

    except Exception as e:
        return render(request, 'teachers/partials/modal_bulk_import.html', {
            'expected_columns': EXPECTED_COLUMNS,
            'error': f"Error processing file: {str(e)}"
        })


@admin_required
def bulk_import_confirm(request):
    """Commit the bulk import to database."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    data = request.session.get('teacher_bulk_data')
    if not data:
        return redirect('teachers:index')

    try:
        rows = json.loads(data)
    except json.JSONDecodeError:
        messages.error(request, 'Invalid session data. Please upload the file again.')
        return redirect('teachers:index')

    created_count = 0
    accounts_created = 0
    errors = []

    # Prepare teachers for bulk create
    teachers_to_create = []
    account_data = []  # (index, email, first_name, last_name, title)

    for idx, row in enumerate(rows):
        try:
            emp_date = datetime.strptime(row['employment_date'], '%Y-%m-%d').date()
            dob = datetime.strptime(row['date_of_birth'], '%Y-%m-%d').date()

            teachers_to_create.append(Teacher(
                title=row.get('title', 'Mr'),
                first_name=row['first_name'],
                last_name=row['last_name'],
                middle_name=row.get('middle_name', ''),
                gender=row['gender'],
                date_of_birth=dob,
                staff_id=row['staff_id'],
                email=row.get('email') or None,
                phone_number=row.get('phone_number', ''),
                subject_specialization=row.get('subject_specialization', 'General'),
                employment_date=emp_date,
                address=row.get('address', ''),
                status='active'
            ))

            # Track accounts to create
            if row.get('create_account') and row.get('email'):
                account_data.append((
                    idx,
                    row['email'],
                    row['first_name'],
                    row['last_name'],
                    row.get('title', 'Mr')
                ))

        except Exception as e:
            errors.append(f"Row {row.get('row_num', '?')}: Error preparing data - {str(e)}")

    if not errors:
        try:
            with transaction.atomic():
                # Bulk create teachers
                created_teachers = Teacher.objects.bulk_create(teachers_to_create)
                created_count = len(created_teachers)

                # Create user accounts for teachers with create_account=True
                if account_data:
                    for idx, email, first_name, last_name, title in account_data:
                        if idx < len(created_teachers):
                            teacher = created_teachers[idx]
                            temp_password = generate_temp_password()

                            user = User.objects.create_user(
                                email=email,
                                password=temp_password,
                                first_name=first_name,
                                last_name=last_name,
                                is_teacher=True,
                                must_change_password=True,
                            )

                            teacher.user = user
                            teacher.save(update_fields=['user'])
                            accounts_created += 1

        except Exception as e:
            errors.append(f"Error during bulk creation: {str(e)}")

    # Clear session
    request.session.pop('teacher_bulk_data', None)

    if errors:
        messages.warning(request, f"Some errors occurred: {'; '.join(errors)}")
    else:
        msg = f"{created_count} teacher(s) imported successfully."
        if accounts_created:
            msg += f" {accounts_created} user account(s) created."
        messages.success(request, msg)

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response

    return redirect('teachers:index')


@admin_required
def bulk_import_template(request):
    """Download sample Excel file."""
    data = {
        'title': ['Mr', 'Mrs', 'Dr'],
        'first_name': ['John', 'Jane', 'Robert'],
        'last_name': ['Doe', 'Smith', 'Brown'],
        'middle_name': ['', 'Ann', ''],
        'gender': ['M', 'F', 'M'],
        'date_of_birth': ['1985-05-12', '1990-08-22', '1982-03-15'],
        'staff_id': ['TCH001', 'TCH002', 'TCH003'],
        'email': ['john@school.com', 'jane@school.com', 'robert@school.com'],
        'phone': ['0244123456', '0501234567', ''],
        'subject_specialization': ['Mathematics', 'English', 'Science'],
        'employment_date': ['2024-01-01', '2024-01-15', '2024-02-01'],
        'address': ['Accra', 'Kumasi', 'Tamale'],
        'create_account': ['yes', 'yes', ''],  # Optional - creates portal login if 'yes'
    }

    df = pd.DataFrame(data)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Teachers')

        worksheet = writer.sheets['Teachers']
        for column in worksheet.columns:
            max_length = 0
            column_cells = [cell for cell in column]
            for cell in column_cells:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except (TypeError, ValueError):
                    pass
            adjusted_width = max_length + 2
            worksheet.column_dimensions[column_cells[0].column_letter].width = adjusted_width

    buffer.seek(0)
    return FileResponse(
        buffer,
        as_attachment=True,
        filename='teacher_import_template.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
