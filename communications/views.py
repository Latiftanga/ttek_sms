import logging
from functools import wraps
from io import BytesIO

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages as django_messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import escape
from django.db import connection
from django.db.models import Count, Q, Exists, OuterRef
from core.utils import (
    cache_page_per_tenant, is_school_admin, htmx_render,
    teacher_or_admin_required as _core_teacher_or_admin_required,
)

import pandas as pd

from .models import SMSMessage, SMSTemplate, EmailMessage, Announcement, AnnouncementRead
from .utils import normalize_phone_number, get_sms_gateway_status, get_email_gateway_status
from students.models import Student, StudentGuardian
from academics.models import Class, AttendanceRecord
from teachers.models import Teacher

logger = logging.getLogger(__name__)


def _prefetch_primary_guardians(students):
    """
    Prefetch primary guardians for a list of students and set the cache
    so that student.guardian_phone / guardian_name don't trigger N+1 queries.
    Returns the same list with caches populated.
    """
    # Build lookup: student_id -> guardian
    sg_qs = StudentGuardian.objects.filter(
        student__in=students,
        is_primary=True
    ).select_related('guardian')

    guardian_map = {}
    for sg in sg_qs:
        guardian_map[sg.student_id] = sg.guardian

    for student in students:
        student._cached_primary_guardian = guardian_map.get(student.id)

    return students


# =============================================================================
# PERMISSION HELPERS
# =============================================================================

# is_school_admin, htmx_render, teacher_or_admin_required imported from core.utils
teacher_or_admin_required = _core_teacher_or_admin_required


def admin_required(view_func):
    """Decorator that requires user to be a school admin (redirects to communications)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_school_admin(request.user):
            django_messages.error(request, 'Only administrators can access this page.')
            return redirect('communications:index')
        return view_func(request, *args, **kwargs)
    return wrapper


# =============================================================================
# BULK SMS/EMAIL HELPERS (extracted from send_to_staff)
# =============================================================================

def _get_targeted_teachers(group, need_email=False):
    """Build teacher queryset filtered by group. Returns a list."""
    teachers = Teacher.objects.filter(status=Teacher.Status.ACTIVE)
    if group == 'teaching':
        teachers = teachers.filter(staff_category=Teacher.StaffCategory.TEACHING)
    elif group == 'non_teaching':
        teachers = teachers.filter(staff_category=Teacher.StaffCategory.NON_TEACHING)
    if need_email:
        teachers = teachers.select_related('user')
    return list(teachers)


def _send_bulk_sms_to_teachers(teachers, message_text, school_name, user, message_type=SMSMessage.MessageType.STAFF):
    """
    Bulk-create SMSMessage records for teachers and queue Celery tasks.
    Returns (queued, failed, skipped) counts.
    """
    sms_records = []
    teacher_sms_map = {}
    seen_phones = set()
    skipped = 0

    for teacher in teachers:
        phone = normalize_phone_number(teacher.phone_number) if teacher.phone_number else None
        if not phone:
            skipped += 1
            continue
        if phone in seen_phones:
            skipped += 1
            continue
        seen_phones.add(phone)

        personalized = message_text.replace('{teacher_name}', teacher.full_name)
        personalized = personalized.replace('{school_name}', school_name)

        sms = SMSMessage(
            recipient_phone=phone,
            recipient_name=teacher.full_name,
            message=personalized,
            message_type=message_type,
            created_by=user,
        )
        sms_records.append(sms)
        teacher_sms_map[teacher.pk] = (sms, phone, personalized)

    queued = 0
    failed = 0

    if sms_records:
        SMSMessage.objects.bulk_create(sms_records)

        from .tasks import send_communication_task
        from django.db import connection as db_connection

        for teacher in teachers:
            if teacher.pk not in teacher_sms_map:
                continue
            sms, phone, personalized = teacher_sms_map[teacher.pk]
            try:
                send_communication_task.delay(
                    db_connection.schema_name,
                    phone,
                    personalized,
                    sms_record_id=str(sms.pk)
                )
                queued += 1
            except Exception as e:
                logger.error("Failed to queue SMS for teacher %s: %s", teacher.pk, e)
                sms.mark_failed("Failed to queue for sending")
                failed += 1

    return queued, failed, skipped


def _send_bulk_email_to_teachers(teachers, subject, message_text, school_name, user, message_type=EmailMessage.MessageType.STAFF):
    """
    Bulk-create EmailMessage records for teachers and queue Celery tasks.
    Returns (queued, failed, skipped) counts.
    """
    email_records = []
    teacher_email_map = {}
    seen_emails = set()
    skipped = 0

    for teacher in teachers:
        email = teacher.email or (teacher.user.email if teacher.user else None)
        if not email:
            skipped += 1
            continue
        if email in seen_emails:
            skipped += 1
            continue
        seen_emails.add(email)

        personalized = message_text.replace('{teacher_name}', teacher.full_name)
        personalized = personalized.replace('{school_name}', school_name)

        record = EmailMessage(
            recipient_email=email,
            recipient_name=teacher.full_name,
            teacher=teacher,
            subject=subject,
            message=personalized,
            message_type=message_type,
            created_by=user,
        )
        email_records.append(record)
        teacher_email_map[teacher.pk] = record

    queued = 0
    failed = 0

    if email_records:
        EmailMessage.objects.bulk_create(email_records)

        from .tasks import send_email_task
        from django.db import connection as db_connection

        for teacher in teachers:
            if teacher.pk not in teacher_email_map:
                continue
            record = teacher_email_map[teacher.pk]
            try:
                send_email_task.delay(
                    db_connection.schema_name,
                    str(record.pk)
                )
                queued += 1
            except Exception as e:
                logger.error("Failed to queue email for teacher %s: %s", teacher.pk, e)
                record.mark_failed("Failed to queue for sending")
                failed += 1

    return queued, failed, skipped


def _send_bulk_sms_to_parents(students, message_text, school_name, user):
    """
    Bulk-create SMSMessage records for student guardians and queue Celery tasks.
    Returns (queued, failed, skipped) counts.
    """
    sms_records = []
    student_sms_map = {}
    seen_phones = set()
    skipped = 0

    for student in students:
        phone = normalize_phone_number(student.guardian_phone) if student.guardian_phone else None
        if not phone:
            skipped += 1
            continue
        if phone in seen_phones:
            skipped += 1
            continue
        seen_phones.add(phone)

        personalized = message_text.replace('{student_name}', student.full_name)
        personalized = personalized.replace('{class_name}', student.current_class.name if student.current_class else '')
        personalized = personalized.replace('{school_name}', school_name)

        sms = SMSMessage(
            recipient_phone=phone,
            recipient_name=student.guardian_name or '',
            student=student,
            message=personalized,
            message_type=SMSMessage.MessageType.ANNOUNCEMENT,
            created_by=user,
        )
        sms_records.append(sms)
        student_sms_map[student.pk] = (sms, phone, personalized)

    queued = 0
    failed = 0

    if sms_records:
        SMSMessage.objects.bulk_create(sms_records)

        from .tasks import send_communication_task
        from django.db import connection as db_connection

        for student in students:
            if student.pk not in student_sms_map:
                continue
            sms, phone, personalized = student_sms_map[student.pk]
            try:
                send_communication_task.delay(
                    db_connection.schema_name,
                    phone,
                    personalized,
                    sms_record_id=str(sms.pk)
                )
                queued += 1
            except Exception as e:
                logger.error("Failed to queue SMS for parent of student %s: %s", student.pk, e)
                sms.mark_failed("Failed to queue for sending")
                failed += 1

    return queued, failed, skipped


def _send_bulk_email_to_parents(students, subject, message_text, school_name, user):
    """
    Bulk-create EmailMessage records for student guardians and queue Celery tasks.
    Returns (queued, failed, skipped) counts.
    """
    email_records = []
    student_email_map = {}
    seen_emails = set()
    skipped = 0

    for student in students:
        email = student.guardian_email
        if not email:
            skipped += 1
            continue
        if email in seen_emails:
            skipped += 1
            continue
        seen_emails.add(email)

        personalized = message_text.replace('{student_name}', student.full_name)
        personalized = personalized.replace('{class_name}', student.current_class.name if student.current_class else '')
        personalized = personalized.replace('{school_name}', school_name)

        record = EmailMessage(
            recipient_email=email,
            recipient_name=student.guardian_name or '',
            subject=subject,
            message=personalized,
            message_type=EmailMessage.MessageType.ANNOUNCEMENT,
            created_by=user,
        )
        email_records.append(record)
        student_email_map[student.pk] = record

    queued = 0
    failed = 0

    if email_records:
        EmailMessage.objects.bulk_create(email_records)

        from .tasks import send_email_task
        from django.db import connection as db_connection

        for student in students:
            if student.pk not in student_email_map:
                continue
            record = student_email_map[student.pk]
            try:
                send_email_task.delay(
                    db_connection.schema_name,
                    str(record.pk)
                )
                queued += 1
            except Exception as e:
                logger.error("Failed to queue email for parent of student %s: %s", student.pk, e)
                record.mark_failed("Failed to queue for sending")
                failed += 1

    return queued, failed, skipped


def _send_bulk_sms_to_students(students, message_text, school_name, user):
    """
    Bulk-create SMSMessage records for students and queue Celery tasks.
    Returns (queued, failed, skipped) counts.
    """
    sms_records = []
    student_sms_map = {}
    seen_phones = set()
    skipped = 0

    for student in students:
        phone = normalize_phone_number(student.phone) if student.phone else None
        if not phone:
            skipped += 1
            continue
        if phone in seen_phones:
            skipped += 1
            continue
        seen_phones.add(phone)

        personalized = message_text.replace('{student_name}', student.full_name)
        personalized = personalized.replace('{class_name}', student.current_class.name if student.current_class else '')
        personalized = personalized.replace('{school_name}', school_name)

        sms = SMSMessage(
            recipient_phone=phone,
            recipient_name=student.full_name,
            student=student,
            message=personalized,
            message_type=SMSMessage.MessageType.ANNOUNCEMENT,
            created_by=user,
        )
        sms_records.append(sms)
        student_sms_map[student.pk] = (sms, phone, personalized)

    queued = 0
    failed = 0

    if sms_records:
        SMSMessage.objects.bulk_create(sms_records)

        from .tasks import send_communication_task
        from django.db import connection as db_connection

        for student in students:
            if student.pk not in student_sms_map:
                continue
            sms, phone, personalized = student_sms_map[student.pk]
            try:
                send_communication_task.delay(
                    db_connection.schema_name,
                    phone,
                    personalized,
                    sms_record_id=str(sms.pk)
                )
                queued += 1
            except Exception as e:
                logger.error("Failed to queue SMS for student %s: %s", student.pk, e)
                sms.mark_failed("Failed to queue for sending")
                failed += 1

    return queued, failed, skipped


# =============================================================================
# COMMUNICATIONS DASHBOARD
# =============================================================================

@login_required
@teacher_or_admin_required
@cache_page_per_tenant(timeout=60)  # Cache for 1 minute (SMS stats change frequently)
def index(request):
    """SMS dashboard with recent messages and quick actions. Cached for 1 minute."""
    messages = SMSMessage.objects.select_related('student', 'created_by')[:50]
    templates = SMSTemplate.objects.filter(is_active=True)

    # Stats — single aggregate query instead of 4 separate counts
    today = timezone.now().date()
    today_stats = SMSMessage.objects.filter(
        created_at__date=today
    ).aggregate(
        total_today=Count('id'),
        sent_today=Count('id', filter=Q(status='sent')),
        failed_today=Count('id', filter=Q(status='failed')),
    )
    pending_count = SMSMessage.objects.filter(status='pending').count()
    stats = {
        **today_stats,
        'pending': pending_count,
    }

    # Gateway status
    sms_gateway = get_sms_gateway_status()
    email_gateway = get_email_gateway_status()

    context = {
        'messages': messages,
        'templates': templates,
        'stats': stats,
        'sms_gateway': sms_gateway,
        'email_gateway': email_gateway,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Communications'},
        ],
    }

    return htmx_render(
        request,
        'communications/index.html',
        'communications/partials/index_content.html',
        context
    )


@login_required
@teacher_or_admin_required
def class_recipients(request):
    """Get recipient count for a class (HTMX endpoint)."""
    class_id = request.GET.get('class_id')

    if not class_id:
        return HttpResponse('''
            <div class="bg-base-200 rounded-lg p-3 text-sm text-base-content/60">
                <i class="fa-solid fa-info-circle mr-1"></i>
                Select a class to see recipient count
            </div>
        ''')

    try:
        class_obj = Class.objects.get(pk=class_id)
        students = Student.objects.filter(current_class=class_obj, status='active')
        total_students = students.count()
        # Count students with a primary guardian who has a phone number
        with_phone = students.filter(
            student_guardians__is_primary=True,
            student_guardians__guardian__phone_number__isnull=False
        ).exclude(
            student_guardians__guardian__phone_number=''
        ).distinct().count()
        without_phone = total_students - with_phone

        # Escape user-controlled data to prevent XSS
        class_name = escape(class_obj.name)
        warning_html = ''
        if without_phone > 0:
            warning_html = f'<span class="flex items-center gap-1 text-warning"><i class="fa-solid fa-triangle-exclamation"></i>{without_phone} without phone</span>'

        return HttpResponse(f'''
            <div class="bg-base-200 rounded-lg p-3">
                <div class="flex items-center justify-between text-sm">
                    <span class="font-medium">{class_name}</span>
                    <span class="badge badge-primary">{total_students} students</span>
                </div>
                <div class="flex items-center gap-4 mt-2 text-xs text-base-content/70">
                    <span class="flex items-center gap-1">
                        <i class="fa-solid fa-check text-success"></i>
                        {with_phone} with phone
                    </span>
                    {warning_html}
                </div>
            </div>
        ''')
    except Class.DoesNotExist:
        return HttpResponse('''
            <div class="alert alert-error py-2 text-sm">
                <i class="fa-solid fa-circle-exclamation"></i>
                Class not found
            </div>
        ''')


@login_required
@teacher_or_admin_required
def notify_absent(request):
    """Notify parents of absent students."""
    today = timezone.now().date()

    if request.method == 'GET':
        # Get today's absent students
        absent_records = AttendanceRecord.objects.filter(
            session__date=today,
            status='A'
        ).select_related('student', 'session__class_assigned')

        # Prefetch guardians to avoid N+1 on guardian_phone
        absent_record_list = list(absent_records)
        _prefetch_primary_guardians([r.student for r in absent_record_list])

        absent_students = []
        for record in absent_record_list:
            if record.student.guardian_phone:
                absent_students.append({
                    'student': record.student,
                    'class': record.session.class_assigned,
                })

        # Get default template
        template = SMSTemplate.objects.filter(
            message_type=SMSMessage.MessageType.ATTENDANCE,
            is_active=True
        ).first()

        default_message = template.content if template else (
            "Dear Parent, your child {student_name} was marked absent from school today. "
            "Please contact the school if this is unexpected."
        )

        return render(request, 'communications/partials/modal_notify_absent.html', {
            'absent_students': absent_students,
            'default_message': default_message,
            'date': today,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    message_template = request.POST.get('message', '').strip()
    student_ids = request.POST.getlist('student_ids')

    if not message_template:
        return render(request, 'communications/partials/modal_notify_absent.html', {
            'error': 'Message is required.',
            'date': today,
        })

    # Validate student_ids are valid integers (Student PK is BigAutoField)
    valid_student_ids = []
    for sid in student_ids:
        try:
            valid_student_ids.append(int(sid))
        except (ValueError, TypeError):
            continue

    if not valid_student_ids:
        return render(request, 'communications/partials/modal_notify_absent.html', {
            'error': 'Please select at least one student.',
            'date': today,
        })

    # Fetch all students and prefetch guardians to avoid N+1
    students = list(Student.objects.filter(
        pk__in=valid_student_ids
    ).select_related('current_class'))
    _prefetch_primary_guardians(students)

    # Filter to students with valid phone numbers
    students_with_phone = [s for s in students if s.guardian_phone]

    if not students_with_phone:
        return render(request, 'communications/partials/modal_notify_absent.html', {
            'success': True,
            'sent_count': 0,
            'failed_count': 0,
            'date': today,
        })

    # Prepare date string once
    date_str = today.strftime('%B %d, %Y')
    school = getattr(connection, 'tenant', None)
    school_name = school.display_name if school else ''

    # Prepare SMS records for bulk creation, deduplicating by phone number
    sms_records = []
    student_sms_map = {}  # Map student_id to (sms_record, phone, message)
    seen_phones = set()  # Track phones to avoid sending duplicates (e.g. siblings)

    for student in students_with_phone:
        phone = normalize_phone_number(student.guardian_phone)
        if not phone:
            continue

        if phone in seen_phones:
            continue
        seen_phones.add(phone)

        # Personalize message
        message = message_template.replace('{student_name}', student.full_name)
        message = message.replace('{class_name}', student.current_class.name if student.current_class else '')
        message = message.replace('{date}', date_str)
        message = message.replace('{school_name}', school_name)

        sms = SMSMessage(
            recipient_phone=phone,
            recipient_name=student.guardian_name or '',
            student=student,
            message=message,
            message_type=SMSMessage.MessageType.ATTENDANCE,
            created_by=request.user,
        )
        sms_records.append(sms)
        student_sms_map[student.pk] = (sms, phone, message)

    # Bulk create all SMS records (single INSERT)
    SMSMessage.objects.bulk_create(sms_records)

    # Queue Celery tasks directly (don't use send_sms() which creates duplicate records)
    from .tasks import send_communication_task
    from django.db import connection as db_connection

    queued_count = 0
    failed_count = 0
    for student in students_with_phone:
        if student.pk not in student_sms_map:
            continue

        sms, phone, message = student_sms_map[student.pk]
        try:
            send_communication_task.delay(
                db_connection.schema_name,
                phone,
                message,
                sms_record_id=str(sms.pk)
            )
            queued_count += 1
        except Exception as e:
            logger.error("Failed to queue SMS for student %s: %s", student.pk, e)
            sms.mark_failed("Failed to queue for sending")
            failed_count += 1

    # Show success state with counts
    return render(request, 'communications/partials/modal_notify_absent.html', {
        'success': True,
        'sent_count': queued_count,
        'failed_count': failed_count,
        'date': today,
    })


@login_required
@admin_required
def staff_recipients(request):
    """Get staff recipient counts (HTMX endpoint)."""
    group = request.GET.get('group', 'all')

    teachers = Teacher.objects.filter(status=Teacher.Status.ACTIVE)
    if group == 'teaching':
        teachers = teachers.filter(staff_category=Teacher.StaffCategory.TEACHING)
    elif group == 'non_teaching':
        teachers = teachers.filter(staff_category=Teacher.StaffCategory.NON_TEACHING)

    total = teachers.count()
    with_phone = teachers.exclude(phone_number='').exclude(phone_number__isnull=True).count()
    with_email = teachers.exclude(email='').exclude(email__isnull=True).count()

    group_label = escape({'all': 'All Staff', 'teaching': 'Teaching Staff', 'non_teaching': 'Non-Teaching Staff'}.get(group, 'All Staff'))

    return HttpResponse(f'''
        <div class="bg-base-200 rounded-lg p-3">
            <div class="flex items-center justify-between text-sm">
                <span class="font-medium">{group_label}</span>
                <span class="badge badge-primary">{total} staff</span>
            </div>
            <div class="flex items-center gap-4 mt-2 text-xs text-base-content/70">
                <span class="flex items-center gap-1">
                    <i class="fa-solid fa-phone text-success"></i>
                    {with_phone} with phone
                </span>
                <span class="flex items-center gap-1">
                    <i class="fa-solid fa-envelope text-info"></i>
                    {with_email} with email
                </span>
            </div>
        </div>
    ''')


@login_required
@teacher_or_admin_required
def message_history(request):
    """View SMS/Email message history with filters."""
    channel = request.GET.get('channel', 'sms')

    if channel == 'email':
        messages = EmailMessage.objects.select_related('teacher', 'created_by')
    else:
        channel = 'sms'
        messages = SMSMessage.objects.select_related('student', 'created_by')

    # Filters
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    search = request.GET.get('search', '').strip()

    if status_filter:
        messages = messages.filter(status=status_filter)
    if type_filter:
        messages = messages.filter(message_type=type_filter)
    if search:
        if channel == 'email':
            messages = messages.filter(
                Q(recipient_email__icontains=search) |
                Q(recipient_name__icontains=search) |
                Q(subject__icontains=search) |
                Q(message__icontains=search)
            )
        else:
            messages = messages.filter(
                Q(recipient_phone__icontains=search) |
                Q(recipient_name__icontains=search) |
                Q(message__icontains=search)
            )

    # Pagination with selectable page size
    per_page = request.GET.get('per_page', '25')
    try:
        per_page = int(per_page)
        if per_page not in [25, 50, 100]:
            per_page = 25
    except ValueError:
        per_page = 25

    paginator = Paginator(messages, per_page)
    page_number = request.GET.get('page', 1)
    messages_page = paginator.get_page(page_number)

    if channel == 'email':
        status_choices = EmailMessage.Status.choices
        type_choices = EmailMessage.MessageType.choices
    else:
        status_choices = SMSMessage.Status.choices
        type_choices = SMSMessage.MessageType.choices

    context = {
        'messages': messages_page,
        'page_obj': messages_page,
        'paginator': paginator,
        'per_page': per_page,
        'channel': channel,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'search': search,
        'status_choices': status_choices,
        'type_choices': type_choices,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Communications', 'url': '/communications/'},
            {'label': 'History'},
        ],
        'back_url': '/communications/',
    }

    return htmx_render(
        request,
        'communications/history.html',
        'communications/partials/history_content.html',
        context
    )


@login_required
@teacher_or_admin_required
def message_history_export(request):
    """Export message history to Excel."""
    messages = SMSMessage.objects.select_related('student', 'created_by')

    # Apply filters
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    search = request.GET.get('search', '').strip()

    if status_filter:
        messages = messages.filter(status=status_filter)
    if type_filter:
        messages = messages.filter(message_type=type_filter)
    if search:
        messages = messages.filter(
            Q(recipient_phone__icontains=search) |
            Q(recipient_name__icontains=search) |
            Q(message__icontains=search)
        )

    # Limit export to 10,000 records to prevent OOM
    MAX_EXPORT_ROWS = 10000
    messages = messages.order_by('-created_at')[:MAX_EXPORT_ROWS]

    # Prepare data for export
    data = []
    for msg in messages.iterator():
        data.append({
            'Recipient Name': msg.recipient_name or '-',
            'Phone': msg.recipient_phone,
            'Student': msg.student.full_name if msg.student else '-',
            'Message': msg.message,
            'Type': msg.get_message_type_display(),
            'Status': msg.get_status_display(),
            'Error': msg.error_message or '-',
            'Sent By': msg.created_by.get_full_name() if msg.created_by else '-',
            'Created': msg.created_at.strftime('%Y-%m-%d %H:%M') if msg.created_at else '-',
            'Sent At': msg.sent_at.strftime('%Y-%m-%d %H:%M') if msg.sent_at else '-',
        })

    df = pd.DataFrame(data)

    # Create Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Messages')

        # Auto-adjust column widths
        from openpyxl.utils import get_column_letter
        worksheet = writer.sheets['Messages']
        for idx, col in enumerate(df.columns):
            max_length = max(
                df[col].astype(str).map(len).max() if len(df) > 0 else 0,
                len(col)
            )
            # Limit max width to prevent very wide columns
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[get_column_letter(idx + 1)].width = adjusted_width

    output.seek(0)

    timestamp = timezone.now().strftime('%Y%m%d_%H%M')
    filename = f'sms_history_{timestamp}.xlsx'

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@admin_required
def templates_list(request):
    """Manage SMS templates."""
    templates = SMSTemplate.objects.all()

    context = {
        'templates': templates,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Communications', 'url': '/communications/'},
            {'label': 'Templates'},
        ],
        'back_url': '/communications/',
    }

    return htmx_render(
        request,
        'communications/templates.html',
        'communications/partials/templates_content.html',
        context
    )


@login_required
@admin_required
def template_create(request):
    """Create a new SMS template."""
    if request.method == 'GET':
        return render(request, 'communications/partials/modal_template_form.html', {
            'type_choices': SMSMessage.MessageType.choices,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    name = request.POST.get('name', '').strip()
    content = request.POST.get('content', '').strip()
    message_type = request.POST.get('message_type', SMSMessage.MessageType.GENERAL)
    valid_types = {c[0] for c in SMSMessage.MessageType.choices}

    if not name or not content:
        return render(request, 'communications/partials/modal_template_form.html', {
            'error': 'Name and content are required.',
            'type_choices': SMSMessage.MessageType.choices,
        })

    if message_type not in valid_types:
        message_type = SMSMessage.MessageType.GENERAL

    SMSTemplate.objects.create(
        name=name,
        content=content,
        message_type=message_type,
    )

    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    return redirect('communications:templates')


@login_required
@admin_required
def template_edit(request, pk):
    """Edit an existing SMS template."""
    template = get_object_or_404(SMSTemplate, pk=pk)

    if request.method == 'GET':
        return render(request, 'communications/partials/modal_template_form.html', {
            'template': template,
            'type_choices': SMSMessage.MessageType.choices,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    name = request.POST.get('name', '').strip()
    content = request.POST.get('content', '').strip()
    message_type = request.POST.get('message_type', template.message_type)
    valid_types = {c[0] for c in SMSMessage.MessageType.choices}

    if not name or not content:
        return render(request, 'communications/partials/modal_template_form.html', {
            'template': template,
            'error': 'Name and content are required.',
            'type_choices': SMSMessage.MessageType.choices,
        })

    if message_type not in valid_types:
        message_type = SMSMessage.MessageType.GENERAL

    template.name = name
    template.content = content
    template.message_type = message_type
    template.save(update_fields=['name', 'content', 'message_type'])

    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    return redirect('communications:templates')


@login_required
@admin_required
def template_delete(request, pk):
    """Delete an SMS template."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    template = get_object_or_404(SMSTemplate, pk=pk)
    template_name = template.name
    template.delete()

    django_messages.success(request, f'Template "{template_name}" has been deleted.')

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Redirect'] = reverse('communications:templates')
        return response

    return redirect('communications:templates')


# =============================================================================
# ANNOUNCEMENTS
# =============================================================================

def _get_students_for_scope(scope, scope_detail):
    """Return active students filtered by scope. Prefetches guardians."""
    students = Student.objects.filter(status='active').select_related('current_class')
    if scope == 'level' and scope_detail:
        try:
            level_type, level_number = scope_detail.split(':')
            students = students.filter(
                current_class__level_type=level_type,
                current_class__level_number=int(level_number),
            )
        except (ValueError, AttributeError):
            students = students.none()
    elif scope == 'class' and scope_detail:
        students = students.filter(current_class_id=scope_detail)
    elif scope == 'individual' and scope_detail:
        ids = [i.strip() for i in scope_detail.split(',') if i.strip()]
        valid_ids = []
        for i in ids:
            try:
                valid_ids.append(int(i))
            except (ValueError, TypeError):
                pass
        students = students.filter(pk__in=valid_ids)
    result = list(students)
    _prefetch_primary_guardians(result)
    return result


@login_required
@admin_required
def announcement_recipients(request):
    """HTMX endpoint: return recipient count + coverage stats."""
    audience = request.GET.get('audience', 'staff')
    scope = request.GET.get('scope', 'all')
    scope_detail = request.GET.get('scope_detail', '')

    if audience == 'staff':
        teachers = Teacher.objects.filter(status=Teacher.Status.ACTIVE)
        if scope == 'teaching':
            teachers = teachers.filter(staff_category=Teacher.StaffCategory.TEACHING)
        elif scope == 'non_teaching':
            teachers = teachers.filter(staff_category=Teacher.StaffCategory.NON_TEACHING)
        elif scope == 'individual' and scope_detail:
            ids = [i.strip() for i in scope_detail.split(',') if i.strip()]
            teachers = teachers.filter(pk__in=ids)
        total = teachers.count()
        with_phone = teachers.exclude(phone_number='').exclude(phone_number__isnull=True).count()
        with_email = teachers.exclude(email='').exclude(email__isnull=True).count()
        return HttpResponse(f'''
            <div class="bg-base-200 rounded-lg p-3">
                <div class="flex items-center justify-between text-sm">
                    <span class="font-medium">Staff</span>
                    <span class="badge badge-primary">{total} recipients</span>
                </div>
                <div class="flex items-center gap-4 mt-2 text-xs text-base-content/70">
                    <span class="flex items-center gap-1">
                        <i class="fa-solid fa-phone text-success"></i>
                        {with_phone} with phone
                    </span>
                    <span class="flex items-center gap-1">
                        <i class="fa-solid fa-envelope text-info"></i>
                        {with_email} with email
                    </span>
                </div>
            </div>
        ''')

    # Parents or Students
    students_qs = Student.objects.filter(status='active').select_related('current_class')
    if scope == 'level' and scope_detail:
        try:
            level_type, level_number = scope_detail.split(':')
            students_qs = students_qs.filter(
                current_class__level_type=level_type,
                current_class__level_number=int(level_number),
            )
        except (ValueError, AttributeError):
            students_qs = students_qs.none()
    elif scope == 'class' and scope_detail:
        students_qs = students_qs.filter(current_class_id=scope_detail)
    elif scope == 'individual' and scope_detail:
        ids = [i.strip() for i in scope_detail.split(',') if i.strip()]
        students_qs = students_qs.filter(pk__in=ids)

    total = students_qs.count()

    if audience == 'parents':
        with_phone = students_qs.filter(
            student_guardians__is_primary=True,
            student_guardians__guardian__phone_number__isnull=False,
        ).exclude(
            student_guardians__guardian__phone_number='',
        ).distinct().count()
        with_email = students_qs.filter(
            student_guardians__is_primary=True,
            student_guardians__guardian__email__isnull=False,
        ).exclude(
            student_guardians__guardian__email='',
        ).distinct().count()
        label = 'Parents'
        phone_label = f'{with_phone} guardians with phone'
        email_html = f'''
            <span class="flex items-center gap-1">
                <i class="fa-solid fa-envelope text-info"></i>
                {with_email} with email
            </span>
        '''
    else:
        with_phone = students_qs.exclude(phone='').exclude(phone__isnull=True).count()
        label = 'Students'
        phone_label = f'{with_phone} with phone'
        email_html = ''

    return HttpResponse(f'''
        <div class="bg-base-200 rounded-lg p-3">
            <div class="flex items-center justify-between text-sm">
                <span class="font-medium">{escape(label)}</span>
                <span class="badge badge-primary">{total} recipients</span>
            </div>
            <div class="flex items-center gap-4 mt-2 text-xs text-base-content/70">
                <span class="flex items-center gap-1">
                    <i class="fa-solid fa-phone text-success"></i>
                    {phone_label}
                </span>
                {email_html}
            </div>
        </div>
    ''')


@login_required
@admin_required
def announcement_search(request):
    """HTMX endpoint: search recipients for individual scope."""
    audience = request.GET.get('audience', 'staff')
    q = request.GET.get('q', '').strip()

    if len(q) < 2:
        return HttpResponse('<div class="text-xs text-base-content/50 p-2">Type at least 2 characters...</div>')

    items = []
    if audience == 'staff':
        teachers = Teacher.objects.filter(
            status=Teacher.Status.ACTIVE,
        ).filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )[:15]
        for t in teachers:
            items.append(f'''
                <button type="button"
                        class="flex items-center gap-2 p-2 hover:bg-base-200 rounded w-full text-left"
                        @click="addRecipient('{t.pk}', '{escape(t.full_name)}')">
                    <i class="fa-solid fa-user-tie text-accent text-xs"></i>
                    <span class="text-sm">{escape(t.full_name)}</span>
                    <span class="text-xs text-base-content/50 ml-auto">{escape(t.phone_number or 'No phone')}</span>
                </button>
            ''')
    else:
        students = Student.objects.filter(
            status='active',
        ).filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
        ).select_related('current_class')[:15]
        _prefetch_primary_guardians(list(students))
        for s in students:
            if audience == 'parents':
                detail = escape(s.guardian_name or 'No guardian')
            else:
                detail = escape(s.current_class.name if s.current_class else 'No class')
            items.append(f'''
                <button type="button"
                        class="flex items-center gap-2 p-2 hover:bg-base-200 rounded w-full text-left"
                        @click="addRecipient('{s.pk}', '{escape(s.full_name)}')">
                    <i class="fa-solid fa-user-graduate text-primary text-xs"></i>
                    <span class="text-sm">{escape(s.full_name)}</span>
                    <span class="text-xs text-base-content/50 ml-auto">{detail}</span>
                </button>
            ''')

    if not items:
        return HttpResponse('<div class="text-xs text-base-content/50 p-2">No results found</div>')

    return HttpResponse('<div class="divide-y divide-base-200">' + ''.join(items) + '</div>')


@login_required
@admin_required
def announcements_list(request):
    """Admin list of all announcements."""
    announcements = Announcement.objects.select_related('created_by').annotate(
        read_count=Count('reads'),
    ).order_by('-created_at')

    paginator = Paginator(announcements, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'announcements': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Communications', 'url': '/communications/'},
            {'label': 'Announcements'},
        ],
        'back_url': '/communications/',
    }

    return htmx_render(
        request,
        'communications/announcements.html',
        'communications/partials/announcements_content.html',
        context
    )


@login_required
@admin_required
def announcement_create(request):
    """Create a new announcement targeting staff, parents, or students."""
    sms_gateway = get_sms_gateway_status()
    email_gateway = get_email_gateway_status()
    classes = Class.objects.filter(is_active=True).order_by('level_type', 'level_number', 'name')

    breadcrumbs = [
        {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
        {'label': 'Communications', 'url': '/communications/'},
        {'label': 'Announcements', 'url': reverse('communications:announcements')},
        {'label': 'New Announcement'},
    ]
    back_url = reverse('communications:announcements')

    if request.method == 'GET':
        context = {
            'sms_gateway': sms_gateway,
            'email_gateway': email_gateway,
            'classes': classes,
            'breadcrumbs': breadcrumbs,
            'back_url': back_url,
        }
        return htmx_render(
            request,
            'communications/announcement_create.html',
            'communications/partials/announcement_create.html',
            context
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    title = request.POST.get('title', '').strip()
    message_text = request.POST.get('message', '').strip()
    audience = request.POST.get('audience', 'staff')
    scope = request.POST.get('scope', 'all')
    scope_detail = request.POST.get('scope_detail', '').strip()
    priority = request.POST.get('priority', 'normal')
    send_sms = request.POST.get('send_sms') == 'on'
    send_email = request.POST.get('send_email') == 'on'
    subject = request.POST.get('subject', '').strip()

    # Validate choices
    valid_audiences = {c[0] for c in Announcement.Audience.choices}
    if audience not in valid_audiences:
        audience = 'staff'
    valid_scopes = {c[0] for c in Announcement.Scope.choices}
    if scope not in valid_scopes:
        scope = 'all'
    valid_priorities = {c[0] for c in Announcement.Priority.choices}
    if priority not in valid_priorities:
        priority = 'normal'

    form_context = {
        'sms_gateway': sms_gateway,
        'email_gateway': email_gateway,
        'classes': classes,
        'title': title,
        'message': message_text,
        'audience': audience,
        'scope': scope,
        'scope_detail': scope_detail,
        'priority': priority,
        'send_sms_checked': send_sms,
        'send_email_checked': send_email,
        'subject': subject,
        'breadcrumbs': breadcrumbs,
        'back_url': back_url,
    }

    if not title or not message_text:
        form_context['error'] = 'Title and message are required.'
        return htmx_render(
            request,
            'communications/announcement_create.html',
            'communications/partials/announcement_create.html',
            form_context
        )

    if send_email and not subject:
        form_context['error'] = 'Subject is required when sending email.'
        return htmx_render(
            request,
            'communications/announcement_create.html',
            'communications/partials/announcement_create.html',
            form_context
        )

    school = getattr(connection, 'tenant', None)
    school_name = school.display_name if school else ''

    # Resolve recipients and dispatch sending based on audience
    from core.models import Notification
    recipient_count = 0

    if audience == 'staff':
        # Map scope to teacher group filter
        if scope in ('teaching', 'non_teaching'):
            group = scope
        elif scope == 'individual' and scope_detail:
            group = 'individual'
        else:
            group = 'all'

        if group == 'individual':
            ids = [i.strip() for i in scope_detail.split(',') if i.strip()]
            teachers = list(Teacher.objects.filter(
                status=Teacher.Status.ACTIVE, pk__in=ids,
            ))
            if send_email:
                for t in teachers:
                    if not hasattr(t, 'user'):
                        pass  # user already loaded
                teachers = list(Teacher.objects.filter(
                    status=Teacher.Status.ACTIVE, pk__in=ids,
                ).select_related('user'))
        else:
            teachers = _get_targeted_teachers(group, need_email=send_email)

        recipient_count = len(teachers)

        # Create the announcement
        announcement = Announcement.objects.create(
            title=title,
            message=message_text,
            audience=audience,
            scope=scope,
            scope_detail=scope_detail,
            target_group=group if group in ('all', 'teaching', 'non_teaching') else 'all',
            priority=priority,
            sent_via_sms=send_sms,
            sent_via_email=send_email,
            recipient_count=recipient_count,
            created_by=request.user,
        )

        # Bell notifications for staff with user accounts
        detail_url = reverse('communications:announcement_detail', args=[announcement.pk])
        notification_type = 'warning' if priority == 'urgent' else 'info'
        for teacher in teachers:
            if teacher.user_id:
                Notification.create_notification(
                    user=teacher.user,
                    title=f'Announcement: {title}',
                    message=message_text[:200],
                    notification_type=notification_type,
                    category='system',
                    icon='fa-solid fa-bullhorn',
                    link=detail_url,
                )

        if send_sms:
            _send_bulk_sms_to_teachers(
                teachers, message_text, school_name, request.user,
                message_type=SMSMessage.MessageType.ANNOUNCEMENT,
            )
        if send_email:
            _send_bulk_email_to_teachers(
                teachers, subject, message_text, school_name, request.user,
                message_type=EmailMessage.MessageType.ANNOUNCEMENT,
            )

    elif audience == 'parents':
        students = _get_students_for_scope(scope, scope_detail)
        recipient_count = len(students)

        announcement = Announcement.objects.create(
            title=title,
            message=message_text,
            audience=audience,
            scope=scope,
            scope_detail=scope_detail,
            priority=priority,
            sent_via_sms=send_sms,
            sent_via_email=send_email,
            recipient_count=recipient_count,
            created_by=request.user,
        )

        if send_sms:
            _send_bulk_sms_to_parents(
                students, message_text, school_name, request.user,
            )
        if send_email:
            _send_bulk_email_to_parents(
                students, subject, message_text, school_name, request.user,
            )

    else:  # students
        students = _get_students_for_scope(scope, scope_detail)
        recipient_count = len(students)

        announcement = Announcement.objects.create(
            title=title,
            message=message_text,
            audience=audience,
            scope=scope,
            scope_detail=scope_detail,
            priority=priority,
            sent_via_sms=send_sms,
            sent_via_email=False,  # Email not supported for students yet
            recipient_count=recipient_count,
            created_by=request.user,
        )

        if send_sms:
            _send_bulk_sms_to_students(
                students, message_text, school_name, request.user,
            )

    audience_label = announcement.get_audience_display_label()
    django_messages.success(
        request,
        f'Announcement "{title}" posted to {recipient_count} recipients ({audience_label}).'
    )

    detail_redirect_url = reverse('communications:announcement_detail', args=[announcement.pk])
    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Redirect'] = detail_redirect_url
        return response
    return redirect(detail_redirect_url)


@login_required
@teacher_or_admin_required
def announcement_detail(request, pk):
    """View a single announcement."""
    announcement = get_object_or_404(
        Announcement.objects.select_related('created_by'),
        pk=pk
    )

    # Mark as read for current user
    AnnouncementRead.objects.get_or_create(
        announcement=announcement,
        user=request.user,
    )

    # Admin stats
    read_count = None
    if is_school_admin(request.user):
        read_count = announcement.reads.count()

    context = {
        'announcement': announcement,
        'read_count': read_count,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Communications', 'url': '/communications/'},
            {'label': 'Announcements', 'url': reverse('communications:announcements') if is_school_admin(request.user) else reverse('communications:announcements_feed')},
            {'label': announcement.title},
        ],
        'back_url': reverse('communications:announcements') if is_school_admin(request.user) else reverse('communications:announcements_feed'),
    }

    return htmx_render(
        request,
        'communications/announcement_detail.html',
        'communications/partials/announcement_detail.html',
        context
    )


@login_required
@teacher_or_admin_required
def announcements_feed(request):
    """Staff feed of announcements matching their category."""
    user = request.user
    teacher = getattr(user, 'teacher_profile', None)

    # Filter announcements relevant to this user (staff-audience only)
    announcements = Announcement.objects.select_related('created_by').filter(
        audience='staff',
    )

    if teacher:
        if teacher.staff_category == Teacher.StaffCategory.TEACHING:
            announcements = announcements.filter(
                scope__in=['all', 'teaching', 'individual']
            )
        elif teacher.staff_category == Teacher.StaffCategory.NON_TEACHING:
            announcements = announcements.filter(
                scope__in=['all', 'non_teaching', 'individual']
            )
    # Admins without teacher profile see all staff announcements

    # Annotate read/unread for this user
    announcements = announcements.annotate(
        is_read=Exists(
            AnnouncementRead.objects.filter(
                announcement=OuterRef('pk'),
                user=user,
            )
        )
    )

    paginator = Paginator(announcements, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'announcements': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Communications', 'url': '/communications/'},
            {'label': 'Announcements'},
        ],
        'back_url': '/communications/',
    }

    return htmx_render(
        request,
        'communications/announcements_feed.html',
        'communications/partials/announcements_feed.html',
        context
    )
