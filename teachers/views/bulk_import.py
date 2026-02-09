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
from teachers.models import Teacher, TeacherInvitation
from .utils import admin_required, clean_value, parse_date
from .accounts import send_invitation_email


EXPECTED_COLUMNS = [
    'title', 'first_name', 'last_name', 'middle_name', 'gender',
    'date_of_birth', 'staff_id', 'email', 'phone',
    'employment_date', 'address',
    'staff_category', 'ghana_card_number', 'ssnit_number',
    'licence_number', 'date_posted_to_current_school',
    'send_invitation'  # Optional - if 'yes', sends invitation email to create account
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
            address = clean_value(row.get('address', ''))
            staff_category = clean_value(row.get('staff_category', '')).lower() or 'teaching'
            ghana_card_number = clean_value(row.get('ghana_card_number', ''))
            ssnit_number = clean_value(row.get('ssnit_number', ''))
            licence_number = clean_value(row.get('licence_number', ''))
            send_invitation = clean_value(row.get('send_invitation', '')).lower() in ['yes', 'true', '1', 'y']

            emp_date = parse_date(row.get('employment_date'))
            dob = parse_date(row.get('date_of_birth'))
            date_posted = parse_date(row.get('date_posted_to_current_school'))

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
                if send_invitation and email in existing_user_emails:
                    errors.append(f"User account with email '{email}' already exists")

            if send_invitation and not email:
                errors.append("Email is required when send_invitation is 'yes'")

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
                    'employment_date': str(emp_date) if emp_date else str(datetime.now().date()),
                    'address': address,
                    'staff_category': staff_category if staff_category in ('teaching', 'non_teaching') else 'teaching',
                    'ghana_card_number': ghana_card_number,
                    'ssnit_number': ssnit_number,
                    'licence_number': licence_number,
                    'date_posted_to_current_school': str(date_posted) if date_posted else '',
                    'send_invitation': send_invitation,
                })
                # Track to catch duplicates within the file
                existing_staff_ids.add(staff_id)
                if email:
                    existing_emails.add(email)
                    if send_invitation:
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
    invitations_sent = 0
    errors = []

    # Prepare teachers for bulk create
    teachers_to_create = []
    invitation_data = []  # (index, email)

    for idx, row in enumerate(rows):
        try:
            emp_date = datetime.strptime(row['employment_date'], '%Y-%m-%d').date()
            dob = datetime.strptime(row['date_of_birth'], '%Y-%m-%d').date()

            date_posted_val = None
            if row.get('date_posted_to_current_school'):
                try:
                    date_posted_val = datetime.strptime(row['date_posted_to_current_school'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass

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
                employment_date=emp_date,
                address=row.get('address', ''),
                staff_category=row.get('staff_category', 'teaching'),
                ghana_card_number=row.get('ghana_card_number', ''),
                ssnit_number=row.get('ssnit_number', ''),
                licence_number=row.get('licence_number', ''),
                date_posted_to_current_school=date_posted_val,
                status='active'
            ))

            # Track invitations to send
            if row.get('send_invitation') and row.get('email'):
                invitation_data.append((idx, row['email']))

        except Exception as e:
            errors.append(f"Row {row.get('row_num', '?')}: Error preparing data - {str(e)}")

    if not errors:
        try:
            with transaction.atomic():
                # Bulk create teachers
                created_teachers = Teacher.objects.bulk_create(teachers_to_create)
                created_count = len(created_teachers)

                # Create and send invitations for teachers with send_invitation=True
                if invitation_data:
                    for idx, email in invitation_data:
                        if idx < len(created_teachers):
                            teacher = created_teachers[idx]
                            invitation = TeacherInvitation.create_for_teacher(
                                teacher=teacher,
                                email=email,
                                created_by=request.user
                            )
                            # Send invitation email
                            if send_invitation_email(invitation, request):
                                invitations_sent += 1

        except Exception as e:
            errors.append(f"Error during bulk creation: {str(e)}")

    # Clear session
    request.session.pop('teacher_bulk_data', None)

    if errors:
        messages.warning(request, f"Some errors occurred: {'; '.join(errors)}")
    else:
        msg = f"{created_count} teacher(s) imported successfully."
        if invitations_sent:
            msg += f" {invitations_sent} invitation(s) sent."
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
        'employment_date': ['2024-01-01', '2024-01-15', '2024-02-01'],
        'address': ['Accra', 'Kumasi', 'Tamale'],
        'staff_category': ['teaching', 'teaching', 'non_teaching'],
        'ghana_card_number': ['GHA-123456789-0', '', 'GHA-987654321-0'],
        'ssnit_number': ['A12345678', '', 'B98765432'],
        'licence_number': ['LIC-001', 'LIC-002', ''],
        'date_posted_to_current_school': ['2024-01-01', '', '2024-02-01'],
        'send_invitation': ['yes', 'yes', ''],  # Optional - sends invite email if 'yes'
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


@admin_required
def bulk_export(request):
    """Export teachers to Excel with current filters applied."""
    from django.db.models import Q

    # Get filter parameters (same as index view)
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')

    # Build queryset
    teachers = Teacher.objects.select_related('user')

    # Apply filters
    if search:
        teachers = teachers.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(staff_id__icontains=search)
        )

    if status_filter:
        teachers = teachers.filter(status=status_filter)

    teachers = teachers.order_by('first_name', 'last_name')

    # Build export data
    export_data = []
    for teacher in teachers:
        export_data.append({
            'Staff ID': teacher.staff_id,
            'Title': teacher.get_title_display() if teacher.title else '',
            'First Name': teacher.first_name,
            'Middle Name': teacher.middle_name or '',
            'Last Name': teacher.last_name,
            'Gender': teacher.get_gender_display() if teacher.gender else '',
            'Date of Birth': teacher.date_of_birth.strftime('%Y-%m-%d') if teacher.date_of_birth else '',
            'Phone Number': teacher.phone_number or '',
            'Email': teacher.email or '',
            'Employment Date': teacher.employment_date.strftime('%Y-%m-%d') if teacher.employment_date else '',
            'Address': teacher.address or '',
            'Nationality': teacher.nationality or '',
            'Staff Category': teacher.get_staff_category_display(),
            'Ghana Card Number': teacher.ghana_card_number or '',
            'SSNIT Number': teacher.ssnit_number or '',
            'Licence Number': teacher.licence_number or '',
            'Date Posted to Current School': teacher.date_posted_to_current_school.strftime('%Y-%m-%d') if teacher.date_posted_to_current_school else '',
            'Status': teacher.get_status_display(),
            'Has Portal Account': 'Yes' if teacher.user else 'No',
        })

    # Create Excel file
    df = pd.DataFrame(export_data)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Teachers')

        # Auto-adjust column widths
        worksheet = writer.sheets['Teachers']
        for idx, col in enumerate(df.columns):
            max_length = max(
                df[col].astype(str).map(len).max() if len(df) > 0 else 0,
                len(col)
            ) + 2
            worksheet.column_dimensions[chr(65 + idx) if idx < 26 else 'A' + chr(65 + idx - 26)].width = min(max_length, 50)

    output.seek(0)

    # Generate filename with date
    filename = f"teachers_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return FileResponse(
        output,
        as_attachment=True,
        filename=filename,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
