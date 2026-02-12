
import logging
from functools import wraps

from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from django.core.cache import cache
from django.http import JsonResponse

from academics.models import Subject, ClassSubject

logger = logging.getLogger(__name__)


def ratelimit(key='user', rate='100/h', block=True):
    """
    Simple cache-based rate limiter decorator.

    Args:
        key: 'user' for user-based, 'ip' for IP-based limiting
        rate: Format "number/period" where period is s/m/h/d (second/minute/hour/day)
        block: If True, return 429 error; if False, just log warning

    Usage:
        @ratelimit(key='user', rate='100/h')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Parse rate limit
            try:
                limit, period = rate.split('/')
                limit = int(limit)
                period_seconds = {
                    's': 1, 'm': 60, 'h': 3600, 'd': 86400
                }.get(period, 3600)
            except (ValueError, AttributeError):
                limit, period_seconds = 100, 3600  # Default: 100/hour

            # Build cache key
            if key == 'user' and request.user.is_authenticated:
                cache_key = f"ratelimit:{view_func.__name__}:user:{request.user.pk}"
            else:
                cache_key = f"ratelimit:{view_func.__name__}:ip:{get_client_ip(request)}"

            # Atomically create the key if it doesn't exist
            if cache.add(cache_key, 1, period_seconds):
                # Key was newly created with value 1, proceed
                pass
            else:
                # Key exists, atomically increment
                try:
                    current = cache.incr(cache_key)
                except ValueError:
                    # Key expired between add and incr, recreate
                    cache.set(cache_key, 1, period_seconds)
                    current = 1

                if current > limit:
                    logger.warning(f"Rate limit exceeded for {cache_key}")
                    if block:
                        return JsonResponse(
                            {'error': 'Too many requests. Please try again later.'},
                            status=429
                        )

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


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
