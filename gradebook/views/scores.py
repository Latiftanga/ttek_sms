from collections import defaultdict
from decimal import Decimal
import logging

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.db import transaction

from .base import (
    teacher_or_admin_required, htmx_render, is_school_admin,
    can_edit_scores, get_client_ip, admin_required, ratelimit
)
from ..models import (
    AssessmentCategory, Assignment, Score, ScoreAuditLog
)
from .. import config
from academics.models import Class, Subject, ClassSubject, StudentSubjectEnrollment
from students.models import Student
from core.models import Term

logger = logging.getLogger(__name__)

# ============ Score Entry ============

@login_required
def score_entry(request):
    """Score entry page - select class and subject."""
    current_term = Term.get_current()
    user = request.user

    # Filter classes based on user role
    if is_school_admin(user):
        # Admins see all classes
        classes = Class.objects.filter(is_active=True).order_by('level_number', 'name')
    elif getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile'):
        # Teachers see only classes they're assigned to
        teacher = user.teacher_profile
        assigned_class_ids = ClassSubject.objects.filter(
            teacher=teacher
        ).values_list('class_assigned_id', flat=True).distinct()
        classes = Class.objects.filter(
            id__in=assigned_class_ids,
            is_active=True
        ).order_by('level_number', 'name')
    else:
        classes = Class.objects.none()

    context = {
        'current_term': current_term,
        'classes': classes,
        'is_admin': is_school_admin(request.user),
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook', 'url': '/gradebook/'},
            {'label': 'Score Entry'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/score_entry.html',
        'gradebook/partials/score_entry_content.html',
        context
    )


@login_required
@teacher_or_admin_required
def score_entry_form(request, class_id, subject_id):
    """Score entry form for a specific class/subject.

    OPTIMIZED: Uses select_related and builds lookup dict for O(1) score access.
    Supports both table view (desktop) and card view (mobile).
    """
    current_term = Term.get_current()
    class_obj = get_object_or_404(Class, pk=class_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    grades_locked = current_term.grades_locked if current_term else False

    # Check if user can edit scores for this subject/class
    can_edit = can_edit_scores(request.user, class_obj, subject)

    # Get the ClassSubject for this class/subject combination
    class_subject = ClassSubject.objects.filter(
        class_assigned=class_obj,
        subject=subject
    ).first()

    # Check if there are subject enrollments for this class
    # This determines whether we filter students by enrollment (SHS) or show all (Basic)
    has_enrollments = StudentSubjectEnrollment.objects.filter(
        class_subject__class_assigned=class_obj,
        is_active=True
    ).exists()

    if has_enrollments and class_subject:
        # SHS behavior: Only show students enrolled in this specific subject
        enrolled_student_ids = StudentSubjectEnrollment.objects.filter(
            class_subject=class_subject,
            is_active=True
        ).values_list('student_id', flat=True)

        students = list(Student.objects.filter(
            id__in=enrolled_student_ids,
            current_class=class_obj
        ).only(
            'id', 'first_name', 'last_name', 'admission_number'
        ).order_by('last_name', 'first_name'))
    else:
        # Basic school behavior: Show all students in the class
        students = list(Student.objects.filter(
            current_class=class_obj
        ).only(
            'id', 'first_name', 'last_name', 'admission_number'
        ).order_by('last_name', 'first_name'))

    # Get assignments for this subject/term
    assignments = list(Assignment.objects.filter(
        subject=subject,
        term=current_term
    ).select_related('assessment_category').order_by('assessment_category__order', 'name'))

    # Get existing scores in single query - build nested dict for O(1) template lookup
    # Structure: {student_id: {assignment_id: points}}
    scores_dict = defaultdict(dict)
    if students and assignments:
        student_ids = [s.id for s in students]
        assignment_ids = [a.id for a in assignments]
        for score in Score.objects.filter(
            student_id__in=student_ids,
            assignment_id__in=assignment_ids
        ).only('student_id', 'assignment_id', 'points'):
            scores_dict[score.student_id][score.assignment_id] = score.points

    # Get categories (small table, usually cached)
    categories = list(AssessmentCategory.objects.filter(is_active=True).order_by('order'))

    # Determine if editing is allowed (not locked AND authorized)
    editing_allowed = can_edit and not grades_locked

    # Check view mode preference (table or card)
    view_mode = request.GET.get('view', 'auto')  # auto, table, or card

    context = {
        'class_obj': class_obj,
        'subject': subject,
        'current_term': current_term,
        'students': students,
        'assignments': assignments,
        'categories': categories,
        'scores_dict': dict(scores_dict),  # Convert to regular dict for template
        'grades_locked': grades_locked,
        'can_edit': can_edit,
        'editing_allowed': editing_allowed,
        'view_mode': view_mode,
    }

    return render(request, 'gradebook/partials/score_form.html', context)


@login_required
@teacher_or_admin_required
def score_entry_student(request, class_id, subject_id, student_id):
    """Mobile-optimized score entry for a single student.

    Shows all assignments for one student in a vertical card layout,
    optimized for touch input on mobile devices.
    """
    current_term = Term.get_current()
    class_obj = get_object_or_404(Class, pk=class_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    student = get_object_or_404(Student, pk=student_id, current_class=class_obj)
    grades_locked = current_term.grades_locked if current_term else False

    # Check if user can edit scores for this subject/class
    can_edit = can_edit_scores(request.user, class_obj, subject)
    editing_allowed = can_edit and not grades_locked

    # Get all students for navigation
    students = list(Student.objects.filter(
        current_class=class_obj
    ).only('id', 'first_name', 'last_name').order_by('last_name', 'first_name'))

    # Find current student index for prev/next navigation
    current_index = next((i for i, s in enumerate(students) if s.id == student.id), 0)
    prev_student = students[current_index - 1] if current_index > 0 else None
    next_student = students[current_index + 1] if current_index < len(students) - 1 else None

    # Get assignments grouped by category
    assignments = Assignment.objects.filter(
        subject=subject,
        term=current_term
    ).select_related('assessment_category').order_by('assessment_category__order', 'name')

    # Get existing scores for this student
    scores_dict = {}
    for score in Score.objects.filter(
        student=student,
        assignment__in=assignments
    ).only('assignment_id', 'points'):
        scores_dict[score.assignment_id] = score.points

    # Group assignments by category for better mobile display
    assignments_by_category = defaultdict(list)
    for assignment in assignments:
        assignments_by_category[assignment.assessment_category].append(assignment)

    context = {
        'class_obj': class_obj,
        'subject': subject,
        'current_term': current_term,
        'student': student,
        'students': students,
        'current_index': current_index,
        'prev_student': prev_student,
        'next_student': next_student,
        'assignments_by_category': dict(assignments_by_category),
        'scores_dict': scores_dict,
        'grades_locked': grades_locked,
        'can_edit': can_edit,
        'editing_allowed': editing_allowed,
    }

    return render(request, 'gradebook/partials/score_form_student.html', context)


@login_required
@teacher_or_admin_required
@ratelimit(key='user', rate='200/h')
def score_save(request):
    """Save scores via HTMX with audit logging. Rate limited to 200 requests/hour."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    student_id = request.POST.get('student_id')
    assignment_id = request.POST.get('assignment_id')
    points = request.POST.get('points', '').strip()

    if not all([student_id, assignment_id]):
        response = HttpResponse(status=200)
        response['HX-Trigger'] = '{"showToast": {"message": "Missing data", "type": "error"}}'
        return response

    student = get_object_or_404(Student.objects.select_related('current_class'), pk=student_id)
    assignment = get_object_or_404(Assignment.objects.select_related('term', 'subject'), pk=assignment_id)

    # Early check for authorization (before transaction)
    if not can_edit_scores(request.user, student.current_class, assignment.subject):
        response = HttpResponse(status=200)
        response['HX-Trigger'] = '{"showToast": {"message": "You are not authorized to edit scores for this subject", "type": "error"}}'
        return response

    # Get audit context
    client_ip = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]

    if points == '' or points is None:
        # Delete score if empty
        try:
            with transaction.atomic():
                # Re-check grade lock inside transaction with row lock
                term = Term.objects.select_for_update().get(pk=assignment.term_id)
                if term.grades_locked:
                    response = HttpResponse(status=200)
                    response['HX-Trigger'] = '{"showToast": {"message": "Grades are locked for this term", "type": "error"}}'
                    return response

                existing_score = Score.objects.filter(student=student, assignment=assignment).first()
                if existing_score:
                    old_value = existing_score.points
                    # Log deletion first
                    ScoreAuditLog.objects.create(
                        score=None,
                        student=student,
                        assignment=assignment,
                        user=request.user,
                        action='DELETE',
                        old_value=old_value,
                        new_value=None,
                        ip_address=client_ip,
                        user_agent=user_agent
                    )
                    existing_score.delete()
        except Exception as e:
            logger.error(f"Error deleting score: {e}")
            response = HttpResponse(status=200)
            response['HX-Trigger'] = '{"showToast": {"message": "Error deleting score", "type": "error"}}'
            return response
        return HttpResponse(status=200)

    # Get existing score for reverting on error
    existing_score = Score.objects.filter(student=student, assignment=assignment).first()
    old_value = existing_score.points if existing_score else None
    old_value_str = str(old_value) if old_value is not None else ''

    try:
        points_decimal = Decimal(points)
    except Exception:
        response = HttpResponse(status=200)
        response['HX-Trigger'] = (
            f'{{"showToast": {{"message": "Invalid number", "type": "error"}}, '
            f'"revertScore": {{"student": {student_id}, "assignment": {assignment_id}, "value": "{old_value_str}"}}}}'
        )
        return response

    # Validate range
    max_points = float(assignment.points_possible)
    if points_decimal < 0:
        response = HttpResponse(status=200)
        response['HX-Trigger'] = (
            f'{{"showToast": {{"message": "Score cannot be negative", "type": "error"}}, '
            f'"revertScore": {{"student": {student_id}, "assignment": {assignment_id}, "value": "{old_value_str}"}}}}'
        )
        return response

    if points_decimal > assignment.points_possible:
        response = HttpResponse(status=200)
        response['HX-Trigger'] = (
            f'{{"showToast": {{"message": "Maximum score is {max_points:.0f}", "type": "error"}}, '
            f'"revertScore": {{"student": {student_id}, "assignment": {assignment_id}, "value": "{old_value_str}"}}}}'
        )
        return response

    # Save score with transaction handling and race condition protection
    try:
        with transaction.atomic():
            # Re-check grade lock inside transaction with row lock to prevent race condition
            term = Term.objects.select_for_update().get(pk=assignment.term_id)
            if term.grades_locked:
                response = HttpResponse(status=200)
                response['HX-Trigger'] = '{"showToast": {"message": "Grades are locked for this term", "type": "error"}}'
                return response

            score, created = Score.objects.update_or_create(
                student=student,
                assignment=assignment,
                defaults={'points': points_decimal}
            )

            # Log the change
            ScoreAuditLog.objects.create(
                score=score,
                student=student,
                assignment=assignment,
                user=request.user,
                action='CREATE' if created else 'UPDATE',
                old_value=old_value,
                new_value=points_decimal,
                ip_address=client_ip,
                user_agent=user_agent
            )
    except Exception as e:
        logger.error(f"Error saving score: {e}")
        response = HttpResponse(status=200)
        response['HX-Trigger'] = (
            f'{{"showToast": {{"message": "Error saving score", "type": "error"}}, '
            f'"revertScore": {{"student": {student_id}, "assignment": "{assignment_id}", "value": "{old_value_str}"}}}}'
        )
        return response

    return HttpResponse(status=200)


# ============ Score Audit History ============

@login_required
@admin_required
def score_audit_history(request, student_id, assignment_id):
    """View audit history for a specific score."""
    student = get_object_or_404(Student, pk=student_id)
    assignment = get_object_or_404(Assignment, pk=assignment_id)

    logs = ScoreAuditLog.objects.filter(
        student=student,
        assignment=assignment
    ).select_related('user').order_by('-created_at')[:config.AUDIT_LOG_DISPLAY_LIMIT]

    return render(request, 'gradebook/partials/score_audit_history.html', {
        'student': student,
        'assignment': assignment,
        'logs': logs,
    })


@login_required
@teacher_or_admin_required
def score_changes_list(request, class_id, subject_id):
    """View all score changes for a class/subject in current term."""
    current_term = Term.get_current()
    class_obj = get_object_or_404(Class, pk=class_id)
    subject = get_object_or_404(Subject, pk=subject_id)

    # Get all assignments for this subject in current term
    assignments = Assignment.objects.filter(
        subject=subject,
        term=current_term
    )

    # Get all students in this class
    students = Student.objects.filter(current_class=class_obj)

    # Get all score changes for these students and assignments
    logs = ScoreAuditLog.objects.filter(
        student__in=students,
        assignment__in=assignments
    ).select_related(
        'student', 'assignment', 'assignment__assessment_category', 'user'
    ).order_by('-created_at')[:100]  # Limit to last 100 changes

    return render(request, 'gradebook/partials/score_changes_list.html', {
        'class_obj': class_obj,
        'subject': subject,
        'current_term': current_term,
        'logs': logs,
    })


# ============ Assignments ============

@login_required
def assignments(request, subject_id):
    """List assignments for a subject in current term."""
    current_term = Term.get_current()
    subject = get_object_or_404(Subject, pk=subject_id)

    assigns = Assignment.objects.filter(
        subject=subject,
        term=current_term
    ).select_related('assessment_category').order_by('assessment_category__order', 'name')

    categories = AssessmentCategory.objects.filter(is_active=True)

    return render(request, 'gradebook/partials/assignments_list.html', {
        'subject': subject,
        'assignments': assigns,
        'categories': categories,
        'current_term': current_term,
    })


@login_required
def assignment_create(request):
    """Create a new assignment."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    current_term = Term.get_current()
    if not current_term:
        return HttpResponse('No current term set', status=400)

    subject_id = request.POST.get('subject_id')
    category_id = request.POST.get('category_id')
    name = request.POST.get('name', '').strip()
    points_possible = request.POST.get('points_possible', '100')

    if not all([subject_id, category_id, name]):
        return HttpResponse('Missing required fields', status=400)

    subject = get_object_or_404(Subject, pk=subject_id)
    category = get_object_or_404(AssessmentCategory, pk=category_id)

    Assignment.objects.create(
        assessment_category=category,
        subject=subject,
        term=current_term,
        name=name,
        points_possible=int(points_possible),
    )

    # Return updated assignments list
    assigns = Assignment.objects.filter(
        subject=subject,
        term=current_term
    ).select_related('assessment_category').order_by('assessment_category__order', 'name')

    categories = AssessmentCategory.objects.filter(is_active=True)

    response = render(request, 'gradebook/partials/assignments_list.html', {
        'subject': subject,
        'assignments': assigns,
        'categories': categories,
        'current_term': current_term,
    })
    # Trigger score form refresh
    response['HX-Trigger'] = '{"assignmentsChanged": {"subject_id": %d}}' % subject.pk
    return response


@login_required
@teacher_or_admin_required
def assignment_edit(request, pk):
    """Edit an assignment."""
    assignment = get_object_or_404(Assignment.objects.select_related('subject', 'term', 'assessment_category'), pk=pk)
    subject = assignment.subject
    current_term = assignment.term

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        points_possible = request.POST.get('points_possible', '100')
        category_id = request.POST.get('category_id')

        if not name:
            return HttpResponse('Name is required', status=400)

        try:
            points = Decimal(points_possible)
            if points < 1:
                return HttpResponse('Points must be at least 1', status=400)
        except Exception:
            return HttpResponse('Invalid points value', status=400)

        # Update assignment
        assignment.name = name
        assignment.points_possible = points
        if category_id:
            category = get_object_or_404(AssessmentCategory, pk=category_id)
            assignment.assessment_category = category
        assignment.save()

        # Return updated assignments list
        assigns = Assignment.objects.filter(
            subject=subject,
            term=current_term
        ).select_related('assessment_category').order_by('assessment_category__order', 'name')

        categories = AssessmentCategory.objects.filter(is_active=True)

        response = render(request, 'gradebook/partials/assignments_list.html', {
            'subject': subject,
            'assignments': assigns,
            'categories': categories,
            'current_term': current_term,
        })
        response['HX-Trigger'] = '{"assignmentsChanged": {"subject_id": %d}}' % subject.pk
        return response

    # GET request - return edit form
    categories = AssessmentCategory.objects.filter(is_active=True)
    return render(request, 'gradebook/partials/assignment_edit_form.html', {
        'assignment': assignment,
        'categories': categories,
    })


@login_required
@teacher_or_admin_required
def assignment_delete(request, pk):
    """Delete an assignment and all associated scores."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    assignment = get_object_or_404(Assignment, pk=pk)
    subject = assignment.subject
    current_term = assignment.term

    # Check for existing scores (they will be cascade deleted)
    score_count = Score.objects.filter(assignment=assignment).count()
    if score_count > 0:
        logger.warning(
            f"Assignment '{assignment.name}' deleted by {request.user}. "
            f"{score_count} scores were cascade deleted."
        )

    assignment.delete()

    # Return updated assignments list
    assigns = Assignment.objects.filter(
        subject=subject,
        term=current_term
    ).select_related('assessment_category').order_by('assessment_category__order', 'name')

    categories = AssessmentCategory.objects.filter(is_active=True)

    response = render(request, 'gradebook/partials/assignments_list.html', {
        'subject': subject,
        'assignments': assigns,
        'categories': categories,
        'current_term': current_term,
    })
    # Trigger score form refresh
    response['HX-Trigger'] = '{"assignmentsChanged": {"subject_id": %d}}' % subject.pk
    return response