"""
Promotion history views for teachers.

Provides CRUD operations for rank/promotion records (admin or teacher's own).
"""
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string

from teachers.models import Teacher, Promotion
from teachers.forms import PromotionForm
from .utils import admin_or_owner, htmx_render


@admin_or_owner
def promotion_list(request, pk):
    """List all promotions for a teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)
    promotions = Promotion.objects.filter(teacher=teacher)

    context = {
        'teacher': teacher,
        'promotions': promotions,
    }

    return htmx_render(
        request,
        'teachers/partials/tab_promotions.html',
        'teachers/partials/tab_promotions.html',
        context
    )


@admin_or_owner
def promotion_create(request, pk):
    """Create a new promotion for a teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)

    if request.method == 'POST':
        form = PromotionForm(request.POST)
        if form.is_valid():
            promotion = form.save(commit=False)
            promotion.teacher = teacher
            promotion.save()
            messages.success(request, f"Added promotion: {promotion.rank}")

            if request.htmx:
                promotions = Promotion.objects.filter(teacher=teacher)
                html = render_to_string(
                    'teachers/partials/tab_promotions.html',
                    {'teacher': teacher, 'promotions': promotions},
                    request
                )
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('teachers:teacher_detail', pk=pk)
    else:
        form = PromotionForm()

    context = {
        'form': form,
        'teacher': teacher,
        'is_edit': False,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_promotion_form.html',
        'teachers/partials/modal_promotion_form.html',
        context
    )


@admin_or_owner
def promotion_edit(request, pk, promo_pk):
    """Edit a promotion."""
    teacher = get_object_or_404(Teacher, pk=pk)
    promotion = get_object_or_404(Promotion, pk=promo_pk, teacher=teacher)

    if request.method == 'POST':
        form = PromotionForm(request.POST, instance=promotion)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated promotion: {promotion.rank}")

            if request.htmx:
                promotions = Promotion.objects.filter(teacher=teacher)
                html = render_to_string(
                    'teachers/partials/tab_promotions.html',
                    {'teacher': teacher, 'promotions': promotions},
                    request
                )
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('teachers:teacher_detail', pk=pk)
    else:
        form = PromotionForm(instance=promotion)

    context = {
        'form': form,
        'teacher': teacher,
        'promotion': promotion,
        'is_edit': True,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_promotion_form.html',
        'teachers/partials/modal_promotion_form.html',
        context
    )


@admin_or_owner
def promotion_delete(request, pk, promo_pk):
    """Delete a promotion."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)
    promotion = get_object_or_404(Promotion, pk=promo_pk, teacher=teacher)

    rank = promotion.rank
    promotion.delete()
    messages.success(request, f"Deleted promotion: {rank}")

    if request.htmx:
        promotions = Promotion.objects.filter(teacher=teacher)
        return htmx_render(
            request,
            'teachers/partials/tab_promotions.html',
            'teachers/partials/tab_promotions.html',
            {'teacher': teacher, 'promotions': promotions}
        )

    return redirect('teachers:teacher_detail', pk=pk)
