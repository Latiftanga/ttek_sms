"""Base utilities, decorators, and helper functions for academics views."""
from functools import wraps
from django.shortcuts import render, redirect
from django.contrib import messages


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


def is_teacher_or_admin(user):
    """Check if user is a teacher, school admin, or superuser."""
    return (user.is_superuser or
            getattr(user, 'is_school_admin', False) or
            getattr(user, 'is_teacher', False))


def teacher_or_admin_required(view_func):
    """Decorator to require teacher or admin access."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not is_teacher_or_admin(request.user):
            messages.error(request, "You don't have permission to access this page.")
            return redirect('core:index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def htmx_render(request, full_template, partial_template, context=None):
    """Render full template for regular requests, partial for HTMX requests."""
    context = context or {}
    is_htmx = bool(request.htmx)
    template = partial_template if is_htmx else full_template
    return render(request, template, context)
