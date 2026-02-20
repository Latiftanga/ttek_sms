import json

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db import transaction
from django.urls import reverse
from django.db.models import Count, Q
from django.contrib import messages

from academics.models import Class, StudentSubjectEnrollment
from core.models import AcademicYear
from students.models import Student, Enrollment
from .utils import admin_required, htmx_render


# Max level_number per level_type (when promoted past this → final year / graduation)
MAX_LEVEL = {
    'creche': 2,
    'nursery': 2,
    'kg': 2,
    'basic': 9,
    'shs': 3,
}


def _is_final_level(class_obj):
    """Check if a class is at the final level for its level_type."""
    return class_obj.level_number >= MAX_LEVEL.get(class_obj.level_type, 99)


def _find_natural_target(class_obj):
    """Find the natural next-level class (same type, level+1, same programme, same section)."""
    return Class.objects.filter(
        level_type=class_obj.level_type,
        level_number=class_obj.level_number + 1,
        programme=class_obj.programme,
        section=class_obj.section,
        is_active=True,
    ).first()


@admin_required
def promotion(request):
    """Show classes grouped by level for class-level promotion."""
    breadcrumbs = [
        {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
        {'label': 'Students', 'url': '/students/'},
        {'label': 'Promotion'},
    ]

    current_year = AcademicYear.get_current()
    if not current_year:
        return render(request, 'students/promotion.html', {
            'error': 'No current academic year set. Please configure the academic year first.',
            'breadcrumbs': breadcrumbs,
            'back_url': '/students/',
        })

    next_year = AcademicYear.objects.filter(
        start_date__gt=current_year.end_date
    ).order_by('start_date').first()

    # Get active classes with enrolled student counts for current year
    classes = Class.objects.filter(is_active=True).annotate(
        enrolled_count=Count(
            'enrollments',
            filter=Q(
                enrollments__academic_year=current_year,
                enrollments__status=Enrollment.Status.ACTIVE,
                enrollments__student__status=Student.Status.ACTIVE,
            )
        )
    ).select_related('programme').order_by(
        'level_type', '-level_number', 'programme__name', 'section'
    )

    # Build flat options list for select_input: [(url, label), ...]
    class_options = []
    for c in classes:
        count = c.enrolled_count
        label = f"{c.name} ({count} student{'s' if count != 1 else ''})"
        if _is_final_level(c):
            label += " - Final year"
        if count == 0:
            label += " - Empty"
        url = reverse('students:promotion_detail', args=[c.pk])
        class_options.append((url, label))

    return htmx_render(
        request,
        'students/promotion.html',
        'students/partials/promotion_content.html',
        {
            'current_year': current_year,
            'next_year': next_year,
            'class_options': class_options,
            'breadcrumbs': breadcrumbs,
            'back_url': '/students/',
        }
    )


@admin_required
def promotion_detail(request, pk):
    """Show per-class promotion form with student list."""
    class_obj = get_object_or_404(Class, pk=pk)

    current_year = AcademicYear.get_current()
    if not current_year:
        return HttpResponse(
            '<div class="alert alert-error">No current academic year set.</div>'
        )

    next_year = AcademicYear.objects.filter(
        start_date__gt=current_year.end_date
    ).order_by('start_date').first()

    if not next_year:
        return HttpResponse(
            '<div class="alert alert-warning">No next academic year configured.</div>'
        )

    is_final = _is_final_level(class_obj)

    # Find natural target and all target classes at next level
    natural_target = None
    target_classes = Class.objects.none()
    if not is_final:
        natural_target = _find_natural_target(class_obj)
        target_classes = Class.objects.filter(
            level_type=class_obj.level_type,
            level_number=class_obj.level_number + 1,
            is_active=True,
        ).select_related('programme').order_by('name')

    # Get students with active enrollment in this class for current year
    students = Student.objects.filter(
        enrollments__class_assigned=class_obj,
        enrollments__academic_year=current_year,
        enrollments__status=Enrollment.Status.ACTIVE,
        status=Student.Status.ACTIVE
    ).order_by('last_name', 'first_name')

    # Get same-level classes for repeater target (include source class)
    repeat_target_classes = Class.objects.filter(
        level_type=class_obj.level_type,
        level_number=class_obj.level_number,
        is_active=True,
    ).select_related('programme').order_by('name')

    # Build options lists for select_input tags
    target_options = [(str(tc.pk), tc.name) for tc in target_classes]
    repeat_options = [
        (str(rc.pk), f"{rc.name} (same class)" if rc.pk == class_obj.pk else rc.name)
        for rc in repeat_target_classes
    ]
    natural_target_pk = str(natural_target.pk) if natural_target else ''

    return render(request, 'students/partials/promotion_detail.html', {
        'class': class_obj,
        'students': students,
        'is_final': is_final,
        'natural_target_pk': natural_target_pk,
        'target_options': target_options,
        'has_target': target_classes.exists(),
        'current_year': current_year,
        'next_year': next_year,
        'repeat_options': repeat_options,
        'default_repeat_pk': str(class_obj.pk),
    })


def _htmx_toast_or_redirect(request, message, toast_type='error'):
    """For HTMX: show toast + error alert in detail area. Otherwise: redirect."""
    if request.htmx:
        icon = 'circle-xmark' if toast_type == 'error' else 'triangle-exclamation'
        alert_type = 'error' if toast_type == 'error' else 'warning'
        response = HttpResponse(
            f'<div class="alert alert-{alert_type} shadow-sm">'
            f'<i class="fa-solid fa-{icon}"></i>'
            f'<span>{message}</span></div>'
        )
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': message, 'type': toast_type}
        })
        response['HX-Retarget'] = '#promotion-detail-area'
        response['HX-Reswap'] = 'innerHTML'
        return response
    messages.error(request, message)
    return redirect('students:promotion')


@admin_required
def promotion_process(request):
    """Process class-level promotion for a single class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    class_id = request.POST.get('class_id')
    next_year_id = request.POST.get('next_year')
    target_class_id = request.POST.get('target_class_id')

    if not class_id or not next_year_id:
        return _htmx_toast_or_redirect(request, 'Missing required parameters.')

    class_obj = get_object_or_404(Class, pk=class_id)
    next_year = get_object_or_404(AcademicYear, pk=next_year_id)
    current_year = AcademicYear.get_current()

    if not current_year:
        return _htmx_toast_or_redirect(request, 'No current academic year set.')

    is_final = _is_final_level(class_obj)

    # Guard: check if this class was already processed for this year
    already_processed = Enrollment.objects.filter(
        class_assigned=class_obj,
        academic_year=current_year,
        status__in=[
            Enrollment.Status.PROMOTED,
            Enrollment.Status.GRADUATED,
            Enrollment.Status.REPEATED,
        ],
    ).exists()
    if already_processed:
        return _htmx_toast_or_redirect(
            request,
            f'{class_obj.name} has already been processed for {current_year}.',
            'warning'
        )

    # Resolve target class for non-final promotions
    target_class = None
    if not is_final:
        if not target_class_id:
            return _htmx_toast_or_redirect(request, 'No target class selected.')
        target_class = get_object_or_404(Class, pk=target_class_id)

    # Parse student actions
    student_actions = {}
    for key, value in request.POST.items():
        if key.startswith('action_'):
            student_id = key.replace('action_', '')
            student_actions[student_id] = {
                'action': value,
                'repeat_target_id': request.POST.get(f'repeat_target_{student_id}'),
            }

    # Get all enrolled students for this class in current year
    enrollments = Enrollment.objects.filter(
        class_assigned=class_obj,
        academic_year=current_year,
        status=Enrollment.Status.ACTIVE,
        student__status=Student.Status.ACTIVE,
    ).select_related('student')

    promoted_count = 0
    repeated_count = 0
    graduated_count = 0
    skipped_count = 0
    errors = []

    with transaction.atomic():
        for enrollment in enrollments:
            student = enrollment.student
            sid = str(student.pk)
            action_data = student_actions.get(sid, {})
            action = action_data.get('action', 'promote')

            if action == 'skip':
                skipped_count += 1
                continue

            if action == 'repeat':
                repeat_target_id = action_data.get('repeat_target_id')
                if not repeat_target_id:
                    errors.append(f'{student.full_name}: No repeat target class selected')
                    continue

                try:
                    repeat_class = Class.objects.get(pk=repeat_target_id)
                except Class.DoesNotExist:
                    errors.append(f'{student.full_name}: Invalid repeat target class')
                    continue

                # Mark old enrollment as repeated
                enrollment.status = Enrollment.Status.REPEATED
                enrollment.save(update_fields=['status', 'updated_at'])

                # Move student to the repeat target class
                student.current_class = repeat_class
                student.save(update_fields=['current_class', 'updated_at'])

                # Create new enrollment in repeat target class
                Enrollment.objects.create(
                    student=student,
                    academic_year=next_year,
                    class_assigned=repeat_class,
                    class_name=repeat_class.name,
                    status=Enrollment.Status.ACTIVE,
                    promoted_from=enrollment,
                    remarks='Repeated',
                )

                # Deactivate old subject enrollments, enroll in new class subjects
                StudentSubjectEnrollment.objects.filter(
                    student=student,
                    class_subject__class_assigned=class_obj,
                ).update(is_active=False)
                StudentSubjectEnrollment.enroll_student_in_class_subjects(
                    student, repeat_class
                )

                repeated_count += 1
                continue

            if action == 'graduate':
                if not is_final:
                    errors.append(f'{student.full_name}: Cannot graduate from non-final class')
                    continue

                enrollment.status = Enrollment.Status.GRADUATED
                enrollment.save(update_fields=['status', 'updated_at'])

                student.status = Student.Status.GRADUATED
                student.current_class = None
                student.save(update_fields=['status', 'current_class', 'updated_at'])

                StudentSubjectEnrollment.objects.filter(
                    student=student,
                    class_subject__class_assigned=class_obj,
                ).update(is_active=False)

                graduated_count += 1
                continue

            # Default action: promote
            if is_final:
                # Final year students default to graduate
                enrollment.status = Enrollment.Status.GRADUATED
                enrollment.save(update_fields=['status', 'updated_at'])

                student.status = Student.Status.GRADUATED
                student.current_class = None
                student.save(update_fields=['status', 'current_class', 'updated_at'])

                StudentSubjectEnrollment.objects.filter(
                    student=student,
                    class_subject__class_assigned=class_obj,
                ).update(is_active=False)

                graduated_count += 1
            else:
                # Mark current enrollment as promoted
                enrollment.status = Enrollment.Status.PROMOTED
                enrollment.save(update_fields=['status', 'updated_at'])

                # Create new enrollment in the TARGET class
                Enrollment.objects.create(
                    student=student,
                    academic_year=next_year,
                    class_assigned=target_class,
                    class_name=target_class.name,
                    status=Enrollment.Status.ACTIVE,
                    promoted_from=enrollment,
                )

                # Move student to target class
                student.current_class = target_class
                student.save(update_fields=['current_class', 'updated_at'])

                # Deactivate old subject enrollments, enroll in target class subjects
                StudentSubjectEnrollment.objects.filter(
                    student=student,
                    class_subject__class_assigned=class_obj,
                ).update(is_active=False)
                StudentSubjectEnrollment.enroll_student_in_class_subjects(
                    student, target_class
                )

                promoted_count += 1

    # Build summary parts
    parts = []
    if promoted_count:
        target_name = target_class.name if target_class else 'N/A'
        parts.append(f'{promoted_count} promoted to {target_name}')
    if repeated_count:
        parts.append(f'{repeated_count} set to repeat')
    if graduated_count:
        parts.append(f'{graduated_count} graduated')
    if skipped_count:
        parts.append(f'{skipped_count} skipped')

    summary = f'{class_obj.name}: ' + ', '.join(parts) + '.'
    toast_type = 'warning' if errors else 'success'
    if errors:
        summary += f' Errors: {"; ".join(errors[:5])}'

    if request.htmx:
        response = HttpResponse(
            f'<div class="alert alert-success shadow-sm">'
            f'<i class="fa-solid fa-circle-check"></i>'
            f'<span>{summary}</span></div>'
        )
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': summary, 'type': toast_type}
        })
        response['HX-Retarget'] = '#promotion-detail-area'
        response['HX-Reswap'] = 'innerHTML'
        return response

    messages.success(request, summary)
    return redirect('students:promotion')
