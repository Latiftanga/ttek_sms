
import json
import logging

from django.contrib import messages
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect

from academics.models import Subject, ClassSubject
from core.utils import (  # noqa: F401
    is_school_admin, is_teacher_or_admin, admin_required,
    teacher_or_admin_required, htmx_render, get_client_ip,
)

logger = logging.getLogger(__name__)


def toast_redirect(request, message, redirect_view, *redirect_args, toast_type='error', **redirect_kwargs):
    """
    Redirect after blocking an action (permission denied, no data, etc.),
    showing `message` via a toast for HTMX requests.

    Several gradebook redirect targets (reports.html, bulk_remarks, etc.)
    don't render Django's messages framework output, so a plain
    messages.error() + redirect() is invisible for the HTMX flows that are
    how these views are actually reached. Mirrors the same fix already
    applied in academics/students this session.
    """
    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': message, 'type': toast_type}
        })
        return response
    messages.error(request, message) if toast_type == 'error' else messages.info(request, message)
    return redirect(redirect_view, *redirect_args, **redirect_kwargs)


def ratelimit(key='user', rate='100/h', block=True):
    """
    Simple cache-based rate limiter decorator for gradebook.

    Uses atomic cache operations for accuracy under concurrency.
    """
    from functools import wraps

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
            schema = getattr(connection, 'schema_name', 'public')
            if key == 'user' and request.user.is_authenticated:
                cache_key = f"ratelimit:{schema}:{view_func.__name__}:user:{request.user.pk}"
            else:
                cache_key = f"ratelimit:{schema}:{view_func.__name__}:ip:{get_client_ip(request)}"

            # Atomically create the key if it doesn't exist
            if cache.add(cache_key, 1, period_seconds):
                pass
            else:
                try:
                    current = cache.incr(cache_key)
                except ValueError:
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


def can_edit_scores(user, class_obj, subject):
    """
    Check if a user can edit scores for a specific class/subject.

    Returns True if:
    - User is superuser or school admin
    - User is the teacher assigned to this subject for this class

    Result is cached on the user object for the lifetime of the request to
    avoid repeated DB hits when called multiple times per HTMX score-save.
    """
    if user.is_superuser or getattr(user, 'is_school_admin', False):
        return True

    if not hasattr(user, 'teacher_profile') or not user.teacher_profile:
        return False

    cache_key = (
        class_obj.pk if class_obj else None,
        subject.pk if subject else None,
    )
    if not hasattr(user, '_can_edit_scores_cache'):
        user._can_edit_scores_cache = {}
    if cache_key not in user._can_edit_scores_cache:
        user._can_edit_scores_cache[cache_key] = ClassSubject.objects.filter(
            class_assigned=class_obj,
            subject=subject,
            teacher=user.teacher_profile
        ).exists()
    return user._can_edit_scores_cache[cache_key]


def get_teacher_subjects(user, class_obj):
    """
    Get subjects a teacher can edit for a specific class.

    Returns all subjects if admin, otherwise only assigned subjects.
    """
    if user.is_superuser or getattr(user, 'is_school_admin', False):
        return Subject.objects.filter(
            class_allocations__class_assigned=class_obj
        ).distinct()

    if not hasattr(user, 'teacher_profile') or not user.teacher_profile:
        return Subject.objects.none()

    return Subject.objects.filter(
        class_allocations__class_assigned=class_obj,
        class_allocations__teacher=user.teacher_profile
    ).distinct()
