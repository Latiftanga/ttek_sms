from functools import wraps
from datetime import datetime

from django.shortcuts import redirect
from django.contrib import messages
import pandas as pd

from core.utils import (  # noqa: F401
    is_school_admin, admin_required, htmx_render,
)


def admin_or_owner(view_func):
    """Allow school admin OR the teacher accessing their own data (pk match)."""
    @wraps(view_func)
    def _wrapped_view(request, pk, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if is_school_admin(request.user):
            return view_func(request, pk, *args, **kwargs)
        if (getattr(request.user, 'is_teacher', False)
                and hasattr(request.user, 'teacher_profile')
                and str(request.user.teacher_profile.pk) == str(pk)):
            return view_func(request, pk, *args, **kwargs)
        messages.error(request, "You don't have permission to access this page.")
        return redirect('core:index')
    return _wrapped_view


def clean_value(value):
    """Clean a cell value, handling NaN and empty strings."""
    if value is None:
        return ''
    if isinstance(value, float) and pd.isna(value):
        return ''
    return str(value).strip()


def parse_date(value):
    """Try to parse date from common formats."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, 'date'):  # pandas Timestamp
        return value.date()

    val_str = str(value).strip()
    if not val_str:
        return None

    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']:
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            continue
    return None
