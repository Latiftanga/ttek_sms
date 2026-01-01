from decimal import Decimal
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import models

from .base import admin_required, htmx_render
from ..models import (
    GradingSystem, GradeScale, AssessmentCategory
)

@login_required
@admin_required
def settings(request):
    """Gradebook settings - grading systems and categories (Admin only)."""
    grading_systems = GradingSystem.objects.prefetch_related('scales').all()
    categories = AssessmentCategory.objects.all()

    # Check if percentages sum to 100
    total_percentage = sum(c.percentage for c in categories if c.is_active)

    context = {
        'grading_systems': grading_systems,
        'categories': categories,
        'total_percentage': total_percentage,
    }

    return htmx_render(
        request,
        'gradebook/settings.html',
        'gradebook/partials/settings_content.html',
        context
    )


# ============ Grading System CRUD ============

@login_required
@admin_required
def grading_systems(request):
    """List all grading systems (Admin only)."""
    systems = GradingSystem.objects.prefetch_related('scales').all()
    return render(request, 'gradebook/partials/grading_systems_list.html', {
        'grading_systems': systems,
    })


@login_required
@admin_required
def grading_system_create(request):
    """Create a new grading system (Admin only)."""
    if request.method == 'GET':
        return render(request, 'gradebook/includes/modal_grading_system.html', {
            'levels': GradingSystem.SCHOOL_LEVELS,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    name = request.POST.get('name', '').strip()
    level = request.POST.get('level', 'BASIC')
    description = request.POST.get('description', '').strip()

    if not name:
        return render(request, 'gradebook/includes/modal_grading_system.html', {
            'error': 'Name is required.',
            'levels': GradingSystem.SCHOOL_LEVELS,
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
            'levels': GradingSystem.SCHOOL_LEVELS,
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
            is_pass=request.POST.get('is_pass') == 'on',
            is_credit=request.POST.get('is_credit') == 'on',
            order=int(request.POST.get('order') or 0),
        )
    except Exception as e:
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
        scale.is_pass = request.POST.get('is_pass') == 'on'
        scale.is_credit = request.POST.get('is_credit') == 'on'
        scale.order = int(request.POST.get('order') or 0)
        scale.save()
    except Exception as e:
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
        return render(request, 'gradebook/includes/modal_category.html', {})

    if request.method != 'POST':
        return HttpResponse(status=405)

    name = request.POST.get('name', '').strip()
    short_name = request.POST.get('short_name', '').strip().upper()
    percentage = int(request.POST.get('percentage', 0))

    if not name or not short_name:
        return render(request, 'gradebook/includes/modal_category.html', {
            'error': 'Name and short name are required.',
        })

    # Check total won't exceed 100%
    current_total = AssessmentCategory.objects.filter(
        is_active=True
    ).aggregate(total=models.Sum('percentage'))['total'] or 0

    if current_total + percentage > 100:
        return render(request, 'gradebook/includes/modal_category.html', {
            'error': f'Total percentage would exceed 100%. Current: {current_total}%',
        })

    AssessmentCategory.objects.create(
        name=name,
        short_name=short_name,
        percentage=percentage,
        order=int(request.POST.get('order', 0)),
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
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    category.name = request.POST.get('name', '').strip()
    category.short_name = request.POST.get('short_name', '').strip().upper()
    category.percentage = int(request.POST.get('percentage', 0))
    category.order = int(request.POST.get('order', 0))
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