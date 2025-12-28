import json
import io
import pandas as pd
from functools import wraps
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, FileResponse
from django.contrib import messages
from django.db.models import Q

from django.contrib.auth import get_user_model

from .models import Teacher
from .forms import TeacherForm
from academics.models import Class, ClassSubject, Period, TimetableEntry
from students.models import Student

User = get_user_model()


def is_school_admin(user):
    """Check if user is a school admin or superuser."""
    return user.is_superuser or getattr(user, 'is_school_admin', False)


def admin_required(view_func):
    """Decorator to require school admin or superuser access."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not is_school_admin(request.user):
            messages.error(request, "You don't have permission to access this page.")
            return redirect('core:index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def htmx_render(request, full_template, partial_template, context=None):
    """
    Render full template for regular requests, partial for HTMX requests.
    """
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)


@admin_required
def index(request):
    """Teacher list page with search and filter - Admin only."""
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


@admin_required
def teacher_create(request):
    """Create a new teacher - Admin only."""
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


@admin_required
def teacher_edit(request, pk):
    """Edit an existing teacher - Admin only."""
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


@admin_required
def teacher_detail(request, pk):
    """View teacher details with classes, subjects, and workload - Admin only."""
    teacher = get_object_or_404(Teacher, pk=pk)

    # Classes where this teacher is the class teacher (form tutor)
    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    ).order_by('name')

    # Subject assignments - classes and subjects this teacher teaches
    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name', 'subject__name'
    )

    # Calculate workload stats
    classes_taught = subject_assignments.values('class_assigned').distinct().count()
    subjects_taught = subject_assignments.values('subject').distinct().count()

    # Total students taught (across all classes)
    class_ids = subject_assignments.values_list('class_assigned_id', flat=True).distinct()
    total_students = Student.objects.filter(
        current_class_id__in=class_ids,
        status='active'
    ).count()

    # Students in homeroom classes
    homeroom_students = Student.objects.filter(
        current_class__in=homeroom_classes,
        status='active'
    ).count()

    workload = {
        'classes_taught': classes_taught,
        'subjects_taught': subjects_taught,
        'total_students': total_students,
        'homeroom_classes': homeroom_classes.count(),
        'homeroom_students': homeroom_students,
    }

    return htmx_render(
        request,
        'teachers/teacher_detail.html',
        'teachers/partials/teacher_detail_content.html',
        {
            'teacher': teacher,
            'homeroom_classes': homeroom_classes,
            'subject_assignments': subject_assignments,
            'workload': workload,
        }
    )


@admin_required
def teacher_delete(request, pk):
    """Delete a teacher - Admin only."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)
    teacher.delete()

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('teachers:index')


# ============ TEACHER DASHBOARD ============

@login_required
def profile(request):
    """View own teacher profile."""
    teacher = getattr(request.user, 'teacher_profile', None)

    if not teacher:
        messages.warning(request, "No teacher profile linked to your account.")
        return redirect('core:index')

    # Get class assignments
    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    ).order_by('name')

    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name'
    )

    # Calculate workload
    classes_taught = list({sa.class_assigned for sa in subject_assignments})
    total_students = Student.objects.filter(
        current_class_id__in=[c.id for c in classes_taught],
        status='active'
    ).count()

    context = {
        'teacher': teacher,
        'homeroom_classes': homeroom_classes,
        'subject_assignments': subject_assignments,
        'workload': {
            'classes_taught': len(classes_taught),
            'subjects_taught': subject_assignments.count(),
            'total_students': total_students,
            'homeroom_classes': homeroom_classes.count(),
        }
    }

    return htmx_render(
        request,
        'teachers/profile.html',
        'teachers/partials/profile_content.html',
        context
    )


@login_required
def dashboard(request):
    """Dashboard for logged-in teachers showing their classes and students."""
    # Get the teacher profile for the logged-in user
    teacher = getattr(request.user, 'teacher_profile', None)

    if not teacher:
        messages.warning(request, "No teacher profile linked to your account.")
        return redirect('core:index')

    # Get current term
    from core.models import Term
    current_term = Term.get_current()

    # Homeroom classes (where teacher is class teacher)
    homeroom_classes = Class.objects.filter(
        class_teacher=teacher,
        is_active=True
    ).prefetch_related('students').order_by('name')

    # Subject assignments
    subject_assignments = ClassSubject.objects.filter(
        teacher=teacher
    ).select_related('class_assigned', 'subject').order_by(
        'class_assigned__level_number', 'class_assigned__name'
    )

    # Get unique classes taught
    classes_taught = list({sa.class_assigned for sa in subject_assignments})
    classes_taught.sort(key=lambda c: (c.level_number or 0, c.name))

    # Calculate stats
    total_students = Student.objects.filter(
        current_class_id__in=[c.id for c in classes_taught],
        status='active'
    ).count()

    homeroom_students = Student.objects.filter(
        current_class__in=homeroom_classes,
        status='active'
    ).count()

    # Group assignments by class for easy display
    assignments_by_class = {}
    for assignment in subject_assignments:
        class_name = assignment.class_assigned.name
        if class_name not in assignments_by_class:
            assignments_by_class[class_name] = {
                'class': assignment.class_assigned,
                'subjects': []
            }
        assignments_by_class[class_name]['subjects'].append(assignment.subject)

    context = {
        'teacher': teacher,
        'current_term': current_term,
        'homeroom_classes': homeroom_classes,
        'classes_taught': classes_taught,
        'assignments_by_class': assignments_by_class,
        'stats': {
            'classes_count': len(classes_taught),
            'subjects_count': subject_assignments.count(),
            'total_students': total_students,
            'homeroom_students': homeroom_students,
        }
    }

    return htmx_render(
        request,
        'teachers/dashboard.html',
        'teachers/partials/dashboard_content.html',
        context
    )


# ============ TEACHER SCHEDULE ============

@login_required
def schedule(request):
    """Weekly schedule/timetable view for logged-in teachers."""
    from django.utils import timezone

    # Get the teacher profile for the logged-in user
    teacher = getattr(request.user, 'teacher_profile', None)

    if not teacher:
        messages.warning(request, "No teacher profile linked to your account.")
        return redirect('core:index')

    today = timezone.now()
    weekday = today.isoweekday()  # 1=Monday, 7=Sunday

    # Get all periods (time slots)
    periods = Period.objects.filter(is_active=True).order_by('order')

    # Get all timetable entries for this teacher
    entries = TimetableEntry.objects.filter(
        class_subject__teacher=teacher
    ).select_related(
        'class_subject__class_assigned',
        'class_subject__subject',
        'period'
    ).order_by('weekday', 'period__order')

    # Organize entries into a grid: {period_id: {weekday: entry}}
    schedule_grid = {}
    for period in periods:
        schedule_grid[period.id] = {
            'period': period,
            'days': {1: None, 2: None, 3: None, 4: None, 5: None}
        }

    for entry in entries:
        if entry.period_id in schedule_grid:
            schedule_grid[entry.period_id]['days'][entry.weekday] = entry

    # Calculate stats
    total_periods = entries.count()
    classes_taught = entries.values('class_subject__class_assigned').distinct().count()

    context = {
        'teacher': teacher,
        'periods': periods,
        'schedule_grid': schedule_grid,
        'weekdays': TimetableEntry.Weekday.choices,
        'weekday': weekday,
        'today': today,
        'stats': {
            'total_periods': total_periods,
            'classes_taught': classes_taught,
        }
    }

    return htmx_render(
        request,
        'teachers/schedule.html',
        'teachers/partials/schedule_content.html',
        context
    )


@admin_required
def teacher_schedule(request, pk):
    """View any teacher's schedule - Admin only."""
    teacher = get_object_or_404(Teacher, pk=pk)

    # Get all periods (time slots)
    periods = Period.objects.filter(is_active=True).order_by('order')

    # Get all timetable entries for this teacher
    entries = TimetableEntry.objects.filter(
        class_subject__teacher=teacher
    ).select_related(
        'class_subject__class_assigned',
        'class_subject__subject',
        'period'
    ).order_by('weekday', 'period__order')

    # Organize entries into a grid
    schedule_grid = {}
    for period in periods:
        schedule_grid[period.id] = {
            'period': period,
            'days': {1: None, 2: None, 3: None, 4: None, 5: None}
        }

    for entry in entries:
        if entry.period_id in schedule_grid:
            schedule_grid[entry.period_id]['days'][entry.weekday] = entry

    # Calculate stats
    total_periods = entries.count()

    context = {
        'teacher': teacher,
        'periods': periods,
        'schedule_grid': schedule_grid,
        'weekdays': TimetableEntry.Weekday.choices,
        'stats': {
            'total_periods': total_periods,
        }
    }

    return htmx_render(
        request,
        'teachers/schedule.html',
        'teachers/partials/schedule_content.html',
        context
    )


# ============ USER ACCOUNT CREATION ============

def generate_temp_password(length=10):
    """Generate a random temporary password."""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def send_account_credentials(user, password, teacher):
    """Send account credentials via email."""
    from django.core.mail import send_mail
    from django.conf import settings

    subject = "Your Teacher Account Has Been Created"
    message = f"""
Dear {teacher.get_title_display()} {teacher.full_name},

Your account for the school management system has been created.

Login Details:
Email: {user.email}
Temporary Password: {password}

Please log in and change your password immediately.

Login URL: {settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'Contact your administrator'}

This is an automated message. Please do not reply.
"""
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') else None,
            [user.email],
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


@admin_required
def create_account(request, pk):
    """Create a user account for a teacher - Admin only."""
    teacher = get_object_or_404(Teacher, pk=pk)

    # If teacher already has an account, redirect
    if teacher.user:
        messages.warning(request, f"{teacher.full_name} already has an account.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    if request.method == 'GET':
        return render(request, 'teachers/partials/modal_create_account.html', {
            'teacher': teacher,
        })

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()

        # Use teacher's email if not provided
        if not email:
            email = teacher.email

        if not email:
            return render(request, 'teachers/partials/modal_create_account.html', {
                'teacher': teacher,
                'error': 'Email address is required. Please provide an email.',
            })

        # Check if email already exists
        if User.objects.filter(email=email).exists():
            return render(request, 'teachers/partials/modal_create_account.html', {
                'teacher': teacher,
                'error': f"An account with email '{email}' already exists.",
            })

        # Generate temporary password
        temp_password = generate_temp_password()

        # Create user account
        user = User.objects.create_user(
            email=email,
            password=temp_password,
            first_name=teacher.first_name,
            last_name=teacher.last_name,
            is_teacher=True,
            must_change_password=True,
        )

        # Link to teacher
        teacher.user = user
        teacher.save(update_fields=['user'])

        # Also update teacher email if it was empty
        if not teacher.email:
            teacher.email = email
            teacher.save(update_fields=['email'])

        # Send credentials via email
        email_sent = send_account_credentials(user, temp_password, teacher)

        if email_sent:
            messages.success(
                request,
                f"Account created for {teacher.full_name}. Credentials sent to {email}."
            )
        else:
            # Still show the password if email failed
            messages.warning(
                request,
                f"Account created but email failed. Temporary password: {temp_password}"
            )

        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    return HttpResponse(status=405)


@admin_required
def deactivate_account(request, pk):
    """Deactivate a teacher's user account - Admin only."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)

    if teacher.user:
        user = teacher.user
        user.is_active = False
        user.save(update_fields=['is_active'])
        messages.success(request, f"Account for {teacher.full_name} has been deactivated.")

    response = HttpResponse(status=204)
    response['HX-Refresh'] = 'true'
    return response


@admin_required
def reset_password(request, pk):
    """Reset a teacher's password and send new credentials - Admin only."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)

    if not teacher.user:
        messages.error(request, f"{teacher.full_name} does not have an account.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    # Generate new temporary password
    temp_password = generate_temp_password()

    user = teacher.user
    user.set_password(temp_password)
    user.must_change_password = True
    user.save(update_fields=['password', 'must_change_password'])

    # Send new credentials
    email_sent = send_account_credentials(user, temp_password, teacher)

    if email_sent:
        messages.success(
            request,
            f"Password reset for {teacher.full_name}. New credentials sent to {user.email}."
        )
    else:
        messages.warning(
            request,
            f"Password reset but email failed. New temporary password: {temp_password}"
        )

    response = HttpResponse(status=204)
    response['HX-Refresh'] = 'true'
    return response


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


@admin_required
def bulk_import(request):
    """Handle bulk import of teachers - Admin only."""
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


@admin_required
def bulk_import_confirm(request):
    """Commit the bulk import to database - Admin only."""
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


@admin_required
def bulk_import_template(request):
    """Download sample Excel file - Admin only."""
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