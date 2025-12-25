import json
import io
import pandas as pd
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, FileResponse
from django.contrib import messages
from django.db.models import Q

from .models import Teacher
from .forms import TeacherForm


def htmx_render(request, full_template, partial_template, context=None):
    """
    Render full template for regular requests, partial for HTMX requests.
    """
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)


@login_required
def index(request):
    """Teacher list page with search and filter."""
    teachers = Teacher.objects.all().order_by('first_name')

    # Search
    search = request.GET.get('search', '').strip()
    if search:
        teachers = teachers.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(staff_id__icontains=search) |
            Q(subject_specialization__icontains=search)
        )

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        teachers = teachers.filter(status=status_filter)

    context = {
        'teachers': teachers,
        'status_choices': Teacher.Status.choices,
        'search': search,
        'status_filter': status_filter,
    }

    return htmx_render(
        request,
        'teachers/index.html',
        'teachers/partials/index_content.html',
        context
    )


@login_required
def teacher_create(request):
    """Create a new teacher."""
    if request.method == 'GET':
        form = TeacherForm()
        return htmx_render(
            request,
            'teachers/teacher_form.html',
            'teachers/partials/teacher_form_content.html',
            {'form': form}
        )

    if request.method == 'POST':
        form = TeacherForm(request.POST, request.FILES)
        if form.is_valid():
            teacher = form.save()
            messages.success(request, f"Teacher {teacher} created successfully.")
            return redirect('teachers:index')
        
        # If invalid
        return htmx_render(
            request,
            'teachers/teacher_form.html',
            'teachers/partials/teacher_form_content.html',
            {'form': form}
        )


@login_required
def teacher_edit(request, pk):
    """Edit an existing teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)

    if request.method == 'GET':
        form = TeacherForm(instance=teacher)
        return htmx_render(
            request,
            'teachers/teacher_form.html',
            'teachers/partials/teacher_form_content.html',
            {'form': form, 'teacher': teacher}
        )

    if request.method == 'POST':
        form = TeacherForm(request.POST, request.FILES, instance=teacher)
        if form.is_valid():
            form.save()
            messages.success(request, "Teacher details updated.")
            return redirect('teachers:index')

        return htmx_render(
            request,
            'teachers/teacher_form.html',
            'teachers/partials/teacher_form_content.html',
            {'form': form, 'teacher': teacher}
        )


@login_required
def teacher_detail(request, pk):
    """View teacher details."""
    teacher = get_object_or_404(Teacher, pk=pk)
    
    # Placeholder for future logic (e.g., classes assigned to this teacher)
    assigned_classes = [] 
    
    # Note: 'school' and 'tenant' are injected globally by core.context_processors
    return htmx_render(
        request,
        'teachers/teacher_detail.html',
        'teachers/partials/teacher_detail_content.html',
        {
            'teacher': teacher,
            'assigned_classes': assigned_classes
        }
    )


@login_required
def teacher_delete(request, pk):
    """Delete a teacher."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)
    teacher.delete()

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('teachers:index')


# ============ BULK IMPORT LOGIC ============

EXPECTED_COLUMNS = [
    'title', 'first_name', 'last_name', 'middle_name', 'gender',
    'date_of_birth', 'staff_id', 'email', 'phone', 
    'subject_specialization', 'employment_date', 'address'
]


def clean_value(value):
    """Clean a cell value, handling NaN and empty strings."""
    if value is None:
        return ''
    if isinstance(value, float) and pd.isna(value):
        return ''
    return str(value).strip()


def parse_date(value):
    """Try to parse date from common formats."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, 'date'):  # pandas Timestamp
        return value.date()
    
    val_str = str(value).strip()
    if not val_str:
        return None
        
    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']:
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue
    return None


@login_required
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
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_').str.replace('number', '').str.replace('_number', '')

        valid_rows = []
        all_errors = []
        
        # Pre-fetch existing unique fields to avoid DB hits in loop
        existing_staff_ids = set(Teacher.objects.values_list('staff_id', flat=True))
        # Use simple email check (ignore empty ones for uniqueness check)
        existing_emails = set(Teacher.objects.exclude(email__isnull=True).exclude(email='').values_list('email', flat=True))

        for idx, row in df.iterrows():
            row_num = idx + 2
            errors = []

            # Extract Data
            title = clean_value(row.get('title', '')).capitalize()
            if title.endswith('.'): title = title[:-1]

            first_name = clean_value(row.get('first_name', ''))
            last_name = clean_value(row.get('last_name', ''))
            middle_name = clean_value(row.get('middle_name', ''))
            gender = clean_value(row.get('gender', '')).upper()
            staff_id = clean_value(row.get('staff_id', ''))
            email = clean_value(row.get('email', ''))
            phone = clean_value(row.get('phone', ''))
            subject = clean_value(row.get('subject_specialization', ''))
            address = clean_value(row.get('address', ''))
            
            emp_date = parse_date(row.get('employment_date'))
            
            # FIXED: Extract and parse Date of Birth
            dob = parse_date(row.get('date_of_birth'))

            # Basic Validation
            if not first_name or not last_name:
                errors.append("Name is required")
            
            # FIXED: Validate Date of Birth
            if not dob:
                errors.append("Date of Birth is required")
            
            if gender not in ['M', 'F']:
                if gender.startswith('M'): gender = 'M'
                elif gender.startswith('F'): gender = 'F'
                else: errors.append("Gender must be M or F")

            if not staff_id:
                errors.append("Staff ID is required")
            elif staff_id in existing_staff_ids:
                errors.append(f"Staff ID '{staff_id}' already exists")
            
            if email and email in existing_emails:
                errors.append(f"Email '{email}' already exists")

            if errors:
                all_errors.append({'row': row_num, 'errors': errors})
            else:
                valid_rows.append({
                    'row_num': row_num,
                    'title': title,
                    'first_name': first_name,
                    'last_name': last_name,
                    'middle_name': middle_name,
                    'gender': gender,
                    # FIXED: Add dob to valid rows
                    'date_of_birth': str(dob), 
                    'staff_id': staff_id,
                    'email': email,
                    'phone_number': phone,
                    'subject_specialization': subject,
                    'employment_date': str(emp_date) if emp_date else str(datetime.now().date()),
                    'address': address,
                    'status': 'active'
                })
                # Add to sets to catch duplicates within the file itself
                existing_staff_ids.add(staff_id)
                if email: existing_emails.add(email)

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


@login_required
def bulk_import_confirm(request):
    """Commit the bulk import to database."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    data = request.session.get('teacher_bulk_data')
    if not data:
        return redirect('teachers:index')

    try:
        rows = json.loads(data)
        count = 0
        
        for row in rows:
            e_date = datetime.strptime(row['employment_date'], '%Y-%m-%d').date()
            # FIXED: Parse dob back from string
            dob = datetime.strptime(row['date_of_birth'], '%Y-%m-%d').date()
            
            Teacher.objects.create(
                title=row.get('title', 'Mr'),
                first_name=row['first_name'],
                last_name=row['last_name'],
                middle_name=row.get('middle_name', ''),
                gender=row['gender'],
                # FIXED: Include dob in creation
                date_of_birth=dob,
                staff_id=row['staff_id'],
                email=row.get('email') or None,
                phone_number=row.get('phone_number', ''),
                subject_specialization=row.get('subject_specialization', 'General'),
                employment_date=e_date,
                address=row.get('address', ''),
                status='active'
            )
            count += 1

        messages.success(request, f"Successfully imported {count} teachers.")
        
        if 'teacher_bulk_data' in request.session:
            del request.session['teacher_bulk_data']

        if request.htmx:
            response = HttpResponse(status=200)
            response['HX-Refresh'] = 'true'
            return response
            
        return redirect('teachers:index')

    except Exception as e:
        messages.error(request, f"Error saving data: {str(e)}")
        # Ideally log this error
        print(f"Bulk Import Error: {e}") 
        return redirect('teachers:index')


@login_required
def bulk_import_template(request):
    """Download sample Excel file."""
    data = {
        'Title': ['Mr', 'Mrs', 'Dr'],
        'First Name': ['John', 'Jane', 'Robert'],
        'Last Name': ['Doe', 'Smith', 'Brown'],
        'Middle Name': ['', 'Ann', ''],
        'Gender': ['M', 'F', 'M'],
        # FIXED: Date of Birth column
        'Date of Birth': ['1985-05-12', '1990-08-22', '1982-03-15'],
        'Staff ID': ['TCH001', 'TCH002', 'TCH003'],
        'Email': ['john@school.com', 'jane@school.com', ''],
        'Phone': ['0244123456', '0501234567', ''],
        'Subject Specialization': ['Mathematics', 'English', 'Science'],
        'Employment Date': ['2024-01-01', '2024-01-15', '2024-02-01'],
        'Address': ['Accra', 'Kumasi', 'Tamale']
    }
    
    df = pd.DataFrame(data)
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Teachers')
        
        worksheet = writer.sheets['Teachers']
        for column in worksheet.columns:
            max_length = 0
            column = [cell for cell in column]
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2)
            worksheet.column_dimensions[column[0].column_letter].width = adjusted_width

    buffer.seek(0)
    return FileResponse(
        buffer, 
        as_attachment=True, 
        filename='teacher_import_template.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )