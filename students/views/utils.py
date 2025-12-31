from functools import wraps
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
import pandas as pd

from core.models import AcademicYear
from students.models import Enrollment


def is_school_admin(user):
    """Check if user is a school admin or superuser."""
    return user.is_superuser or getattr(user, 'is_school_admin', False)


def admin_required(view_func):
    """Decorator to require school admin or superuser access."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not is_school_admin(request.user):
            messages.error(request, "You don't have permission to access this page.")
            return redirect('core:index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def create_enrollment_for_student(student):
    """Create an enrollment record for a student in the current academic year."""
    current_year = AcademicYear.get_current()
    if not current_year:
        return None, False

    class_to_use = student.current_class
    if not class_to_use:
        return None, False

    enrollment, created = Enrollment.objects.get_or_create(
        student=student,
        academic_year=current_year,
        defaults={
            'class_assigned': class_to_use,
            'status': Enrollment.Status.ACTIVE,
        }
    )
    return enrollment, created


def htmx_render(request, full_template, partial_template, context=None):
    """Render full template for regular requests, partial for HTMX requests."""
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)


def parse_date(value):
    """Parse date from various formats."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, 'date'):  # pandas Timestamp
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def clean_value(value):
    """Clean a cell value, handling NaN and empty strings."""
    if value is None:
        return ''
    if isinstance(value, float) and pd.isna(value):
        return ''
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()
