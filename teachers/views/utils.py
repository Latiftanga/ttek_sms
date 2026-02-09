from functools import wraps
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
import pandas as pd


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


def htmx_render(request, full_template, partial_template, context=None):
    """Render full template for regular requests, partial for HTMX requests."""
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)


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
