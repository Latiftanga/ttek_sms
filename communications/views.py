from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Q

from .models import SMSMessage, SMSTemplate
from .utils import send_sms, validate_phone_number
from students.models import Student
from academics.models import Class, AttendanceSession, AttendanceRecord
from core.models import SchoolSettings


def htmx_render(request, full_template, partial_template, context=None):
    """Render full template for regular requests, partial for HTMX requests."""
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)


@login_required
def index(request):
    """SMS dashboard with recent messages and quick actions."""
    messages = SMSMessage.objects.select_related('student', 'created_by')[:50]
    templates = SMSTemplate.objects.filter(is_active=True)

    # Stats
    today = timezone.now().date()
    stats = {
        'total_today': SMSMessage.objects.filter(created_at__date=today).count(),
        'sent_today': SMSMessage.objects.filter(created_at__date=today, status='sent').count(),
        'failed_today': SMSMessage.objects.filter(created_at__date=today, status='failed').count(),
        'pending': SMSMessage.objects.filter(status='pending').count(),
    }

    context = {
        'messages': messages,
        'templates': templates,
        'stats': stats,
    }

    return htmx_render(
        request,
        'communications/index.html',
        'communications/partials/index_content.html',
        context
    )


@login_required
def send_single(request):
    """Send SMS to a single recipient."""
    templates = SMSTemplate.objects.filter(is_active=True)

    if request.method == 'GET':
        return render(request, 'communications/partials/modal_send_single.html', {
            'templates': templates,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    phone = request.POST.get('phone', '').strip()
    message = request.POST.get('message', '').strip()
    recipient_name = request.POST.get('recipient_name', '').strip()

    if not phone or not message:
        return render(request, 'communications/partials/modal_send_single.html', {
            'error': 'Phone number and message are required.',
            'templates': templates,
            'phone': phone,
            'message': message,
            'recipient_name': recipient_name,
        })

    # Normalize phone number (add Ghana country code if needed)
    if phone.startswith('0'):
        phone = '+233' + phone[1:]
    elif not phone.startswith('+'):
        phone = '+233' + phone

    try:
        validate_phone_number(phone)
    except Exception as e:
        return render(request, 'communications/partials/modal_send_single.html', {
            'error': str(e),
            'templates': templates,
            'phone': phone,
            'message': message,
            'recipient_name': recipient_name,
        })

    # Create SMS record
    sms = SMSMessage.objects.create(
        recipient_phone=phone,
        recipient_name=recipient_name,
        message=message,
        message_type=SMSMessage.MessageType.GENERAL,
        created_by=request.user,
    )

    # Send SMS
    try:
        send_sms(phone, message)
        sms.mark_sent()
    except Exception as e:
        sms.mark_failed(str(e))
        return render(request, 'communications/partials/modal_send_single.html', {
            'error': f'Failed to send: {str(e)}',
            'templates': templates,
            'phone': phone,
            'message': message,
            'recipient_name': recipient_name,
        })

    # Show success state
    return render(request, 'communications/partials/modal_send_single.html', {
        'success': True,
    })


@login_required
def send_to_class(request):
    """Send SMS to all parents in a class."""
    classes = Class.objects.filter(is_active=True).order_by('level_number', 'name')
    templates = SMSTemplate.objects.filter(is_active=True)

    if request.method == 'GET':
        return render(request, 'communications/partials/modal_send_class.html', {
            'classes': classes,
            'templates': templates,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    class_id = request.POST.get('class_id')
    message = request.POST.get('message', '').strip()

    if not class_id or not message:
        return render(request, 'communications/partials/modal_send_class.html', {
            'error': 'Class and message are required.',
            'classes': classes,
            'templates': templates,
            'selected_class': int(class_id) if class_id else None,
            'message': message,
        })

    class_obj = get_object_or_404(Class, pk=class_id)
    students = Student.objects.filter(current_class=class_obj, status='active')

    sent_count = 0
    failed_count = 0
    skipped_count = 0

    for student in students:
        phone = student.guardian_phone
        if not phone:
            skipped_count += 1
            continue

        # Normalize phone
        if phone.startswith('0'):
            phone = '+233' + phone[1:]
        elif not phone.startswith('+'):
            phone = '+233' + phone

        # Personalize message
        personalized = message.replace('{student_name}', student.full_name)
        personalized = personalized.replace('{class_name}', class_obj.name)

        sms = SMSMessage.objects.create(
            recipient_phone=phone,
            recipient_name=student.guardian_name or '',
            student=student,
            message=personalized,
            message_type=SMSMessage.MessageType.ANNOUNCEMENT,
            created_by=request.user,
        )

        try:
            send_sms(phone, personalized)
            sms.mark_sent()
            sent_count += 1
        except Exception as e:
            sms.mark_failed(str(e))
            failed_count += 1

    # Show success state with counts
    return render(request, 'communications/partials/modal_send_class.html', {
        'success': True,
        'sent_count': sent_count,
        'failed_count': failed_count,
        'skipped_count': skipped_count,
    })


@login_required
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
        with_phone = students.exclude(guardian_phone='').exclude(guardian_phone__isnull=True).count()
        without_phone = total_students - with_phone

        return HttpResponse(f'''
            <div class="bg-base-200 rounded-lg p-3">
                <div class="flex items-center justify-between text-sm">
                    <span class="font-medium">{class_obj.name}</span>
                    <span class="badge badge-primary">{total_students} students</span>
                </div>
                <div class="flex items-center gap-4 mt-2 text-xs text-base-content/70">
                    <span class="flex items-center gap-1">
                        <i class="fa-solid fa-check text-success"></i>
                        {with_phone} with phone
                    </span>
                    {'<span class="flex items-center gap-1 text-warning"><i class="fa-solid fa-triangle-exclamation"></i>' + str(without_phone) + ' without phone</span>' if without_phone > 0 else ''}
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
def notify_absent(request):
    """Notify parents of absent students."""
    today = timezone.now().date()

    if request.method == 'GET':
        # Get today's absent students
        absent_records = AttendanceRecord.objects.filter(
            session__date=today,
            status='A'
        ).select_related('student', 'session__class_assigned')

        absent_students = []
        for record in absent_records:
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
    school = SchoolSettings.load()

    if not message_template:
        return render(request, 'communications/partials/modal_notify_absent.html', {
            'error': 'Message is required.',
            'date': today,
        })

    if not student_ids:
        return render(request, 'communications/partials/modal_notify_absent.html', {
            'error': 'Please select at least one student.',
            'date': today,
        })

    sent_count = 0
    failed_count = 0

    for student_id in student_ids:
        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            continue

        phone = student.guardian_phone
        if not phone:
            continue

        # Normalize phone
        if phone.startswith('0'):
            phone = '+233' + phone[1:]
        elif not phone.startswith('+'):
            phone = '+233' + phone

        # Personalize message
        message = message_template.replace('{student_name}', student.full_name)
        message = message.replace('{class_name}', student.current_class.name if student.current_class else '')
        message = message.replace('{date}', today.strftime('%B %d, %Y'))
        message = message.replace('{school_name}', school.display_name or '')

        sms = SMSMessage.objects.create(
            recipient_phone=phone,
            recipient_name=student.guardian_name or '',
            student=student,
            message=message,
            message_type=SMSMessage.MessageType.ATTENDANCE,
            created_by=request.user,
        )

        try:
            send_sms(phone, message)
            sms.mark_sent()
            sent_count += 1
        except Exception as e:
            sms.mark_failed(str(e))
            failed_count += 1

    # Show success state with counts
    return render(request, 'communications/partials/modal_notify_absent.html', {
        'success': True,
        'sent_count': sent_count,
        'failed_count': failed_count,
        'date': today,
    })


@login_required
def message_history(request):
    """View SMS message history with filters."""
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
        messages = messages.filter(
            Q(recipient_phone__icontains=search) |
            Q(recipient_name__icontains=search) |
            Q(message__icontains=search)
        )

    messages = messages[:100]

    context = {
        'messages': messages,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'search': search,
        'status_choices': SMSMessage.Status.choices,
        'type_choices': SMSMessage.MessageType.choices,
    }

    return htmx_render(
        request,
        'communications/history.html',
        'communications/partials/history_content.html',
        context
    )


@login_required
def templates_list(request):
    """Manage SMS templates."""
    templates = SMSTemplate.objects.all()

    return htmx_render(
        request,
        'communications/templates.html',
        'communications/partials/templates_content.html',
        {'templates': templates}
    )


@login_required
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

    if not name or not content:
        return render(request, 'communications/partials/modal_template_form.html', {
            'error': 'Name and content are required.',
            'type_choices': SMSMessage.MessageType.choices,
        })

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
def template_delete(request, pk):
    """Delete an SMS template."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    template = get_object_or_404(SMSTemplate, pk=pk)
    template.delete()

    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    return redirect('communications:templates')
