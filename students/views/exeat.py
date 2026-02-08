"""Exeat management views for boarding students."""
import logging
from functools import wraps

from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone

from core.models import AcademicYear
from ..models import Exeat, HouseMaster, Student
from ..forms import ExeatForm, HouseMasterForm
from .utils import admin_required, is_school_admin

logger = logging.getLogger(__name__)


class SMSResult:
    """Result of SMS notification attempt with detailed status."""
    SUCCESS = 'success'
    NO_GUARDIAN = 'no_guardian'
    NO_PHONE = 'no_phone'
    SMS_DISABLED = 'sms_disabled'
    SMS_NOT_CONFIGURED = 'sms_not_configured'
    QUEUE_FAILED = 'queue_failed'
    ERROR = 'error'

    def __init__(self, status, message_id=None, error=None, guardian_phone=None):
        self.status = status
        self.message_id = message_id
        self.error = error
        self.guardian_phone = guardian_phone

    @property
    def is_success(self):
        return self.status == self.SUCCESS

    @property
    def user_message(self):
        """Get user-friendly message for display."""
        messages_map = {
            self.SUCCESS: "SMS notification sent to guardian.",
            self.NO_GUARDIAN: "No primary guardian set for this student. SMS not sent.",
            self.NO_PHONE: "Guardian has no phone number. SMS not sent.",
            self.SMS_DISABLED: "SMS notifications are disabled. Please configure SMS in settings.",
            self.SMS_NOT_CONFIGURED: "SMS gateway not configured. Please set up SMS API in settings.",
            self.QUEUE_FAILED: f"Failed to send SMS: {self.error}",
            self.ERROR: f"SMS error: {self.error}",
        }
        return messages_map.get(self.status, "Unknown SMS status.")


def check_sms_gateway():
    """
    Check if SMS gateway is properly configured.

    Returns:
        tuple: (is_ready, status_message)
    """
    try:
        from communications.utils import get_sms_gateway_status
        status = get_sms_gateway_status()
        return status.get('ready', False), status.get('message', 'Unknown')
    except Exception as e:
        logger.error(f"Error checking SMS gateway: {e}")
        return False, str(e)


def send_exeat_approval_sms(exeat, user=None):
    """
    Send SMS to guardian when exeat is approved.

    Args:
        exeat: The approved Exeat instance
        user: The user who approved (for tracking)

    Returns:
        SMSResult: Result object with status and details
    """
    try:
        from communications.utils import send_sms, get_sms_gateway_status
        from communications.models import SMSMessage

        student = exeat.student
        guardian = student.get_primary_guardian()

        # Validate guardian exists
        if not guardian:
            logger.warning(f"No guardian for student {student.full_name} - skipping SMS")
            return SMSResult(SMSResult.NO_GUARDIAN)

        # Validate guardian has phone
        if not guardian.phone_number:
            logger.warning(f"Guardian {guardian.full_name} has no phone - skipping SMS")
            return SMSResult(SMSResult.NO_PHONE)

        # Check SMS gateway status
        gateway_status = get_sms_gateway_status()
        if not gateway_status.get('enabled'):
            logger.info(f"SMS disabled - not sending exeat approval for {student.full_name}")
            return SMSResult(SMSResult.SMS_DISABLED)

        if not gateway_status.get('ready'):
            logger.warning(f"SMS gateway not ready: {gateway_status.get('message')}")
            return SMSResult(SMSResult.SMS_NOT_CONFIGURED, error=gateway_status.get('message'))

        # Format message based on exeat type - keep concise for SMS
        if exeat.exeat_type == 'internal':
            message = (
                f"Dear {guardian.full_name}, {student.full_name} has been "
                f"granted internal exeat. Dest: {exeat.destination[:30]}. "
                f"Return by {exeat.expected_return_time.strftime('%I:%M%p')}."
            )
        else:
            message = (
                f"Dear {guardian.full_name}, {student.full_name} has been "
                f"granted external exeat. Dest: {exeat.destination[:30]}. "
                f"Leaving {exeat.departure_date.strftime('%d/%m')}. "
                f"Return {exeat.expected_return_date.strftime('%d/%m')}."
            )

        # Send SMS with proper message type and recipient name
        result = send_sms(
            to_phone=guardian.phone_number,
            message=message,
            student=student,
            message_type='exeat',
            created_by=user
        )

        if result.get('success'):
            message_id = result.get('message_id')

            # Link SMS record to exeat for audit trail
            if message_id:
                try:
                    sms_record = SMSMessage.objects.get(pk=message_id)
                    # Update recipient name (fix for missing guardian_name)
                    sms_record.recipient_name = guardian.full_name
                    sms_record.save(update_fields=['recipient_name'])
                    exeat.approval_sms = sms_record
                except SMSMessage.DoesNotExist:
                    pass

            exeat.guardian_notified_approval = True
            exeat.save(update_fields=['guardian_notified_approval', 'approval_sms'])

            logger.info(f"Exeat approval SMS queued for {student.full_name} to {guardian.phone_number}")
            return SMSResult(
                SMSResult.SUCCESS,
                message_id=message_id,
                guardian_phone=guardian.phone_number
            )
        else:
            error = result.get('error', 'Unknown error')
            logger.error(f"Failed to queue exeat SMS: {error}")
            return SMSResult(SMSResult.QUEUE_FAILED, error=error)

    except Exception as e:
        logger.exception(f"Error sending exeat approval SMS: {e}")
        return SMSResult(SMSResult.ERROR, error=str(e))


def send_exeat_return_sms(exeat, user=None):
    """
    Send SMS to guardian when student returns from exeat.

    Args:
        exeat: The completed Exeat instance
        user: The user who marked return (for tracking)

    Returns:
        SMSResult: Result object with status and details
    """
    try:
        from communications.utils import send_sms, get_sms_gateway_status
        from communications.models import SMSMessage

        student = exeat.student
        guardian = student.get_primary_guardian()

        # Validate guardian exists
        if not guardian:
            logger.warning(f"No guardian for student {student.full_name} - skipping return SMS")
            return SMSResult(SMSResult.NO_GUARDIAN)

        # Validate guardian has phone
        if not guardian.phone_number:
            logger.warning(f"Guardian {guardian.full_name} has no phone - skipping return SMS")
            return SMSResult(SMSResult.NO_PHONE)

        # Check SMS gateway status
        gateway_status = get_sms_gateway_status()
        if not gateway_status.get('enabled'):
            logger.info(f"SMS disabled - not sending return notification for {student.full_name}")
            return SMSResult(SMSResult.SMS_DISABLED)

        if not gateway_status.get('ready'):
            logger.warning(f"SMS gateway not ready: {gateway_status.get('message')}")
            return SMSResult(SMSResult.SMS_NOT_CONFIGURED, error=gateway_status.get('message'))

        # Keep message concise
        message = (
            f"Dear {guardian.full_name}, {student.full_name} has safely "
            f"returned to campus. Thank you."
        )

        # Send SMS
        result = send_sms(
            to_phone=guardian.phone_number,
            message=message,
            student=student,
            message_type='exeat',
            created_by=user
        )

        if result.get('success'):
            message_id = result.get('message_id')

            # Link SMS record to exeat
            if message_id:
                try:
                    sms_record = SMSMessage.objects.get(pk=message_id)
                    sms_record.recipient_name = guardian.full_name
                    sms_record.save(update_fields=['recipient_name'])
                    exeat.return_sms = sms_record
                except SMSMessage.DoesNotExist:
                    pass

            exeat.guardian_notified_return = True
            exeat.save(update_fields=['guardian_notified_return', 'return_sms'])

            logger.info(f"Exeat return SMS queued for {student.full_name} to {guardian.phone_number}")
            return SMSResult(
                SMSResult.SUCCESS,
                message_id=message_id,
                guardian_phone=guardian.phone_number
            )
        else:
            error = result.get('error', 'Unknown error')
            logger.error(f"Failed to queue return SMS: {error}")
            return SMSResult(SMSResult.QUEUE_FAILED, error=error)

    except Exception as e:
        logger.exception(f"Error sending exeat return SMS: {e}")
        return SMSResult(SMSResult.ERROR, error=str(e))


def get_teacher_profile(user):
    """Get the teacher profile for a user if they are a teacher."""
    if getattr(user, 'is_teacher', False):
        return getattr(user, 'teacher_profile', None)
    return None


def get_housemaster_assignment(user):
    """Get the housemaster assignment for the current user/academic year."""
    teacher = get_teacher_profile(user)
    if not teacher:
        return None
    current_year = AcademicYear.get_current()
    if not current_year:
        return None
    return HouseMaster.objects.filter(
        teacher=teacher,
        academic_year=current_year,
        is_active=True
    ).select_related('house').first()


def is_housemaster(user):
    """Check if user is assigned as a housemaster."""
    return get_housemaster_assignment(user) is not None


def is_senior_housemaster(user):
    """Check if user is the senior housemaster."""
    assignment = get_housemaster_assignment(user)
    return assignment and assignment.is_senior


def housemaster_required(view_func):
    """Decorator to require housemaster or admin access."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if getattr(request, 'htmx', None):
                return HttpResponse(status=401)
            return redirect('accounts:login')
        if not (is_school_admin(request.user) or is_housemaster(request.user)):
            if getattr(request, 'htmx', None):
                return HttpResponse(
                    '<div class="text-error text-sm p-2">Access denied. Housemaster role required.</div>',
                    status=403
                )
            messages.error(request, "You don't have permission to access this page.")
            return redirect('core:index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def admin_or_senior_required(view_func):
    """Decorator to require school admin or senior housemaster access."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if getattr(request, 'htmx', None):
                return HttpResponse(status=401)
            return redirect('accounts:login')
        if not (is_school_admin(request.user) or is_senior_housemaster(request.user)):
            if getattr(request, 'htmx', None):
                return HttpResponse(
                    '<div class="text-error text-sm p-2">Access denied. Admin or Senior Housemaster role required.</div>',
                    status=403
                )
            messages.error(request, "You don't have permission to access this page.")
            return redirect('core:index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# ============ Exeat Views ============

@login_required
@housemaster_required
def exeat_index(request):
    """List exeats - filtered by housemaster's house or all for admin/senior."""
    user = request.user
    assignment = get_housemaster_assignment(user)

    # Base queryset
    exeats = Exeat.objects.select_related(
        'student', 'student__house', 'housemaster', 'approved_by'
    ).order_by('-created_at')

    # Filter based on role
    if is_school_admin(user):
        # Admin sees all
        pass
    elif assignment and assignment.is_senior:
        # Senior housemaster sees all
        pass
    elif assignment:
        # Regular housemaster sees only their house's students
        exeats = exeats.filter(student__house=assignment.house)
    else:
        exeats = exeats.none()

    # Apply filters
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    house_filter = request.GET.get('house', '')
    search = request.GET.get('search', '').strip()

    if status_filter:
        exeats = exeats.filter(status=status_filter)
    if type_filter:
        exeats = exeats.filter(exeat_type=type_filter)
    # House filter only for admin/senior
    if house_filter and (is_school_admin(user) or (assignment and assignment.is_senior)):
        exeats = exeats.filter(student__house_id=house_filter)
    if search:
        exeats = exeats.filter(
            Q(student__first_name__icontains=search) |
            Q(student__last_name__icontains=search) |
            Q(student__admission_number__icontains=search) |
            Q(destination__icontains=search)
        )

    # Stats - filtered by house for regular housemasters (single query with aggregate)
    today = timezone.now().date()
    stats_qs = Exeat.objects.all()
    if assignment and not assignment.is_senior and not is_school_admin(user):
        stats_qs = stats_qs.filter(student__house=assignment.house)

    # Use aggregate for single query instead of 4 separate COUNT queries
    stats = stats_qs.aggregate(
        pending=Count('id', filter=Q(status='pending')),
        recommended=Count('id', filter=Q(status='recommended')),
        active=Count('id', filter=Q(status='active')),
        overdue=Count('id', filter=Q(status='overdue')),
    )

    # Get houses for filter dropdown (admin/senior only)
    from ..models import House
    houses = House.objects.filter(is_active=True).order_by('name') if (
        is_school_admin(user) or (assignment and assignment.is_senior)
    ) else []

    # Pagination
    per_page = request.GET.get('per_page', '25')
    try:
        per_page = int(per_page)
        if per_page not in [25, 50, 100]:
            per_page = 25
    except ValueError:
        per_page = 25

    paginator = Paginator(exeats, per_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'exeats': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'per_page': per_page,
        'stats': stats,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'house_filter': house_filter,
        'search': search,
        'status_choices': Exeat.Status.choices,
        'type_choices': Exeat.ExeatType.choices,
        'houses': houses,
        'is_senior': is_senior_housemaster(user) or is_school_admin(user),
        'assignment': assignment,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Exeats'},
        ],
    }

    if request.headers.get('HX-Request'):
        return render(request, 'students/partials/exeat_content.html', context)
    return render(request, 'students/exeat_index.html', context)


@login_required
@housemaster_required
def exeat_create(request):
    """Create a new exeat request."""
    user = request.user
    assignment = get_housemaster_assignment(user)

    # Get students for selection
    if is_school_admin(user):
        students = Student.objects.filter(
            status='active',
            house__isnull=False
        ).select_related('house', 'current_class').order_by('last_name', 'first_name')
    elif assignment:
        students = Student.objects.filter(
            status='active',
            house=assignment.house
        ).select_related('house', 'current_class').order_by('last_name', 'first_name')
    else:
        students = Student.objects.none()

    selected_student = None
    if request.method == 'POST':
        form = ExeatForm(request.POST, students=students)
        if form.is_valid():
            exeat = form.save(commit=False)
            exeat.requested_by = user

            # Set housemaster from student's house
            student = exeat.student
            hm_assignment = HouseMaster.get_for_house(student.house)
            if hm_assignment:
                exeat.housemaster = hm_assignment.teacher

            # Auto-populate emergency contact from primary guardian
            guardian = student.get_primary_guardian()
            if guardian:
                exeat.contact_person = guardian.full_name
                exeat.contact_phone = guardian.phone_number or ''

            exeat.save()
            messages.success(request, f'Exeat request created for {student.full_name}.')

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Redirect'] = f'/students/exeats/{exeat.pk}/'
                return response
            return redirect('students:exeat_detail', pk=exeat.pk)
        else:
            # Preserve selected student for re-rendering the form
            student_id = request.POST.get('student')
            if student_id:
                selected_student = students.filter(pk=student_id).first()
    else:
        # Pre-select student if provided in query param
        initial = {}
        student_id = request.GET.get('student')
        if student_id:
            initial['student'] = student_id
            selected_student = students.filter(pk=student_id).first()
        form = ExeatForm(initial=initial, students=students)

    context = {
        'form': form,
        'students': students,
        'selected_student': selected_student,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Exeats', 'url': '/students/exeats/'},
            {'label': 'New Request'},
        ],
    }

    if request.headers.get('HX-Request'):
        return render(request, 'students/partials/exeat_form.html', context)
    return render(request, 'students/exeat_form.html', context)


@login_required
@housemaster_required
def exeat_student_search(request):
    """Search for students for exeat form (AJAX endpoint)."""
    user = request.user
    assignment = get_housemaster_assignment(user)
    query = request.GET.get('q', '').strip()

    students = Student.objects.none()
    if len(query) >= 2:
        # Base queryset - active students
        base_qs = Student.objects.filter(status='active')

        # Filter by house based on user role
        if is_school_admin(user):
            # Admin can search all active students (those without houses shown as disabled)
            students = base_qs
        elif assignment:
            # Housemaster can only search students in their house
            students = base_qs.filter(house=assignment.house)
        else:
            students = base_qs.filter(house__isnull=False)

        # Apply search filter
        students = students.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(admission_number__icontains=query)
        ).select_related('house', 'current_class')[:10]

    return render(request, 'students/partials/exeat_student_search_results.html', {
        'students': students
    })


@login_required
@housemaster_required
def exeat_student_guardian(request, pk):
    """Get student's guardian info for exeat form (HTMX endpoint)."""
    student = get_object_or_404(Student, pk=pk)
    guardian = student.get_primary_guardian()

    context = {
        'student': student,
        'guardian': guardian,
        'has_guardian': guardian is not None,
        'has_phone': bool(guardian.phone_number) if guardian else False,
    }
    return render(request, 'students/partials/exeat_guardian_info.html', context)


@login_required
@housemaster_required
def exeat_detail(request, pk):
    """View exeat details."""
    exeat = get_object_or_404(
        Exeat.objects.select_related(
            'student', 'student__house', 'student__current_class',
            'housemaster', 'recommended_by', 'approved_by', 'requested_by',
            'approval_sms', 'return_sms'  # Include SMS records for notification display
        ),
        pk=pk
    )

    user = request.user
    assignment = get_housemaster_assignment(user)

    # Permission check
    can_view = (
        is_school_admin(user) or
        (assignment and assignment.is_senior) or
        (assignment and exeat.student.house == assignment.house)
    )

    if not can_view:
        messages.error(request, "You don't have permission to view this exeat.")
        return redirect('students:exeat_index')

    # Determine what actions the user can take
    can_approve_internal = (
        exeat.exeat_type == 'internal' and
        exeat.status == 'pending' and
        (is_school_admin(user) or (assignment and exeat.student.house == assignment.house))
    )

    can_recommend = (
        exeat.exeat_type == 'external' and
        exeat.status == 'pending' and
        (is_school_admin(user) or (assignment and exeat.student.house == assignment.house))
    )

    can_approve_external = (
        exeat.exeat_type == 'external' and
        exeat.status == 'recommended' and
        (is_school_admin(user) or (assignment and assignment.is_senior))
    )

    is_admin_or_senior = is_school_admin(user) or (assignment and assignment.is_senior)
    is_house_housemaster = assignment and exeat.student.house == assignment.house

    can_mark_departed = (
        exeat.status == 'approved' and
        (is_admin_or_senior or is_house_housemaster)
    )
    can_mark_returned = (
        exeat.status in ['active', 'overdue'] and
        (is_admin_or_senior or is_house_housemaster)
    )
    can_reject = (
        exeat.status in ['pending', 'recommended', 'overdue'] and
        (is_admin_or_senior or is_house_housemaster)
    )

    context = {
        'exeat': exeat,
        'can_approve_internal': can_approve_internal,
        'can_recommend': can_recommend,
        'can_approve_external': can_approve_external,
        'can_mark_departed': can_mark_departed,
        'can_mark_returned': can_mark_returned,
        'can_reject': can_reject,
        'is_senior': is_senior_housemaster(user) or is_school_admin(user),
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Exeats', 'url': '/students/exeats/'},
            {'label': exeat.student.full_name},
        ],
    }

    if request.headers.get('HX-Request'):
        return render(request, 'students/partials/exeat_detail.html', context)
    return render(request, 'students/exeat_detail.html', context)


@login_required
@housemaster_required
def exeat_approve(request, pk):
    """Approve an exeat (internal) or recommend (external pending)."""
    exeat = get_object_or_404(Exeat, pk=pk)
    user = request.user
    teacher = get_teacher_profile(user)
    assignment = get_housemaster_assignment(user)

    if request.method != 'POST':
        return HttpResponse(status=405)

    # Internal exeat - direct approval by housemaster
    if exeat.exeat_type == 'internal' and exeat.status == 'pending':
        if not (is_school_admin(user) or (assignment and exeat.student.house == assignment.house)):
            messages.error(request, "You can't approve this exeat.")
            return redirect('students:exeat_detail', pk=pk)

        exeat.approve(teacher)
        messages.success(request, f'Internal exeat approved for {exeat.student.full_name}.')

        # Send SMS notification to guardian with feedback
        sms_result = send_exeat_approval_sms(exeat, user)
        if sms_result.is_success:
            messages.info(request, f"SMS sent to guardian ({sms_result.guardian_phone}).")
        elif sms_result.status == SMSResult.SMS_DISABLED:
            messages.warning(request, "SMS notifications are disabled. Guardian not notified.")
        elif sms_result.status in [SMSResult.NO_GUARDIAN, SMSResult.NO_PHONE]:
            messages.warning(request, sms_result.user_message)
        else:
            messages.error(request, f"SMS failed: {sms_result.user_message}")

    # External exeat - recommend by housemaster
    elif exeat.exeat_type == 'external' and exeat.status == 'pending':
        if not (is_school_admin(user) or (assignment and exeat.student.house == assignment.house)):
            messages.error(request, "You can't recommend this exeat.")
            return redirect('students:exeat_detail', pk=pk)

        exeat.recommend(teacher)
        messages.success(request, 'External exeat recommended for senior housemaster approval.')

    # External exeat - final approval by senior housemaster
    elif exeat.exeat_type == 'external' and exeat.status == 'recommended':
        if not (is_school_admin(user) or (assignment and assignment.is_senior)):
            messages.error(request, "Only the senior housemaster can approve external exeats.")
            return redirect('students:exeat_detail', pk=pk)

        exeat.approve(teacher)
        messages.success(request, f'External exeat approved for {exeat.student.full_name}.')

        # Send SMS notification to guardian with feedback
        sms_result = send_exeat_approval_sms(exeat, user)
        if sms_result.is_success:
            messages.info(request, f"SMS sent to guardian ({sms_result.guardian_phone}).")
        elif sms_result.status == SMSResult.SMS_DISABLED:
            messages.warning(request, "SMS notifications are disabled. Guardian not notified.")
        elif sms_result.status in [SMSResult.NO_GUARDIAN, SMSResult.NO_PHONE]:
            messages.warning(request, sms_result.user_message)
        else:
            messages.error(request, f"SMS failed: {sms_result.user_message}")

    else:
        messages.error(request, "This exeat cannot be approved in its current state.")

    if request.headers.get('HX-Request'):
        response = HttpResponse(status=204)
        response['HX-Redirect'] = f'/students/exeats/{pk}/'
        return response
    return redirect('students:exeat_detail', pk=pk)


@login_required
@housemaster_required
def exeat_reject(request, pk):
    """Reject an exeat request."""
    exeat = get_object_or_404(Exeat, pk=pk)
    user = request.user
    assignment = get_housemaster_assignment(user)

    if request.method != 'POST':
        return HttpResponse(status=405)

    if exeat.status not in ['pending', 'recommended', 'overdue']:
        messages.error(request, "This exeat cannot be rejected.")
        return redirect('students:exeat_detail', pk=pk)

    # Check permission
    can_reject = (
        is_school_admin(user) or
        (assignment and assignment.is_senior) or
        (assignment and exeat.student.house == assignment.house)
    )

    if not can_reject:
        messages.error(request, "You can't reject this exeat.")
        return redirect('students:exeat_detail', pk=pk)

    reason = request.POST.get('reason', '')
    exeat.reject(reason)
    messages.success(request, f'Exeat rejected for {exeat.student.full_name}.')

    if request.headers.get('HX-Request'):
        response = HttpResponse(status=204)
        response['HX-Redirect'] = f'/students/exeats/{pk}/'
        return response
    return redirect('students:exeat_detail', pk=pk)


@login_required
@housemaster_required
def exeat_depart(request, pk):
    """Mark student as departed."""
    exeat = get_object_or_404(Exeat, pk=pk)
    user = request.user
    assignment = get_housemaster_assignment(user)

    if request.method != 'POST':
        return HttpResponse(status=405)

    can_depart = (
        is_school_admin(user) or
        (assignment and assignment.is_senior) or
        (assignment and exeat.student.house == assignment.house)
    )
    if not can_depart:
        messages.error(request, "You don't have permission to mark this exeat as departed.")
        return redirect('students:exeat_detail', pk=pk)

    if exeat.status != 'approved':
        messages.error(request, "Only approved exeats can be marked as departed.")
        return redirect('students:exeat_detail', pk=pk)

    exeat.mark_departed()
    messages.success(request, f'{exeat.student.full_name} has departed.')

    if request.headers.get('HX-Request'):
        response = HttpResponse(status=204)
        response['HX-Redirect'] = f'/students/exeats/{pk}/'
        return response
    return redirect('students:exeat_detail', pk=pk)


@login_required
@housemaster_required
def exeat_return(request, pk):
    """Mark student as returned."""
    exeat = get_object_or_404(Exeat, pk=pk)
    user = request.user
    assignment = get_housemaster_assignment(user)

    if request.method != 'POST':
        return HttpResponse(status=405)

    can_return = (
        is_school_admin(user) or
        (assignment and assignment.is_senior) or
        (assignment and exeat.student.house == assignment.house)
    )
    if not can_return:
        messages.error(request, "You don't have permission to mark this exeat as returned.")
        return redirect('students:exeat_detail', pk=pk)

    if exeat.status not in ['active', 'overdue']:
        messages.error(request, "Only active or overdue exeats can be marked as returned.")
        return redirect('students:exeat_detail', pk=pk)

    exeat.mark_returned()
    messages.success(request, f'{exeat.student.full_name} has returned.')

    # Send SMS notification to guardian with feedback
    sms_result = send_exeat_return_sms(exeat, request.user)
    if sms_result.is_success:
        messages.info(request, f"Return notification SMS sent to guardian ({sms_result.guardian_phone}).")
    elif sms_result.status == SMSResult.SMS_DISABLED:
        messages.warning(request, "SMS notifications are disabled. Guardian not notified of return.")
    elif sms_result.status in [SMSResult.NO_GUARDIAN, SMSResult.NO_PHONE]:
        messages.warning(request, sms_result.user_message)
    else:
        messages.error(request, f"Return SMS failed: {sms_result.user_message}")

    if request.headers.get('HX-Request'):
        response = HttpResponse(status=204)
        response['HX-Redirect'] = f'/students/exeats/{pk}/'
        return response
    return redirect('students:exeat_detail', pk=pk)


# ============ HouseMaster Assignment Views ============

@login_required
@admin_required
def housemaster_index(request):
    """List housemaster assignments."""
    current_year = AcademicYear.get_current()

    assignments = HouseMaster.objects.filter(
        academic_year=current_year
    ).select_related('teacher', 'house', 'academic_year').order_by('house__name')

    context = {
        'assignments': assignments,
        'current_year': current_year,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Settings', 'url': '/settings/'},
            {'label': 'House Masters'},
        ],
    }

    if request.headers.get('HX-Request'):
        return render(request, 'students/partials/housemaster_content.html', context)
    return render(request, 'students/housemaster_index.html', context)


@login_required
@admin_required
def housemaster_assign(request):
    """Assign a teacher as housemaster."""
    if request.method == 'POST':
        form = HouseMasterForm(request.POST)
        if form.is_valid():
            assignment = form.save()
            messages.success(
                request,
                f'{assignment.teacher.full_name} assigned as housemaster for {assignment.house.name}.'
            )

            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'housemasterChanged'
                return response
            return redirect('students:housemaster_index')
    else:
        form = HouseMasterForm()

    context = {
        'form': form,
        'action': 'Assign',
    }

    if request.headers.get('HX-Request'):
        return render(request, 'students/partials/housemaster_form.html', context)
    return render(request, 'students/housemaster_form.html', context)


@login_required
@admin_required
def housemaster_remove(request, pk):
    """Remove a housemaster assignment."""
    assignment = get_object_or_404(HouseMaster, pk=pk)

    if request.method == 'POST':
        name = f"{assignment.teacher.full_name} from {assignment.house.name}"
        assignment.delete()
        messages.success(request, f'Removed {name}.')

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Trigger'] = 'housemasterChanged'
            return response
        return redirect('students:housemaster_index')

    return HttpResponse(status=405)


# ============ Exeat Reports ============

def get_exeat_report_data(start_date, end_date, house_filter=None, type_filter=None):
    """
    Get exeat data and statistics for reporting.

    Args:
        start_date: Start date for the report period
        end_date: End date for the report period
        house_filter: Optional house ID to filter by
        type_filter: Optional exeat type to filter by

    Returns:
        dict: Report data with exeats and statistics
    """
    from django.db.models import Count
    from ..models import House

    # Base queryset
    exeats = Exeat.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).select_related(
        'student', 'student__house', 'student__current_class',
        'housemaster', 'recommended_by', 'approved_by'
    ).order_by('-created_at')

    # Apply filters
    if house_filter:
        exeats = exeats.filter(student__house_id=house_filter)
    if type_filter:
        exeats = exeats.filter(exeat_type=type_filter)

    # Calculate statistics
    total = exeats.count()
    by_status = dict(exeats.values('status').annotate(count=Count('id')).values_list('status', 'count'))
    by_type = dict(exeats.values('exeat_type').annotate(count=Count('id')).values_list('exeat_type', 'count'))

    # Exeats by house
    by_house = list(
        exeats.values('student__house__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Exeats by housemaster (who approved)
    by_approver = list(
        exeats.exclude(approved_by__isnull=True)
        .values('approved_by__first_name', 'approved_by__last_name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Exeats by student (to identify frequent requesters)
    by_student = list(
        exeats.values('student__first_name', 'student__last_name', 'student__admission_number', 'student__house__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    # Calculate approval rate
    approved_count = by_status.get('approved', 0) + by_status.get('active', 0) + by_status.get('completed', 0)
    rejected_count = by_status.get('rejected', 0)
    pending_count = by_status.get('pending', 0) + by_status.get('recommended', 0)
    approval_rate = (approved_count / total * 100) if total > 0 else 0

    # Overdue exeats
    overdue_count = exeats.filter(status='overdue').count()

    # Get houses for filter dropdown
    houses = House.objects.all().order_by('name')

    return {
        'exeats': exeats,
        'total': total,
        'by_status': by_status,
        'by_type': by_type,
        'by_house': by_house,
        'by_approver': by_approver,
        'by_student': by_student,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'pending_count': pending_count,
        'approval_rate': round(approval_rate, 1),
        'overdue_count': overdue_count,
        'houses': houses,
        'start_date': start_date,
        'end_date': end_date,
    }


@login_required
@housemaster_required
def exeat_report(request):
    """Exeat report with statistics and export options."""
    from datetime import datetime

    user = request.user
    assignment = get_housemaster_assignment(user)
    is_admin_or_senior = is_school_admin(user) or (assignment and assignment.is_senior)

    # Get date range from request or default to current month
    today = timezone.now().date()
    default_start = today.replace(day=1)
    default_end = today

    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    house_filter = request.GET.get('house', '')
    type_filter = request.GET.get('type', '')

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else default_start
    except ValueError:
        start_date = default_start

    try:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else default_end
    except ValueError:
        end_date = default_end

    # Ensure valid date range
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    # For regular housemasters, force filter to their house only
    if not is_admin_or_senior and assignment:
        house_filter = str(assignment.house.pk)

    # Get report data
    report_data = get_exeat_report_data(
        start_date, end_date,
        house_filter=house_filter if house_filter else None,
        type_filter=type_filter if type_filter else None
    )

    context = {
        **report_data,
        'house_filter': house_filter,
        'type_filter': type_filter,
        'type_choices': Exeat.ExeatType.choices,
        'status_choices': Exeat.Status.choices,
        'is_admin_or_senior': is_admin_or_senior,
        'assignment': assignment,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Exeats', 'url': '/students/exeats/'},
            {'label': 'Reports'},
        ],
    }

    if request.headers.get('HX-Request'):
        return render(request, 'students/partials/exeat_report_content.html', context)
    return render(request, 'students/exeat_report.html', context)


@login_required
@housemaster_required
def exeat_report_pdf(request):
    """Export exeat report as PDF."""
    from datetime import datetime
    from io import BytesIO
    from django.template.loader import render_to_string
    from django.conf import settings as django_settings
    from weasyprint import HTML, CSS

    user = request.user
    assignment = get_housemaster_assignment(user)
    is_admin_or_senior = is_school_admin(user) or (assignment and assignment.is_senior)

    # Get date range and filters
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    house_filter = request.GET.get('house', '')
    type_filter = request.GET.get('type', '')

    # For regular housemasters, force filter to their house only
    if not is_admin_or_senior and assignment:
        house_filter = str(assignment.house.pk)

    today = timezone.now().date()
    default_start = today.replace(day=1)

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else default_start
    except ValueError:
        start_date = default_start

    try:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
    except ValueError:
        end_date = today

    # Get report data
    report_data = get_exeat_report_data(
        start_date, end_date,
        house_filter=house_filter if house_filter else None,
        type_filter=type_filter if type_filter else None
    )

    # Get school settings for header
    from core.models import SchoolSettings
    school = SchoolSettings.load()

    context = {
        **report_data,
        'school': school,
        'generated_at': timezone.now(),
        'generated_by': request.user,
    }

    # Render HTML
    html_string = render_to_string('students/reports/exeat_report_pdf.html', context)

    # Generate PDF
    html = HTML(string=html_string, base_url=str(django_settings.BASE_DIR))
    pdf_buffer = BytesIO()

    # PDF styling
    css = CSS(string='''
        @page {
            size: A4 landscape;
            margin: 1.5cm;
        }
        body {
            font-family: Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.4;
        }
        .header {
            text-align: center;
            margin-bottom: 20px;
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
        }
        .header h1 {
            margin: 0;
            font-size: 16pt;
        }
        .header p {
            margin: 5px 0;
            color: #666;
        }
        .stats-grid {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }
        .stat-box {
            background: #f5f5f5;
            padding: 10px 15px;
            border-radius: 5px;
            text-align: center;
        }
        .stat-box .number {
            font-size: 20pt;
            font-weight: bold;
            color: #333;
        }
        .stat-box .label {
            font-size: 8pt;
            color: #666;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 6px 8px;
            text-align: left;
            font-size: 9pt;
        }
        th {
            background: #f0f0f0;
            font-weight: bold;
        }
        tr:nth-child(even) {
            background: #fafafa;
        }
        .section-title {
            font-size: 12pt;
            font-weight: bold;
            margin: 20px 0 10px 0;
            color: #333;
            border-bottom: 1px solid #ccc;
            padding-bottom: 5px;
        }
        .badge {
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 8pt;
        }
        .badge-success { background: #d4edda; color: #155724; }
        .badge-warning { background: #fff3cd; color: #856404; }
        .badge-error { background: #f8d7da; color: #721c24; }
        .badge-info { background: #d1ecf1; color: #0c5460; }
        .footer {
            margin-top: 30px;
            font-size: 8pt;
            color: #666;
            text-align: center;
        }
    ''')

    html.write_pdf(pdf_buffer, stylesheets=[css])
    pdf_buffer.seek(0)

    # Generate filename
    filename = f"exeat_report_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.pdf"

    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@housemaster_required
def exeat_report_excel(request):
    """Export exeat report as Excel."""
    from datetime import datetime
    import io
    import pandas as pd
    from django.http import FileResponse

    user = request.user
    assignment = get_housemaster_assignment(user)
    is_admin_or_senior = is_school_admin(user) or (assignment and assignment.is_senior)

    # Get date range and filters
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    house_filter = request.GET.get('house', '')
    type_filter = request.GET.get('type', '')

    # For regular housemasters, force filter to their house only
    if not is_admin_or_senior and assignment:
        house_filter = str(assignment.house.pk)

    today = timezone.now().date()
    default_start = today.replace(day=1)

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else default_start
    except ValueError:
        start_date = default_start

    try:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
    except ValueError:
        end_date = today

    # Get report data
    report_data = get_exeat_report_data(
        start_date, end_date,
        house_filter=house_filter if house_filter else None,
        type_filter=type_filter if type_filter else None
    )

    # Build Excel data
    exeat_rows = []
    for exeat in report_data['exeats']:
        exeat_rows.append({
            'Date': exeat.created_at.strftime('%Y-%m-%d'),
            'Student': exeat.student.full_name,
            'Admission #': exeat.student.admission_number,
            'Class': exeat.student.current_class.name if exeat.student.current_class else '',
            'House': exeat.student.house.name if exeat.student.house else '',
            'Type': exeat.get_exeat_type_display(),
            'Destination': exeat.destination,
            'Reason': exeat.reason,
            'Departure Date': exeat.departure_date.strftime('%Y-%m-%d'),
            'Departure Time': exeat.departure_time.strftime('%H:%M'),
            'Expected Return': exeat.expected_return_date.strftime('%Y-%m-%d'),
            'Return Time': exeat.expected_return_time.strftime('%H:%M'),
            'Status': exeat.get_status_display(),
            'Recommended By': exeat.recommended_by.full_name if exeat.recommended_by else '',
            'Approved By': exeat.approved_by.full_name if exeat.approved_by else '',
            'Approved At': exeat.approved_at.strftime('%Y-%m-%d %H:%M') if exeat.approved_at else '',
            'Actual Departure': exeat.actual_departure.strftime('%Y-%m-%d %H:%M') if exeat.actual_departure else '',
            'Actual Return': exeat.actual_return.strftime('%Y-%m-%d %H:%M') if exeat.actual_return else '',
            'Guardian Notified': 'Yes' if exeat.guardian_notified_approval else 'No',
        })

    # Create summary data
    summary_rows = [
        {'Metric': 'Report Period', 'Value': f"{start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}"},
        {'Metric': 'Total Exeats', 'Value': report_data['total']},
        {'Metric': 'Internal Exeats', 'Value': report_data['by_type'].get('internal', 0)},
        {'Metric': 'External Exeats', 'Value': report_data['by_type'].get('external', 0)},
        {'Metric': 'Approved', 'Value': report_data['approved_count']},
        {'Metric': 'Rejected', 'Value': report_data['rejected_count']},
        {'Metric': 'Pending', 'Value': report_data['pending_count']},
        {'Metric': 'Approval Rate', 'Value': f"{report_data['approval_rate']}%"},
        {'Metric': 'Overdue', 'Value': report_data['overdue_count']},
    ]

    # Exeats by house
    house_rows = [{'House': h['student__house__name'] or 'No House', 'Count': h['count']} for h in report_data['by_house']]

    # Exeats by approver
    approver_rows = [
        {'Approver': f"{a['approved_by__first_name']} {a['approved_by__last_name']}", 'Count': a['count']}
        for a in report_data['by_approver']
    ]

    # Frequent students
    student_rows = [
        {
            'Student': f"{s['student__first_name']} {s['student__last_name']}",
            'Admission #': s['student__admission_number'],
            'House': s['student__house__name'] or 'No House',
            'Count': s['count']
        }
        for s in report_data['by_student']
    ]

    # Create Excel file with multiple sheets
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Summary sheet
        df_summary = pd.DataFrame(summary_rows)
        df_summary.to_excel(writer, index=False, sheet_name='Summary')

        # Exeat details sheet
        df_exeats = pd.DataFrame(exeat_rows)
        df_exeats.to_excel(writer, index=False, sheet_name='Exeat Details')

        # By house sheet
        if house_rows:
            df_house = pd.DataFrame(house_rows)
            df_house.to_excel(writer, index=False, sheet_name='By House')

        # By approver sheet
        if approver_rows:
            df_approver = pd.DataFrame(approver_rows)
            df_approver.to_excel(writer, index=False, sheet_name='By Approver')

        # Frequent students sheet
        if student_rows:
            df_students = pd.DataFrame(student_rows)
            df_students.to_excel(writer, index=False, sheet_name='Frequent Students')

        # Auto-adjust column widths for each sheet
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for column_cells in worksheet.columns:
                max_length = 0
                column = column_cells[0].column_letter
                for cell in column_cells:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except Exception:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column].width = adjusted_width

    output.seek(0)

    # Generate filename
    filename = f"exeat_report_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.xlsx"

    return FileResponse(
        output,
        as_attachment=True,
        filename=filename,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
