import json
import logging

from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
from django.core.paginator import Paginator

from .base import admin_required, htmx_render, is_school_admin
from ..models import RemarkTemplate, TermReport
from academics.models import Class
from students.models import Student
from core.models import Term

logger = logging.getLogger(__name__)


# ============ Bulk Remarks Entry ============

@login_required
def bulk_remarks_entry(request, class_id):
    """
    Bulk remarks entry page for form teachers.
    Shows all students with their performance data and input fields.
    Supports pagination for mobile-friendly experience.
    """
    current_term = Term.get_current()
    class_obj = get_object_or_404(Class, pk=class_id)
    user = request.user

    # Permission check - must be class teacher or admin
    if not is_school_admin(user):
        if not (getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile')):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('gradebook:reports')
        if class_obj.class_teacher != user.teacher_profile:
            messages.error(request, 'You can only enter remarks for your homeroom class.')
            return redirect('gradebook:reports')

    # Get all students for counting
    all_students = list(Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('last_name', 'first_name'))

    if not all_students:
        messages.info(request, 'No active students found in this class.')
        return redirect('gradebook:reports')

    # Prefetch all term reports for counting completed
    all_student_ids = [s.id for s in all_students]
    all_reports = {
        r.student_id: r for r in TermReport.objects.filter(
            student_id__in=all_student_ids,
            term=current_term
        )
    }

    # Count completed remarks across all students
    completed_count = 0
    for student in all_students:
        report = all_reports.get(student.id)
        if report and report.class_teacher_remark:
            completed_count += 1

    # Pagination - 10 students per page for mobile-friendly experience
    page_number = request.GET.get('page', 1)
    paginator = Paginator(all_students, 10)
    page_obj = paginator.get_page(page_number)

    # Attach term reports to paginated students
    for student in page_obj:
        student.term_report = all_reports.get(student.id)

    # Get remark templates
    remark_templates = RemarkTemplate.objects.filter(is_active=True).order_by('category', 'order')

    # Group templates by category
    templates_by_category = {}
    for template in remark_templates:
        category = template.get_category_display()
        if category not in templates_by_category:
            templates_by_category[category] = []
        templates_by_category[category].append(template)

    context = {
        'class_obj': class_obj,
        'students': page_obj,
        'page_obj': page_obj,
        'current_term': current_term,
        'templates_by_category': templates_by_category,
        'conduct_choices': TermReport.CONDUCT_CHOICES,
        'rating_choices': TermReport.RATING_CHOICES,
        'completed_count': completed_count,
        'total_count': len(all_students),
        'is_admin': is_school_admin(user),
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook', 'url': '/gradebook/'},
            {'label': 'Reports', 'url': '/gradebook/reports/'},
            {'label': f'{class_obj.name} Remarks'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/bulk_remarks.html',
        'gradebook/partials/bulk_remarks_content.html',
        context
    )


@login_required
def bulk_remark_save(request):
    """Save individual student remark via HTMX (auto-save)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    student_id = request.POST.get('student_id')
    field = request.POST.get('field')
    value = request.POST.get('value', '').strip()

    current_term = Term.get_current()
    if not current_term:
        return HttpResponse('No current term', status=400)

    student = get_object_or_404(Student.objects.select_related('current_class'), pk=student_id)

    # Permission check
    user = request.user
    if not is_school_admin(user):
        if not (getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile')):
            return HttpResponse(status=403)
        if not student.current_class or student.current_class.class_teacher != user.teacher_profile:
            return HttpResponse(status=403)

    # Get or create term report
    term_report, created = TermReport.objects.get_or_create(
        student=student,
        term=current_term,
        defaults={'out_of': 1}
    )

    # Update the field
    allowed_fields = [
        'class_teacher_remark', 'conduct_rating', 'attitude_rating',
        'interest_rating', 'attendance_rating'
    ]

    if field in allowed_fields:
        setattr(term_report, field, value)
        term_report.save(update_fields=[field])

        # Return success indicator
        response = HttpResponse(status=200)
        response['HX-Trigger'] = json.dumps({
            'remarkSaved': {
                'student_id': str(student_id),
                'field': field
            }
        })
        return response

    return HttpResponse('Invalid field', status=400)


@login_required
def bulk_remarks_sign(request, class_id):
    """Sign off all remarks for a class (class teacher confirmation)."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    current_term = Term.get_current()
    class_obj = get_object_or_404(Class, pk=class_id)
    user = request.user

    # Permission check
    if not is_school_admin(user):
        if not (getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile')):
            return HttpResponse(status=403)
        if class_obj.class_teacher != user.teacher_profile:
            return HttpResponse(status=403)

    # Sign all reports for this class
    now = timezone.now()

    updated = TermReport.objects.filter(
        student__current_class=class_obj,
        term=current_term,
        class_teacher_signed=False
    ).update(
        class_teacher_signed=True,
        class_teacher_signed_at=now
    )

    response = HttpResponse(status=200)
    response['HX-Trigger'] = json.dumps({
        'showToast': {
            'message': f'Signed {updated} report(s) successfully',
            'type': 'success'
        },
        'refreshPage': True
    })
    return response


# ============ Remark Templates Management ============

@login_required
@admin_required
def remark_templates(request):
    """List and manage remark templates (Admin only)."""
    templates = RemarkTemplate.objects.all().order_by('category', 'order')

    # Group by category
    templates_by_category = {}
    for template in templates:
        category = template.get_category_display()
        if category not in templates_by_category:
            templates_by_category[category] = []
        templates_by_category[category].append(template)

    context = {
        'templates': templates,
        'templates_by_category': templates_by_category,
        'categories': RemarkTemplate.PERFORMANCE_CATEGORY,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook', 'url': '/gradebook/'},
            {'label': 'Remark Templates'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/remark_templates.html',
        'gradebook/partials/remark_templates_content.html',
        context
    )


@login_required
@admin_required
def remark_template_create(request):
    """Create a new remark template."""
    if request.method == 'GET':
        return render(request, 'gradebook/includes/modal_remark_template.html', {
            'categories': RemarkTemplate.PERFORMANCE_CATEGORY,
            'mode': 'create',
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    category = request.POST.get('category', 'GENERAL')
    content = request.POST.get('content', '').strip()
    order = int(request.POST.get('order', 0))

    if not content:
        return render(request, 'gradebook/includes/modal_remark_template.html', {
            'categories': RemarkTemplate.PERFORMANCE_CATEGORY,
            'mode': 'create',
            'error': 'Remark content is required',
            'form_data': {'category': category, 'content': content, 'order': order},
        })

    RemarkTemplate.objects.create(
        category=category,
        content=content,
        order=order,
    )

    response = HttpResponse(status=204)
    response['HX-Trigger'] = json.dumps({
        'closeModal': True,
        'showToast': {'message': 'Template created successfully', 'type': 'success'},
        'refreshTemplates': True
    })
    return response


@login_required
@admin_required
def remark_template_edit(request, pk):
    """Edit a remark template."""
    template = get_object_or_404(RemarkTemplate, pk=pk)

    if request.method == 'GET':
        return render(request, 'gradebook/includes/modal_remark_template.html', {
            'template': template,
            'categories': RemarkTemplate.PERFORMANCE_CATEGORY,
            'mode': 'edit',
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    category = request.POST.get('category', 'GENERAL')
    content = request.POST.get('content', '').strip()
    order = int(request.POST.get('order', 0))
    is_active = request.POST.get('is_active') == 'on'

    if not content:
        return render(request, 'gradebook/includes/modal_remark_template.html', {
            'template': template,
            'categories': RemarkTemplate.PERFORMANCE_CATEGORY,
            'mode': 'edit',
            'error': 'Remark content is required',
        })

    template.category = category
    template.content = content
    template.order = order
    template.is_active = is_active
    template.save()

    response = HttpResponse(status=204)
    response['HX-Trigger'] = json.dumps({
        'closeModal': True,
        'showToast': {'message': 'Template updated successfully', 'type': 'success'},
        'refreshTemplates': True
    })
    return response


@login_required
@admin_required
def remark_template_delete(request, pk):
    """Delete a remark template."""
    template = get_object_or_404(RemarkTemplate, pk=pk)

    if request.method != 'POST':
        return HttpResponse(status=405)

    template.delete()

    response = HttpResponse(status=200)
    response['HX-Trigger'] = json.dumps({
        'showToast': {'message': 'Template deleted', 'type': 'success'},
        'refreshTemplates': True
    })
    return response
