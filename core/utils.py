import base64
import logging
from functools import wraps
from io import BytesIO

from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.core.cache import cache

logger = logging.getLogger(__name__)


# =============================================================================
# Rate Limiting
# =============================================================================

def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def ratelimit(key='user', rate='10/h', block=True):
    """
    Simple cache-based rate limiter decorator.

    Args:
        key: 'user' for user-based, 'ip' for IP-based limiting
        rate: Format "number/period" where period is s/m/h/d (second/minute/hour/day)
        block: If True, return 429 error; if False, just log warning

    Usage:
        @ratelimit(key='user', rate='10/h')
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
                limit, period_seconds = 10, 3600  # Default: 10/hour

            # Build cache key
            if key == 'user' and request.user.is_authenticated:
                cache_key = f"ratelimit:{view_func.__name__}:user:{request.user.pk}"
            else:
                cache_key = f"ratelimit:{view_func.__name__}:ip:{get_client_ip(request)}"

            # Check current count
            current = cache.get(cache_key, 0)

            if current >= limit:
                logger.warning(f"Rate limit exceeded for {cache_key}")
                if block:
                    # Return HTML for HTMX requests, JSON for API requests
                    if request.headers.get('HX-Request'):
                        return HttpResponse(
                            '<div class="alert alert-error text-sm py-2">'
                            '<i class="fa-solid fa-circle-xmark"></i> Too many requests. Please try again later.'
                            '</div>',
                            status=429
                        )
                    return JsonResponse(
                        {'error': 'Too many requests. Please try again later.'},
                        status=429
                    )

            # Increment counter
            cache.set(cache_key, current + 1, period_seconds)

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def cache_page_per_tenant(timeout=300):
    """
    Tenant-aware page caching decorator for multi-tenant Django apps.

    Caches the response per tenant schema to avoid cross-tenant data leakage.
    Works with HTMX by caching partial and full responses separately.

    Args:
        timeout: Cache timeout in seconds (default 5 minutes)

    Usage:
        @cache_page_per_tenant(timeout=300)
        def my_dashboard(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from django.db import connection

            # Build tenant-aware cache key
            schema = getattr(connection, 'schema_name', 'public')
            is_htmx = request.headers.get('HX-Request', '')
            path = request.get_full_path()

            cache_key = f"page:{schema}:{view_func.__name__}:{path}:htmx={is_htmx}"

            # Try to get cached response
            cached = cache.get(cache_key)
            if cached is not None:
                return HttpResponse(
                    cached['content'],
                    content_type=cached.get('content_type', 'text/html'),
                    status=cached.get('status', 200)
                )

            # Generate response
            response = view_func(request, *args, **kwargs)

            # Only cache successful GET responses
            if request.method == 'GET' and response.status_code == 200:
                # Don't cache responses with Set-Cookie
                if not response.cookies:
                    cache.set(cache_key, {
                        'content': response.content,
                        'content_type': response.get('Content-Type', 'text/html'),
                        'status': response.status_code,
                    }, timeout)

            return response
        return wrapper
    return decorator


# =============================================================================
# Education System Feature Gating
# =============================================================================

def get_current_tenant():
    """Get the current tenant (School) based on database connection schema."""
    from django.db import connection
    from schools.models import School
    try:
        return School.objects.get(schema_name=connection.schema_name)
    except School.DoesNotExist:
        return None


def requires_feature(feature_name, error_message=None):
    """
    Decorator to require a specific tenant feature for a view.

    Args:
        feature_name: Tenant property to check (e.g., 'has_programmes', 'has_houses', 'has_shs_levels')
        error_message: Custom error message

    Usage:
        @requires_feature('has_programmes')
        def programme_create(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from django.contrib import messages as django_messages

            tenant = get_current_tenant()
            if tenant and not getattr(tenant, feature_name, False):
                msg = error_message or "This feature is not available for your school's education system."

                # Handle HTMX requests
                if request.headers.get('HX-Request'):
                    return HttpResponse(
                        f'<div class="alert alert-warning"><i class="fa-solid fa-triangle-exclamation"></i> {msg}</div>',
                        status=403
                    )

                django_messages.warning(request, msg)
                return redirect('core:index')

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def requires_shs(view_func):
    """Decorator to require SHS education system."""
    return requires_feature('has_shs_levels', 'This feature is only available for SHS schools.')(view_func)


def requires_programmes(view_func):
    """Decorator to require programmes support (SHS or Both)."""
    return requires_feature('has_programmes', 'Programmes are only available for SHS schools.')(view_func)


def requires_houses(view_func):
    """Decorator to require houses support (SHS or Both)."""
    return requires_feature('has_houses', 'Houses are only available for SHS schools.')(view_func)


# =============================================================================
# Teacher Utility Functions and Decorators
# =============================================================================

def get_teacher_or_none(user):
    """
    Get the teacher profile from a user, or None if not a teacher.

    Returns:
        Teacher instance or None
    """
    if not getattr(user, 'is_teacher', False):
        return None
    return getattr(user, 'teacher_profile', None)


def teacher_required(view_func=None, *, htmx_error=False, error_message=None):
    """
    Decorator to require teacher access for a view.

    Args:
        htmx_error: If True, returns HTML error for HTMX requests instead of redirect
        error_message: Custom error message (default: "You do not have permission to access this page.")

    Usage:
        @teacher_required
        def my_view(request):
            teacher = request.teacher  # Teacher profile added to request
            ...

        @teacher_required(htmx_error=True)
        def htmx_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if htmx_error:
                    return HttpResponse('<div class="alert alert-error">Please login to continue.</div>', status=401)
                return redirect('accounts:login')

            teacher = get_teacher_or_none(request.user)
            if teacher is None:
                msg = error_message or "You do not have permission to access this page."
                if htmx_error:
                    return HttpResponse(f'<div class="alert alert-error">{msg}</div>', status=403)
                messages.error(request, msg)
                return redirect('core:index')

            # Add teacher to request for convenience
            request.teacher = teacher
            return view_func(request, *args, **kwargs)
        return _wrapped_view

    if view_func is not None:
        return decorator(view_func)
    return decorator


def get_teacher_classes(teacher, include_homeroom=True, include_assigned=True, active_only=True):
    """
    Get all classes a teacher has access to.

    Args:
        teacher: Teacher instance
        include_homeroom: Include classes where teacher is class teacher
        include_assigned: Include classes where teacher teaches a subject
        active_only: Only return active classes

    Returns:
        QuerySet of Class objects
    """
    from academics.models import Class, ClassSubject

    class_ids = set()

    if include_homeroom:
        homeroom_qs = Class.objects.filter(class_teacher=teacher)
        if active_only:
            homeroom_qs = homeroom_qs.filter(is_active=True)
        class_ids.update(homeroom_qs.values_list('id', flat=True))

    if include_assigned:
        assigned_ids = ClassSubject.objects.filter(teacher=teacher).values_list('class_assigned_id', flat=True)
        class_ids.update(assigned_ids)

    qs = Class.objects.filter(id__in=class_ids)
    if active_only:
        qs = qs.filter(is_active=True)

    return qs.order_by('level_number', 'name')


def teacher_has_class_access(teacher, class_obj):
    """
    Check if a teacher has access to a specific class.

    Returns:
        bool: True if teacher is homeroom teacher or teaches a subject in this class
    """
    from academics.models import ClassSubject

    # Check if homeroom teacher
    if class_obj.class_teacher_id == teacher.id:
        return True

    # Check if teaches any subject in this class
    return ClassSubject.objects.filter(
        teacher=teacher,
        class_assigned=class_obj
    ).exists()


def teacher_has_subject_access(teacher, class_obj, subject):
    """
    Check if a teacher has access to a specific class-subject combination.

    Returns:
        bool: True if teacher is assigned to teach this subject in this class
    """
    from academics.models import ClassSubject

    return ClassSubject.objects.filter(
        teacher=teacher,
        class_assigned=class_obj,
        subject=subject
    ).exists()


def generate_qr_code_base64(data, box_size=10, border=2):
    """
    Generate a QR code and return it as a base64 data URI.

    Args:
        data: The data to encode in the QR code (usually a URL)
        box_size: Size of each box in pixels (default 10)
        border: Border size in boxes (default 2)

    Returns:
        str: Base64 data URI string for embedding in HTML/PDF, or None if failed
    """
    try:
        import qrcode

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)

        # Create image using default PIL/Pillow backend
        img = qr.make_image(fill_color="black", back_color="white")

        # Save to buffer as PNG
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        # Encode as base64
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{img_base64}"

    except ImportError as e:
        logger.warning(f"qrcode or PIL package not installed: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        return None


def generate_verification_qr(verification_code, request=None, domain=None):
    """
    Generate a QR code for document verification.

    Args:
        verification_code: The verification code to encode
        request: Django request object (optional, used to build absolute URL)
        domain: Domain string like "school.example.com" (optional, used when request not available)

    Returns:
        str: Base64 data URI string, or None if failed
    """
    from django.conf import settings

    # Build the verification URL
    verify_path = f"/verify/{verification_code}/"

    if request:
        # Build absolute URL from request
        verification_url = request.build_absolute_uri(verify_path)
    elif domain:
        # Build URL from provided domain
        scheme = 'https'  # Default to https for security
        verification_url = f"{scheme}://{domain}{verify_path}"
    else:
        # Try to get base URL from settings
        base_url = getattr(settings, 'VERIFICATION_BASE_URL', None)
        if base_url:
            verification_url = f"{base_url.rstrip('/')}{verify_path}"
        else:
            # Fall back to relative path (won't be recognized as link by phone cameras)
            verification_url = verify_path

    return generate_qr_code_base64(verification_url, box_size=6, border=1)
