import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)

# Configurable thresholds
CONSECUTIVE_ABSENCE_THRESHOLD = 3
DEFAULT_SMS_TEMPLATE = (
    "Dear Parent, {student_name} has been absent from {school_name} "
    "for {days} consecutive day(s) ({dates}). "
    "Please contact the school if your child is unwell. Thank you."
)


@shared_task(bind=True)
def notify_consecutive_absences(self):
    """
    Check all tenants for students with consecutive absences
    and send SMS to their guardians.

    Recommended schedule: daily at end of school day via django-celery-beat.
    Only sends one notification per student per absence streak
    (tracks last notified date to avoid duplicates).
    """
    from schools.models import School

    tenants = School.objects.exclude(schema_name='public')
    total_notified = 0

    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                notified = _process_tenant_absences(tenant)
                total_notified += notified
        except Exception as e:
            logger.error(
                f"Error checking absences for {tenant.schema_name}: {e}"
            )

    logger.info(f"Consecutive absence check complete: {total_notified} notifications sent")
    return {'total_notified': total_notified}


def _process_tenant_absences(tenant):
    """Process absence notifications for a single tenant."""
    from academics.models import AttendanceSession, AttendanceRecord
    from students.models import Student
    from communications.utils import send_sms
    from core.models import SchoolSettings

    today = timezone.localdate()
    notified = 0

    # Get school-specific SMS template or use default
    settings = SchoolSettings.load()
    sms_template = settings.absence_sms_template or DEFAULT_SMS_TEMPLATE

    # Get recent school days (last 10 calendar days to cover weekends)
    recent_sessions = AttendanceSession.objects.filter(
        date__gte=today - timedelta(days=14),
        date__lte=today,
        session_type='Daily',
    ).values_list('date', flat=True).distinct().order_by('-date')

    school_days = list(recent_sessions)
    if len(school_days) < CONSECUTIVE_ABSENCE_THRESHOLD:
        return 0

    # Only check the most recent N school days
    check_days = school_days[:CONSECUTIVE_ABSENCE_THRESHOLD]

    # Find students absent on ALL of the last N school days using a single query
    # instead of iterating per student (N+1 fix)
    from django.db.models import Count as DjCount

    absent_students = (
        AttendanceRecord.objects.filter(
            session__date__in=check_days,
            status='A',
            student__status='active',
            student__current_class__isnull=False,
        )
        .values('student_id')
        .annotate(absent_days_count=DjCount('session__date', distinct=True))
        .filter(absent_days_count__gte=CONSECUTIVE_ABSENCE_THRESHOLD)
    )

    absent_student_ids = [r['student_id'] for r in absent_students]
    if not absent_student_ids:
        return 0

    active_students = Student.objects.filter(
        pk__in=absent_student_ids,
    ).select_related('current_class')

    # Get absent dates per student in bulk
    absent_records = AttendanceRecord.objects.filter(
        student_id__in=absent_student_ids,
        session__date__in=check_days,
        status='A',
    ).values_list('student_id', 'session__date')

    from collections import defaultdict
    absent_dates_by_student = defaultdict(set)
    for sid, d in absent_records:
        absent_dates_by_student[sid].add(d)

    for student in active_students:
        student_absent_dates = absent_dates_by_student.get(student.id, set())
        absent_count = len(student_absent_dates)
        if absent_count < CONSECUTIVE_ABSENCE_THRESHOLD:
            continue

        # Skip if already notified for this streak (check most recent absence date)
        latest_absent = max(student_absent_dates)
        cache_key = f'absence_notified_{student.id}'
        from django.core.cache import cache
        last_notified_date = cache.get(cache_key)
        if last_notified_date and last_notified_date >= latest_absent:
            continue

        # Get guardian and notification preference
        guardian = student.get_primary_guardian() if hasattr(student, 'get_primary_guardian') else None
        phone = getattr(student, 'guardian_phone', None) or getattr(student, 'parent_phone', None)
        if not phone:
            continue

        pref = getattr(guardian, 'notification_preference', 'sms') if guardian else 'sms'
        if pref == 'none':
            continue

        # Format dates for the SMS
        sorted_dates = sorted(student_absent_dates)
        dates_str = ', '.join(d.strftime('%d/%m') for d in sorted_dates)

        message = sms_template.format(
            student_name=student.first_name,
            school_name=tenant.name,
            days=absent_count,
            dates=dates_str,
        )

        try:
            if pref in ('sms', 'both'):
                send_sms(phone, message)
            if pref in ('email', 'both') and guardian and guardian.email:
                from django.core.mail import send_mail
                send_mail(
                    subject=f"Absence Alert - {student.first_name}",
                    message=message,
                    from_email=None,
                    recipient_list=[guardian.email],
                    fail_silently=True,
                )
            notified += 1
            # Track notification to prevent duplicates (expire after 7 days)
            cache.set(cache_key, latest_absent, timeout=7 * 24 * 3600)
            logger.info(
                f"Absence alert sent for {student.full_name} "
                f"({absent_count} days) via {pref}"
            )
        except Exception as e:
            logger.error(
                f"Failed to send absence alert for {student.full_name}: {e}"
            )

    return notified
