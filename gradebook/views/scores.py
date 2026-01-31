from collections import defaultdict
from decimal import Decimal
import json
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
from ..utils import validate_score
from .. import config
from academics.models import Class, Subject, ClassSubject, StudentSubjectEnrollment
from students.models import Student
from core.models import Term

logger = logging.getLogger(__name__)


def _build_error_response(
    message: str,
    student_id: str,
    assignment_id: str,
    old_value: str = '',
    error_code: str = 'error',
    hint: str = '',
    max_value: float = None
) -> HttpResponse:
    """
    Build a standardized error response for score save operations.

    Returns an HttpResponse with HX-Trigger header containing detailed error info
    for the frontend to display helpful feedback to teachers.
    """
    trigger_data = {
        'showToast': {
            'message': message,
            'type': 'error'
        },
        'revertScore': {
            'student': student_id,
            'assignment': assignment_id,
            'value': old_value
        },
        'scoreError': {
            'student': student_id,
            'assignment': assignment_id,
            'message': message,
            'code': error_code,
            'hint': hint,
        }
    }
    if max_value is not None:
        trigger_data['scoreError']['max'] = max_value

    response = HttpResponse(status=200)
    response['HX-Trigger'] = json.dumps(trigger_data)
    return response


def _get_score_entry_base_context(request, class_id, subject_id):
    """
    Shared helper to build base context for score entry views.

    Returns dict with common data needed by both table and student views:
    - class_obj, subject, current_term
    - students (filtered by enrollment if SHS)
    - assignments, categories
    - can_edit, grades_locked, editing_allowed

    This eliminates duplication between score_entry_form and score_entry_student.
    """
    current_term = Term.get_current()
    class_obj = get_object_or_404(Class, pk=class_id)
    subject = get_object_or_404(Subject, pk=subject_id)
    grades_locked = current_term.grades_locked if current_term else False

    # Check if user can edit scores for this subject/class
    can_edit = can_edit_scores(request.user, class_obj, subject)
    editing_allowed = can_edit and not grades_locked

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

    # Get categories (small table, usually cached)
    categories = list(AssessmentCategory.objects.filter(is_active=True).order_by('order'))

    return {
        'class_obj': class_obj,
        'subject': subject,
        'current_term': current_term,
        'students': students,
        'assignments': assignments,
        'categories': categories,
        'grades_locked': grades_locked,
        'can_edit': can_edit,
        'editing_allowed': editing_allowed,
    }


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
    # Get base context from shared helper (DRY)
    context = _get_score_entry_base_context(request, class_id, subject_id)
    students = context['students']
    assignments = context['assignments']

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

    # Check view mode preference (table or card)
    view_mode = request.GET.get('view', 'auto')  # auto, table, or card

    # Add view-specific context
    context['scores_dict'] = dict(scores_dict)  # Convert to regular dict for template
    context['view_mode'] = view_mode

    return render(request, 'gradebook/partials/score_form.html', context)


@login_required
@teacher_or_admin_required
def score_entry_student(request, class_id, subject_id, student_id):
    """Mobile-optimized score entry for a single student.

    Shows all assignments for one student in a vertical card layout,
    optimized for touch input on mobile devices.
    """
    # Get base context from shared helper (DRY)
    context = _get_score_entry_base_context(request, class_id, subject_id)
    students = context['students']
    assignments = context['assignments']
    class_obj = context['class_obj']

    # Get the specific student
    student = get_object_or_404(Student, pk=student_id, current_class=class_obj)

    # Find current student index for prev/next navigation
    current_index = next((i for i, s in enumerate(students) if s.id == student.id), 0)
    prev_student = students[current_index - 1] if current_index > 0 else None
    next_student = students[current_index + 1] if current_index < len(students) - 1 else None

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

    # Add student-view specific context
    context['student'] = student
    context['current_index'] = current_index
    context['prev_student'] = prev_student
    context['next_student'] = next_student
    context['assignments_by_category'] = dict(assignments_by_category)
    context['scores_dict'] = scores_dict

    return render(request, 'gradebook/partials/score_form_student.html', context)


@login_required
@teacher_or_admin_required
@ratelimit(key='user', rate='200/h')
def score_save(request):
    """
    Save scores via HTMX with audit logging and detailed validation feedback.

    Rate limited to 200 requests/hour per user.

    Returns detailed error information via HX-Trigger header so the frontend
    can display helpful feedback to teachers about validation issues.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    student_id = request.POST.get('student_id', '')
    assignment_id = request.POST.get('assignment_id', '')
    points = request.POST.get('points', '').strip()

    if not all([student_id, assignment_id]):
        return _build_error_response(
            message="Missing required data",
            student_id=student_id,
            assignment_id=assignment_id,
            error_code='missing_data',
            hint="Please refresh the page and try again"
        )

    # Fetch student and assignment
    try:
        student = Student.objects.select_related('current_class').get(pk=student_id)
    except Student.DoesNotExist:
        return _build_error_response(
            message="Student not found",
            student_id=student_id,
            assignment_id=assignment_id,
            error_code='student_not_found',
            hint="The student may have been removed"
        )

    try:
        assignment = Assignment.objects.select_related('term', 'subject').get(pk=assignment_id)
    except Assignment.DoesNotExist:
        return _build_error_response(
            message="Assignment not found",
            student_id=student_id,
            assignment_id=assignment_id,
            error_code='assignment_not_found',
            hint="The assignment may have been deleted"
        )

    # Early check for authorization (before transaction)
    if not can_edit_scores(request.user, student.current_class, assignment.subject):
        return _build_error_response(
            message="Not authorized to edit scores for this subject",
            student_id=student_id,
            assignment_id=assignment_id,
            error_code='unauthorized',
            hint="Contact your administrator if you need access"
        )

    # Get audit context
    client_ip = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]

    # Get existing score for reverting on error
    existing_score = Score.objects.filter(student=student, assignment=assignment).first()
    old_value = existing_score.points if existing_score else None
    old_value_str = str(old_value) if old_value is not None else ''
    max_points = assignment.points_possible

    # Handle empty value (deletion)
    if points == '':
        try:
            with transaction.atomic():
                # Re-check grade lock inside transaction with row lock
                term = Term.objects.select_for_update().get(pk=assignment.term_id)
                if term.grades_locked:
                    return _build_error_response(
                        message="Grades are locked for this term",
                        student_id=student_id,
                        assignment_id=assignment_id,
                        old_value=old_value_str,
                        error_code='grades_locked',
                        hint="Contact admin to unlock grades if needed"
                    )

                if existing_score:
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

            # Success - return 200 with no error trigger
            return HttpResponse(status=200)

        except Exception as e:
            logger.error(f"Error deleting score for student {student_id}, assignment {assignment_id}: {e}")
            return _build_error_response(
                message="Error removing score",
                student_id=student_id,
                assignment_id=assignment_id,
                old_value=old_value_str,
                error_code='delete_error',
                hint="Please try again"
            )

    # Validate the score using our utility
    points_decimal, validation_error = validate_score(
        value=points,
        max_points=max_points,
        allow_empty=False
    )

    if validation_error:
        return _build_error_response(
            message=validation_error.message,
            student_id=student_id,
            assignment_id=assignment_id,
            old_value=old_value_str,
            error_code=validation_error.error_code,
            hint=validation_error.hint,
            max_value=float(max_points)
        )

    # Save score with transaction handling and race condition protection
    try:
        with transaction.atomic():
            # Re-check grade lock inside transaction with row lock to prevent race condition
            term = Term.objects.select_for_update().get(pk=assignment.term_id)
            if term.grades_locked:
                return _build_error_response(
                    message="Grades are locked for this term",
                    student_id=student_id,
                    assignment_id=assignment_id,
                    old_value=old_value_str,
                    error_code='grades_locked',
                    hint="Contact admin to unlock grades if needed"
                )

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

        # Success response
        return HttpResponse(status=200)

    except Exception as e:
        logger.error(f"Error saving score for student {student_id}, assignment {assignment_id}: {e}")
        return _build_error_response(
            message="Error saving score",
            student_id=student_id,
            assignment_id=assignment_id,
            old_value=old_value_str,
            error_code='save_error',
            hint="Please try again. If the problem persists, contact support."
        )


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
    ).select_related('assessment_category')

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

def _get_assignments_context(subject, term):
    """Helper to build consistent context for assignments list."""
    from django.db.models import Count

    assigns = Assignment.objects.filter(
        subject=subject,
        term=term
    ).select_related('assessment_category').order_by('assessment_category__order', '-date', 'name')

    categories = AssessmentCategory.objects.filter(is_active=True).order_by('order')

    # Get assignment counts per category for this subject/term
    category_counts = dict(
        Assignment.objects.filter(
            subject=subject,
            term=term
        ).values('assessment_category').annotate(
            count=Count('id')
        ).values_list('assessment_category', 'count')
    )

    # Add count and next number to each category
    categories_with_counts = []
    for cat in categories:
        count = category_counts.get(cat.pk, 0)
        label = cat.short_name if len(cat.short_name) <= 6 else cat.name
        categories_with_counts.append({
            'obj': cat,
            'count': count,
            'next_name': f"{label} {count + 1}",
        })

    return {
        'subject': subject,
        'assignments': assigns,
        'categories': categories_with_counts,
        'current_term': term,
    }


@login_required
def assignments(request, subject_id):
    """List assignments for a subject in current term."""
    current_term = Term.get_current()
    subject = get_object_or_404(Subject, pk=subject_id)

    context = _get_assignments_context(subject, current_term)
    return render(request, 'gradebook/partials/assignments_list.html', context)


@login_required
def assignment_create(request):
    """Create a new assignment with auto-generated name based on category."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    current_term = Term.get_current()
    if not current_term:
        return HttpResponse('No current term set', status=400)

    subject_id = request.POST.get('subject_id')
    category_id = request.POST.get('category_id')
    date_str = request.POST.get('date', '').strip()
    points_possible = request.POST.get('points_possible', '100')

    if not all([subject_id, category_id, date_str]):
        return HttpResponse('Missing required fields', status=400)

    subject = get_object_or_404(Subject, pk=subject_id)
    category = get_object_or_404(AssessmentCategory, pk=category_id)

    # Parse date
    from datetime import datetime
    try:
        assignment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return HttpResponse('Invalid date format', status=400)

    # Auto-generate assignment name based on category
    # Count existing assignments in this category for this subject/term
    existing_count = Assignment.objects.filter(
        assessment_category=category,
        subject=subject,
        term=current_term
    ).count()

    # Generate name like "Quiz 1", "Quiz 2", "Project 1", etc.
    # Use short_name if it's a single word, otherwise use name
    category_label = category.short_name if len(category.short_name) <= 6 else category.name
    name = f"{category_label} {existing_count + 1}"

    Assignment.objects.create(
        assessment_category=category,
        subject=subject,
        term=current_term,
        name=name,
        points_possible=int(points_possible),
        date=assignment_date,
    )

    # Return updated assignments list
    context = _get_assignments_context(subject, current_term)
    response = render(request, 'gradebook/partials/assignments_list.html', context)
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
        date_str = request.POST.get('date', '').strip()

        if not name:
            return HttpResponse('Name is required', status=400)

        try:
            points = Decimal(points_possible)
            if points < 1:
                return HttpResponse('Points must be at least 1', status=400)
        except Exception:
            return HttpResponse('Invalid points value', status=400)

        # Parse date if provided
        if date_str:
            from datetime import datetime
            try:
                assignment.date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return HttpResponse('Invalid date format', status=400)

        # Update assignment
        assignment.name = name
        assignment.points_possible = points
        if category_id:
            category = get_object_or_404(AssessmentCategory, pk=category_id)
            assignment.assessment_category = category
        assignment.save()

        # Return updated assignments list
        context = _get_assignments_context(subject, current_term)
        response = render(request, 'gradebook/partials/assignments_list.html', context)
        response['HX-Trigger'] = '{"assignmentsChanged": {"subject_id": %d}}' % subject.pk
        return response

    # GET request - return edit form
    categories = AssessmentCategory.objects.filter(is_active=True).order_by('order')
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
    context = _get_assignments_context(subject, current_term)
    response = render(request, 'gradebook/partials/assignments_list.html', context)
    response['HX-Trigger'] = '{"assignmentsChanged": {"subject_id": %d}}' % subject.pk
    return response