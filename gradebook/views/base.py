
import logging
from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from academics.models import Class, Subject, ClassSubject
from students.models import Student

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def is_school_admin(user):
    """Check if user is a school admin or superuser."""
    return user.is_superuser or getattr(user, 'is_school_admin', False)


def is_teacher_or_admin(user):
    """Check if user is a teacher, school admin, or superuser."""
    return (user.is_superuser or
            getattr(user, 'is_school_admin', False) or
            getattr(user, 'is_teacher', False))


def admin_required(view_func):
    """Decorator to require school admin or superuser."""
    return user_passes_test(is_school_admin, login_url='/')(view_func)


def teacher_or_admin_required(view_func):
    """Decorator to require teacher, school admin, or superuser."""
    return user_passes_test(is_teacher_or_admin, login_url='/')(view_func)


def can_edit_scores(user, class_obj, subject):
    """
    Check if a user can edit scores for a specific class/subject.

    Returns True if:
    - User is superuser or school admin
    - User is the teacher assigned to this subject for this class
    """
    # Admins can always edit
    if user.is_superuser or getattr(user, 'is_school_admin', False):
        return True

    # Check if user has a teacher profile
    if not hasattr(user, 'teacher_profile') or not user.teacher_profile:
        return False

    teacher = user.teacher_profile

    # Check if this teacher is assigned to teach this subject to this class
    return ClassSubject.objects.filter(
        class_assigned=class_obj,
        subject=subject,
        teacher=teacher
    ).exists()


def get_teacher_subjects(user, class_obj):
    """
    Get subjects a teacher can edit for a specific class.

    Returns all subjects if admin, otherwise only assigned subjects.
    """
    if user.is_superuser or getattr(user, 'is_school_admin', False):
        # Admins see all subjects for the class
        return Subject.objects.filter(
            class_allocations__class_assigned=class_obj
        ).distinct()

    # Teachers only see their assigned subjects
    if not hasattr(user, 'teacher_profile') or not user.teacher_profile:
        return Subject.objects.none()

    return Subject.objects.filter(
        class_allocations__class_assigned=class_obj,
        class_allocations__teacher=user.teacher_profile
    ).distinct()


def htmx_render(request, full_template, partial_template, context=None):
    """Render full template for regular requests, partial for HTMX requests."""
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)
