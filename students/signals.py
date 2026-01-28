"""Signals for the students app."""
import logging
from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_delete, sender='students.StudentGuardian')
def reassign_primary_guardian(sender, instance, **kwargs):
    """
    When a StudentGuardian is deleted, if it was the primary guardian,
    reassign primary status to another guardian for that student.
    """
    if not instance.is_primary:
        return

    # Find another guardian for this student and make them primary
    from students.models import StudentGuardian
    next_guardian = StudentGuardian.objects.filter(
        student_id=instance.student_id
    ).first()

    if next_guardian:
        next_guardian.is_primary = True
        next_guardian.save(update_fields=['is_primary'])
        logger.info(
            f"Reassigned primary guardian for student {instance.student_id} "
            f"to {next_guardian.guardian.full_name}"
        )
