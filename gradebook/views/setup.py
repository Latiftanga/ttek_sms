from decimal import Decimal, InvalidOperation
from django.db import connection, models
from django.db.models import Count
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse

from .base import admin_required, htmx_render
from ..models import (
    GradingSystem, GradeScale, AssessmentCategory
)
from core.models import SchoolSettings


def _get_school_levels():
    """Return SCHOOL_LEVELS filtered by the current tenant's education system."""
    tenant = connection.tenant
    education_system = getattr(tenant, 'education_system', 'both')
    if education_system == 'basic':
        return [lvl for lvl in GradingSystem.SCHOOL_LEVELS if lvl[0] == 'BASIC']
    elif education_system == 'shs':
        return [lvl for lvl in GradingSystem.SCHOOL_LEVELS if lvl[0] == 'SHS']
    return GradingSystem.SCHOOL_LEVELS


def _safe_int(value, default=0):
    """Safely convert a value to int, returning default on failure."""
    try:
        return int(value or default)
    except (ValueError, TypeError):
        return default

@login_required
@admin_required
def gradebook_settings(request):
    """Gradebook settings - grading systems and categories (Admin only)."""
    grading_systems = GradingSystem.objects.prefetch_related('scales')
    categories = AssessmentCategory.objects.annotate(
        assignment_count=Count('assignments')
    ).order_by('order')

    # Check if percentages sum to 100
    total_percentage = sum(c.percentage for c in categories if c.is_active)

    school_settings = SchoolSettings.load()

    context = {
        'grading_systems': grading_systems,
        'categories': categories,
        'total_percentage': total_percentage,
        'school_settings': school_settings,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook', 'url': '/gradebook/'},
            {'label': 'Settings'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/settings.html',
        'gradebook/partials/settings_content.html',
        context
    )


# ============ Report Card Configuration ============

@login_required
@admin_required
def report_card_config_update(request):
    """Update report card configuration."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    school_settings = SchoolSettings.load()

    school_settings.rc_title = request.POST.get('rc_title', 'Terminal Report Card').strip()
    school_settings.rc_display_name = request.POST.get('rc_display_name', '').strip()
    school_settings.rc_show_student_photo = 'rc_show_student_photo' in request.POST
    school_settings.rc_show_class_teacher = 'rc_show_class_teacher' in request.POST
    school_settings.rc_show_position = 'rc_show_position' in request.POST
    school_settings.rc_show_aggregate = 'rc_show_aggregate' in request.POST
    school_settings.rc_show_attendance = 'rc_show_attendance' in request.POST
    school_settings.rc_show_conduct = 'rc_show_conduct' in request.POST
    school_settings.rc_show_promotion = 'rc_show_promotion' in request.POST
    school_settings.rc_show_grading_key = 'rc_show_grading_key' in request.POST
    school_settings.rc_show_qr_code = 'rc_show_qr_code' in request.POST
    school_settings.save()

    context = {'school_settings': school_settings, 'rc_success': True}
    return render(request, 'gradebook/partials/card_report.html', context)


@login_required
@admin_required
def grade_alert_config_update(request):
    """Update grade drop alert configuration."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    school_settings = SchoolSettings.load()
    school_settings.grade_alert_enabled = 'grade_alert_enabled' in request.POST
    try:
        threshold = int(request.POST.get('grade_alert_threshold', 50))
        threshold = max(0, min(100, threshold))
    except (ValueError, TypeError):
        threshold = 50
    school_settings.grade_alert_threshold = threshold
    school_settings.grade_alert_sms_template = request.POST.get('grade_alert_sms_template', '').strip()
    school_settings.save()

    # Re-render the full settings page with all required context
    grading_systems_qs = GradingSystem.objects.prefetch_related('scales')
    categories = AssessmentCategory.objects.annotate(
        assignment_count=Count('assignments')
    ).order_by('order')
    total_percentage = sum(c.percentage for c in categories if c.is_active)

    return htmx_render(
        request,
        'gradebook/settings.html',
        'gradebook/partials/settings_content.html',
        {
            'school_settings': school_settings,
            'grading_systems': grading_systems_qs,
            'categories': categories,
            'total_percentage': total_percentage,
        },
    )


@login_required
@admin_required
def distribution_config_update(request):
    """Update report distribution configuration."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    from django.utils.dateparse import parse_datetime

    school_settings = SchoolSettings.load()
    school_settings.auto_distribute_on_lock = 'auto_distribute_on_lock' in request.POST

    scheduled_str = request.POST.get('scheduled_report_date', '').strip()
    school_settings.scheduled_report_date = parse_datetime(scheduled_str) if scheduled_str else None
    school_settings.save()

    grading_systems_qs = GradingSystem.objects.prefetch_related('scales')
    categories = AssessmentCategory.objects.annotate(
        assignment_count=Count('assignments')
    ).order_by('order')
    total_percentage = sum(c.percentage for c in categories if c.is_active)

    return htmx_render(
        request,
        'gradebook/settings.html',
        'gradebook/partials/settings_content.html',
        {
            'school_settings': school_settings,
            'grading_systems': grading_systems_qs,
            'categories': categories,
            'total_percentage': total_percentage,
        },
    )


# ============ Grading System CRUD ============

@login_required
@admin_required
def grading_systems(request):
    """List all grading systems (Admin only)."""
    systems = GradingSystem.objects.prefetch_related('scales')
    return render(request, 'gradebook/partials/grading_systems_list.html', {
        'grading_systems': systems,
    })


@login_required
@admin_required
def grading_system_create(request):
    """Create a new grading system (Admin only)."""
    if request.method == 'GET':
        return render(request, 'gradebook/includes/modal_grading_system.html', {
            'levels': _get_school_levels(),
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    name = request.POST.get('name', '').strip()
    level = request.POST.get('level', 'BASIC')
    description = request.POST.get('description', '').strip()

    if not name:
        return render(request, 'gradebook/includes/modal_grading_system.html', {
            'error': 'Name is required.',
            'levels': _get_school_levels(),
        })

    GradingSystem.objects.create(
        name=name,
        level=level,
        description=description,
    )

    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'closeModal, refreshSettings'
    return response


@login_required
@admin_required
def grading_system_edit(request, pk):
    """Edit a grading system (Admin only)."""
    system = get_object_or_404(GradingSystem, pk=pk)

    if request.method == 'GET':
        return render(request, 'gradebook/includes/modal_grading_system.html', {
            'system': system,
            'levels': _get_school_levels(),
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    system.name = request.POST.get('name', '').strip()
    system.level = request.POST.get('level', 'BASIC')
    system.description = request.POST.get('description', '').strip()
    system.is_active = request.POST.get('is_active') == 'on'
    system.save()

    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'closeModal, refreshSettings'
    return response


@login_required
@admin_required
def grading_system_delete(request, pk):
    """Delete a grading system (Admin only)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    system = get_object_or_404(GradingSystem, pk=pk)
    system.delete()

    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'refreshSettings'
    return response


# ============ Grade Scale CRUD ============

@login_required
@admin_required
def grade_scales(request, system_id):
    """List grades for a grading system (Admin only)."""
    system = get_object_or_404(GradingSystem, pk=system_id)
    scales = system.scales.all()

    return render(request, 'gradebook/partials/grade_scales_list.html', {
        'system': system,
        'scales': scales,
    })


@login_required
@admin_required
def grade_scale_create(request, system_id):
    """Create a new grade scale (Admin only)."""
    system = get_object_or_404(GradingSystem, pk=system_id)

    if request.method == 'GET':
        return render(request, 'gradebook/includes/modal_grade_scale.html', {
            'system': system,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        GradeScale.objects.create(
            grading_system=system,
            grade_label=request.POST.get('grade_label', '').strip(),
            min_percentage=Decimal(request.POST.get('min_percentage', '0')),
            max_percentage=Decimal(request.POST.get('max_percentage', '0')),
            aggregate_points=int(request.POST.get('aggregate_points') or 0) or None,
            interpretation=request.POST.get('interpretation', '').strip(),
            is_pass=bool(request.POST.get('is_pass')),
            is_credit=bool(request.POST.get('is_credit')),
            order=int(request.POST.get('order') or 0),
        )
    except (ValueError, InvalidOperation, ValidationError) as e:
        return render(request, 'gradebook/includes/modal_grade_scale.html', {
            'system': system,
            'error': str(e),
        })

    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'closeModal, refreshSettings'
    return response


@login_required
@admin_required
def grade_scale_edit(request, pk):
    """Edit a grade scale (Admin only)."""
    scale = get_object_or_404(GradeScale, pk=pk)

    if request.method == 'GET':
        return render(request, 'gradebook/includes/modal_grade_scale.html', {
            'system': scale.grading_system,
            'scale': scale,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        scale.grade_label = request.POST.get('grade_label', '').strip()
        scale.min_percentage = Decimal(request.POST.get('min_percentage', '0'))
        scale.max_percentage = Decimal(request.POST.get('max_percentage', '0'))
        scale.aggregate_points = int(request.POST.get('aggregate_points') or 0) or None
        scale.interpretation = request.POST.get('interpretation', '').strip()
        scale.is_pass = bool(request.POST.get('is_pass'))
        scale.is_credit = bool(request.POST.get('is_credit'))
        scale.order = int(request.POST.get('order') or 0)
        scale.save()
    except (ValueError, InvalidOperation, ValidationError) as e:
        return render(request, 'gradebook/includes/modal_grade_scale.html', {
            'system': scale.grading_system,
            'scale': scale,
            'error': str(e),
        })

    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'closeModal, refreshSettings'
    return response


@login_required
@admin_required
def grade_scale_delete(request, pk):
    """Delete a grade scale (Admin only)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    scale = get_object_or_404(GradeScale, pk=pk)
    scale.delete()

    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'refreshSettings'
    return response


# ============ Assessment Category CRUD ============

@login_required
@admin_required
def categories(request):
    """List all assessment categories (Admin only)."""
    cats = AssessmentCategory.objects.all()
    total = sum(c.percentage for c in cats if c.is_active)

    return render(request, 'gradebook/partials/categories_list.html', {
        'categories': cats,
        'total_percentage': total,
    })


@login_required
@admin_required
def category_create(request):
    """Create a new assessment category (Admin only)."""
    if request.method == 'GET':
        return render(request, 'gradebook/includes/modal_category.html', {
            'category_types': AssessmentCategory.CATEGORY_TYPES,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    name = request.POST.get('name', '').strip()
    short_name = request.POST.get('short_name', '').strip().upper()
    percentage = _safe_int(request.POST.get('percentage', 0))

    if not name or not short_name:
        return render(request, 'gradebook/includes/modal_category.html', {
            'error': 'Name and short name are required.',
            'category_types': AssessmentCategory.CATEGORY_TYPES,
        })

    # Check total won't exceed 100%
    current_total = AssessmentCategory.objects.filter(
        is_active=True
    ).aggregate(total=models.Sum('percentage'))['total'] or 0

    if current_total + percentage > 100:
        return render(request, 'gradebook/includes/modal_category.html', {
            'error': f'Total percentage would exceed 100%. Current: {current_total}%',
            'category_types': AssessmentCategory.CATEGORY_TYPES,
        })

    # Parse advisory fields
    expected_assessments = _safe_int(request.POST.get('expected_assessments', 0))
    min_assessments = _safe_int(request.POST.get('min_assessments', 0))
    max_assessments = _safe_int(request.POST.get('max_assessments', 0))

    # Validate advisory fields
    if min_assessments > 0 and max_assessments > 0 and min_assessments > max_assessments:
        return render(request, 'gradebook/includes/modal_category.html', {
            'error': 'Minimum assessments cannot be greater than maximum assessments.',
            'category_types': AssessmentCategory.CATEGORY_TYPES,
        })

    AssessmentCategory.objects.create(
        name=name,
        short_name=short_name,
        category_type=request.POST.get('category_type', 'OTHER'),
        percentage=percentage,
        order=_safe_int(request.POST.get('order', 0)),
        expected_assessments=expected_assessments,
        min_assessments=min_assessments,
        max_assessments=max_assessments,
    )

    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'closeModal, refreshSettings'
    return response


@login_required
@admin_required
def category_edit(request, pk):
    """Edit an assessment category (Admin only)."""
    category = get_object_or_404(AssessmentCategory, pk=pk)

    if request.method == 'GET':
        return render(request, 'gradebook/includes/modal_category.html', {
            'category': category,
            'category_types': AssessmentCategory.CATEGORY_TYPES,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    # Parse advisory fields
    expected_assessments = _safe_int(request.POST.get('expected_assessments', 0))
    min_assessments = _safe_int(request.POST.get('min_assessments', 0))
    max_assessments = _safe_int(request.POST.get('max_assessments', 0))

    # Validate advisory fields
    if min_assessments > 0 and max_assessments > 0 and min_assessments > max_assessments:
        return render(request, 'gradebook/includes/modal_category.html', {
            'category': category,
            'category_types': AssessmentCategory.CATEGORY_TYPES,
            'error': 'Minimum assessments cannot be greater than maximum assessments.',
        })

    new_percentage = _safe_int(request.POST.get('percentage', 0))

    # Check total won't exceed 100% (excluding this category's current percentage)
    current_total = AssessmentCategory.objects.filter(
        is_active=True
    ).exclude(pk=category.pk).aggregate(total=models.Sum('percentage'))['total'] or 0

    if current_total + new_percentage > 100:
        return render(request, 'gradebook/includes/modal_category.html', {
            'category': category,
            'category_types': AssessmentCategory.CATEGORY_TYPES,
            'error': f'Total percentage would exceed 100%. Other categories: {current_total}%',
        })

    category.name = request.POST.get('name', '').strip()
    category.short_name = request.POST.get('short_name', '').strip().upper()
    category.category_type = request.POST.get('category_type', 'OTHER')
    category.percentage = new_percentage
    category.order = _safe_int(request.POST.get('order', 0))
    category.expected_assessments = expected_assessments
    category.min_assessments = min_assessments
    category.max_assessments = max_assessments
    category.is_active = request.POST.get('is_active') == 'on'
    category.save()

    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'closeModal, refreshSettings'
    return response


@login_required
@admin_required
def category_delete(request, pk):
    """Delete an assessment category (Admin only)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    category = get_object_or_404(AssessmentCategory, pk=pk)
    category.delete()

    response = HttpResponse(status=204)
    response['HX-Trigger'] = 'refreshSettings'
    return response