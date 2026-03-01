"""
Notification helpers for sending bell notifications to parents and students.
"""
import logging

from django.db import connection

from .models import Notification

logger = logging.getLogger(__name__)


def notify_guardian(student, title, message, category='system',
                    notification_type='info', icon='', link=''):
    """
    Send a bell notification to a student's primary guardian (if they have a user account).
    """
    from students.models import StudentGuardian

    sg = StudentGuardian.objects.filter(
        student=student, is_primary=True
    ).select_related('guardian__user').first()

    if not sg or not sg.guardian.user_id:
        return None

    return Notification.create_notification(
        user=sg.guardian.user,
        title=title,
        message=message,
        notification_type=notification_type,
        category=category,
        icon=icon,
        link=link,
    )


def notify_student(student, title, message, category='system',
                    notification_type='info', icon='', link=''):
    """
    Send a bell notification to a student (if they have a user account).
    """
    if not student.user_id:
        return None

    return Notification.create_notification(
        user=student.user,
        title=title,
        message=message,
        notification_type=notification_type,
        category=category,
        icon=icon,
        link=link,
    )


def notify_guardians_bulk(students, title, message, category='system',
                           notification_type='info', icon='', link=''):
    """
    Send bell notifications to primary guardians of multiple students in bulk.
    Only notifies guardians who have user accounts.
    """
    from django.core.cache import cache
    from students.models import StudentGuardian

    student_ids = [s.id for s in students]
    sg_qs = StudentGuardian.objects.filter(
        student_id__in=student_ids,
        is_primary=True,
        guardian__user__isnull=False,
    ).select_related('guardian__user')

    # Deduplicate by guardian user (a guardian may have multiple children)
    seen_user_ids = set()
    notifications = []
    for sg in sg_qs:
        user = sg.guardian.user
        if user.pk in seen_user_ids:
            continue
        seen_user_ids.add(user.pk)
        notifications.append(Notification(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            category=category,
            icon=icon,
            link=link,
        ))

    if not notifications:
        return []

    result = Notification.objects.bulk_create(notifications)

    # Invalidate caches
    for user_id in seen_user_ids:
        cache_key = f'notif_unread_{connection.schema_name}_{user_id}'
        cache.delete(cache_key)

    return result


def notify_students_bulk(students, title, message, category='system',
                          notification_type='info', icon='', link=''):
    """
    Send bell notifications to multiple students in bulk.
    Only notifies students who have user accounts.
    """
    from django.core.cache import cache

    notifications = []
    user_ids = []
    for student in students:
        if student.user_id:
            user_ids.append(student.user_id)
            notifications.append(Notification(
                user_id=student.user_id,
                title=title,
                message=message,
                notification_type=notification_type,
                category=category,
                icon=icon,
                link=link,
            ))

    if not notifications:
        return []

    result = Notification.objects.bulk_create(notifications)

    for user_id in user_ids:
        cache_key = f'notif_unread_{connection.schema_name}_{user_id}'
        cache.delete(cache_key)

    return result
