import base64
import logging
from functools import wraps
from io import BytesIO

from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpResponse

logger = logging.getLogger(__name__)


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
    from django.db.models import Q
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
