import logging
from datetime import datetime

from celery import shared_task
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def check_overdue_exeats(self):
    """
    Check all tenants for exeats that are past their expected return time
    and mark them as overdue. Sends SMS notification to guardians for
    newly overdue exeats.

    Recommended schedule: every 30 minutes via django-celery-beat DatabaseScheduler.
    """
    from schools.models import School

    tenants = School.objects.exclude(schema_name='public')

    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                from students.models import Exeat

                now = timezone.now()

                # Find active/approved exeats past their expected return
                overdue_exeats = []
                candidates = Exeat.objects.filter(
                    status__in=['active', 'approved'],
                ).select_related('student')

                for exeat in candidates:
                    expected = datetime.combine(
                        exeat.expected_return_date,
                        exeat.expected_return_time,
                    )
                    if timezone.is_naive(expected):
                        expected = timezone.make_aware(expected)
                    if now > expected:
                        overdue_exeats.append(exeat)

                if not overdue_exeats:
                    continue

                # Bulk update status to overdue
                overdue_ids = [e.pk for e in overdue_exeats]
                Exeat.objects.filter(pk__in=overdue_ids).update(
                    status='overdue',
                )

                logger.info(
                    f"[{tenant.schema_name}] Marked {len(overdue_ids)} exeat(s) as overdue"
                )

                # Prefetch primary guardians for all overdue students (avoid N+1)
                from students.models import StudentGuardian
                overdue_student_ids = [e.student_id for e in overdue_exeats]
                guardian_map = {}
                for sg in StudentGuardian.objects.filter(
                    student_id__in=overdue_student_ids, is_primary=True
                ).select_related('guardian'):
                    guardian_map[sg.student_id] = sg.guardian

                # Set cache on each student to prevent extra queries
                for exeat in overdue_exeats:
                    exeat.student._cached_primary_guardian = guardian_map.get(
                        exeat.student_id
                    )

                # Send SMS notifications for exeats not yet notified
                for exeat in overdue_exeats:
                    if exeat.guardian_notified_overdue:
                        continue

                    try:
                        guardian = guardian_map.get(exeat.student_id)
                        if not guardian or not guardian.phone_number:
                            continue

                        from communications.utils import send_sms

                        message = (
                            f"{tenant.name}: ALERT - {exeat.student.full_name} has not "
                            f"returned from exeat. Expected return was "
                            f"{exeat.expected_return_date.strftime('%d/%m/%Y')} "
                            f"at {exeat.expected_return_time.strftime('%H:%M')}. "
                            f"Please contact the school immediately."
                        )

                        send_sms(
                            to_phone=guardian.phone_number,
                            message=message,
                            student=exeat.student,
                            message_type='exeat',
                        )

                        Exeat.objects.filter(pk=exeat.pk).update(
                            guardian_notified_overdue=True,
                        )
                        logger.info(
                            f"[{tenant.schema_name}] Overdue SMS sent for "
                            f"{exeat.student.full_name} to {guardian.phone_number}"
                        )
                    except Exception as e:
                        logger.error(
                            f"[{tenant.schema_name}] Failed to send overdue SMS "
                            f"for exeat {exeat.pk}: {e}"
                        )

        except Exception as e:
            logger.error(
                f"[{tenant.schema_name}] Error checking overdue exeats: {e}"
            )
