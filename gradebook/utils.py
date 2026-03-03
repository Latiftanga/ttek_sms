"""
Utility functions for the gradebook app.
Extracted helpers to reduce code duplication.
"""
import base64
import os
import logging
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, List, Tuple, Any

from django.db import connection
from django.conf import settings as django_settings
from django.db.models import Count, F, Max

from .models import Assignment, Score, AssessmentCategory
from academics.models import ClassSubject, StudentSubjectEnrollment
from students.models import Student

logger = logging.getLogger(__name__)


# ============ Score Validation ============

class ScoreValidationError(Exception):
    """Raised when score validation fails. Provides detailed error info for UI feedback."""

    def __init__(
        self,
        message: str,
        error_code: str = 'invalid',
        field: str = 'points',
        max_value: Optional[Decimal] = None,
        hint: Optional[str] = None
    ):
        self.message = message
        self.error_code = error_code
        self.field = field
        self.max_value = max_value
        self.hint = hint or self._generate_hint()
        super().__init__(message)

    def _generate_hint(self) -> str:
        """Generate a helpful hint based on error type."""
        hints = {
            'required': 'Enter a score value',
            'invalid_number': 'Use digits only (e.g., 85 or 85.5)',
            'negative': 'Scores must be 0 or higher',
            'exceeds_max': f'Enter a value between 0 and {self.max_value}' if self.max_value else 'Value too high',
            'too_many_decimals': 'Use at most 2 decimal places (e.g., 85.75)',
        }
        return hints.get(self.error_code, '')

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        result = {
            'error': self.message,
            'code': self.error_code,
            'field': self.field,
            'hint': self.hint,
        }
        if self.max_value is not None:
            result['max_value'] = float(self.max_value)
        return result


def validate_score(
    value: Any,
    max_points: Decimal,
    allow_empty: bool = True
) -> Tuple[Optional[Decimal], Optional[ScoreValidationError]]:
    """
    Validate a score value with detailed error messages.

    Args:
        value: The score value to validate (can be string, number, or None)
        max_points: Maximum allowed points for this assignment
        allow_empty: Whether to allow empty/None values (for deletion)

    Returns:
        Tuple of (validated_decimal_value, error) where error is None if valid
    """
    # Handle empty values
    if value is None or (isinstance(value, str) and value.strip() == ''):
        if allow_empty:
            return None, None
        return None, ScoreValidationError(
            message="Score is required",
            error_code='required',
            max_value=max_points
        )

    # Convert to string for processing
    value_str = str(value).strip()

    # Try to parse as decimal
    try:
        points = Decimal(value_str)
    except (InvalidOperation, ValueError):
        return None, ScoreValidationError(
            message="Please enter a valid number",
            error_code='invalid_number',
            max_value=max_points
        )

    # Check for negative values
    if points < 0:
        return None, ScoreValidationError(
            message="Score cannot be negative",
            error_code='negative',
            max_value=max_points
        )

    # Check for exceeding maximum
    if points > max_points:
        return None, ScoreValidationError(
            message=f"Maximum score is {max_points:.0f}",
            error_code='exceeds_max',
            max_value=max_points
        )

    # Check for too many decimal places (max 2)
    if points.as_tuple().exponent < -2:
        return None, ScoreValidationError(
            message="Maximum 2 decimal places allowed",
            error_code='too_many_decimals',
            max_value=max_points
        )

    return points, None


# ============ Grade Calculation (Consolidated) ============

def calculate_category_scores(
    student_id: int,
    subject_id: int,
    categories: List[Any],
    assignments_by_subject_category: Dict[Tuple[int, int], List[Any]],
    scores_lookup: Dict[Tuple[int, int], Any]
) -> Dict[str, Any]:
    """
    Calculate scores by category for a student in a subject.

    This is the core calculation logic shared by models, signals, and views.

    Args:
        student_id: The student's ID
        subject_id: The subject's ID
        categories: List of AssessmentCategory objects
        assignments_by_subject_category: Dict mapping (subject_id, category_id) to assignments
        scores_lookup: Dict mapping (student_id, assignment_id) to Score objects

    Returns:
        Dictionary containing:
        - category_scores_json: JSON-serializable category breakdown
        - class_score: Decimal total for CLASS_SCORE type categories
        - exam_score: Decimal total for EXAM type categories
        - total_score: Decimal total across all categories
    """
    category_scores_json = {}
    total = Decimal('0.0')
    class_score_total = Decimal('0.0')
    exam_score_total = Decimal('0.0')

    for category in categories:
        cat_assignments = assignments_by_subject_category.get(
            (subject_id, category.id), []
        )

        if not cat_assignments:
            continue

        # Calculate weight per assignment
        assignment_count = len(cat_assignments)
        weight_per_assignment = Decimal(str(category.percentage)) / Decimal(str(assignment_count))
        category_total = Decimal('0.0')

        for assignment in cat_assignments:
            score = scores_lookup.get((student_id, assignment.id))

            if score and score.points is not None:
                score_pct = Decimal(str(score.points)) / Decimal(str(assignment.points_possible))
                category_total += score_pct * weight_per_assignment

        rounded_total = round(category_total, 2)

        # Store in JSON format for dynamic category support
        category_scores_json[str(category.pk)] = {
            'score': float(rounded_total),
            'short_name': category.short_name,
            'name': category.name,
            'percentage': category.percentage,
            'category_type': category.category_type,
            'order': category.order,
        }

        total += category_total

        # Aggregate by category type for legacy fields
        if category.category_type == 'CLASS_SCORE':
            class_score_total += category_total
        elif category.category_type == 'EXAM':
            exam_score_total += category_total

    return {
        'category_scores_json': category_scores_json,
        'class_score': round(class_score_total, 2),
        'exam_score': round(exam_score_total, 2),
        'total_score': round(total, 2),
    }


def determine_grade_from_scales(
    total_score: Optional[Decimal],
    grade_scales: List[Any]
) -> Dict[str, Any]:
    """
    Determine grade label and pass status from grade scales.

    Args:
        total_score: The total score percentage
        grade_scales: List of GradeScale objects (should be ordered by -min_percentage)

    Returns:
        Dictionary containing:
        - grade: The grade label (e.g., 'A1', 'B2')
        - grade_remark: The interpretation (e.g., 'Excellent')
        - is_passing: Boolean indicating if this is a passing grade
    """
    result = {
        'grade': '',
        'grade_remark': '',
        'is_passing': False,
    }

    if total_score is None:
        return result

    for scale in grade_scales:
        if scale.min_percentage <= total_score <= scale.max_percentage:
            result['grade'] = scale.grade_label
            result['grade_remark'] = scale.interpretation
            result['is_passing'] = scale.is_pass
            break

    return result


def build_assignments_lookup(
    assignments: List[Any]
) -> Dict[Tuple[int, int], List[Any]]:
    """
    Build lookup dictionary for assignments by (subject_id, category_id).

    Args:
        assignments: List of Assignment objects with assessment_category relation

    Returns:
        Dict mapping (subject_id, category_id) to list of assignments
    """
    lookup = defaultdict(list)
    for assignment in assignments:
        key = (assignment.subject_id, assignment.assessment_category_id)
        lookup[key].append(assignment)
    return dict(lookup)


def build_scores_lookup(
    scores: List[Any]
) -> Dict[Tuple[int, int], Any]:
    """
    Build lookup dictionary for scores by (student_id, assignment_id).

    Args:
        scores: List of Score objects

    Returns:
        Dict mapping (student_id, assignment_id) to Score object
    """
    return {
        (s.student_id, s.assignment_id): s for s in scores
    }


# ============ Assessment Status ============


def get_all_categories_assessment_status(subject, term):
    """
    Get assessment status for all active categories for a subject/term.

    Returns a list of dicts, each containing:
    - category: the AssessmentCategory instance
    - count: actual number of assessments
    - expected: recommended count
    - min: minimum required
    - max: maximum allowed
    - status: 'ok', 'below_min', 'above_max', 'below_expected', 'above_expected'
    - message: human-readable status message
    - weight_per_assignment: the weight each assignment carries
    """
    categories = list(AssessmentCategory.objects.filter(is_active=True).order_by('order'))

    # Single query: count assignments per category for this subject/term
    counts_qs = Assignment.objects.filter(
        assessment_category__in=categories,
        subject=subject,
        term=term,
    ).values('assessment_category_id').annotate(count=Count('id'))
    counts_by_cat = {row['assessment_category_id']: row['count'] for row in counts_qs}

    results = []
    for category in categories:
        count = counts_by_cat.get(category.id, 0)

        # Build status dict
        status = {
            'count': count,
            'expected': category.expected_assessments,
            'min': category.min_assessments,
            'max': category.max_assessments,
            'status': 'ok',
            'message': '',
            'category': category,
        }

        if category.min_assessments > 0 and count < category.min_assessments:
            status['status'] = 'below_min'
            status['message'] = f'Requires at least {category.min_assessments} assessment(s), has {count}'
        elif category.max_assessments > 0 and count > category.max_assessments:
            status['status'] = 'above_max'
            status['message'] = f'Maximum {category.max_assessments} assessment(s) allowed, has {count}'
        elif category.expected_assessments > 0:
            if count < category.expected_assessments:
                status['status'] = 'below_expected'
                status['message'] = f'Expected {category.expected_assessments}, has {count}'
            elif count > category.expected_assessments:
                status['status'] = 'above_expected'
                status['message'] = f'Expected {category.expected_assessments}, has {count}'

        # Weight per assignment
        if count > 0:
            status['weight_per_assignment'] = float(Decimal(str(category.percentage)) / Decimal(str(count)))
        else:
            status['weight_per_assignment'] = 0.0

        results.append(status)

    return results


def check_subject_assessment_completeness(subject, term):
    """
    Check if a subject has all required assessments for all categories.

    Returns:
    - is_complete: True if all categories meet minimum requirements
    - has_warnings: True if any category is below expected (but above minimum)
    - issues: list of issue messages (for categories below minimum)
    - warnings: list of warning messages (for categories below expected)
    """
    statuses = get_all_categories_assessment_status(subject, term)

    is_complete = True
    has_warnings = False
    issues = []
    warnings = []

    for status in statuses:
        if status['status'] == 'below_min':
            is_complete = False
            issues.append(f"{status['category'].name}: {status['message']}")
        elif status['status'] in ('below_expected', 'above_expected', 'above_max'):
            has_warnings = True
            warnings.append(f"{status['category'].name}: {status['message']}")

    return {
        'is_complete': is_complete,
        'has_warnings': has_warnings,
        'issues': issues,
        'warnings': warnings,
        'statuses': statuses,
    }

def _get_enrollment_counts(cs_ids):
    """
    Count students per ClassSubject, matching the score entry form logic exactly.

    The score entry form shows students who:
    1. Have an active StudentSubjectEnrollment for the ClassSubject, AND
    2. Still belong to that class (current_class matches class_assigned)

    Using F() to join student.current_class against class_subject.class_assigned
    ensures transferred students aren't counted against their old class.
    """
    if not cs_ids:
        return {}
    return dict(
        StudentSubjectEnrollment.objects.filter(
            class_subject_id__in=cs_ids,
            is_active=True,
            student__current_class_id=F('class_subject__class_assigned_id'),
        ).values('class_subject_id').annotate(
            count=Count('id')
        ).values_list('class_subject_id', 'count')
    )


def _get_class_student_counts(class_ids):
    """
    Count all students per class (fallback for classes without subject enrollments).

    Matches the score entry form's basic-school path which shows all students
    in the class with current_class=class_obj (no status filter).
    """
    if not class_ids:
        return {}
    return dict(
        Student.objects.filter(
            current_class_id__in=class_ids
        ).values('current_class_id').annotate(
            count=Count('id')
        ).values_list('current_class_id', 'count')
    )


def calculate_score_entry_progress(current_term):
    """Calculate the overall score entry progress for the current term."""
    if not current_term:
        return 0, 0, 0

    term_assignments = Assignment.objects.filter(term=current_term).values_list('subject_id', flat=True)
    if not term_assignments:
        return 0, 0, 0

    class_subject_data = list(
        ClassSubject.objects.filter(
            subject_id__in=term_assignments
        ).values('id', 'subject_id', 'class_assigned_id')
    )
    if not class_subject_data:
        return 0, 0, 0

    cs_ids = [cs['id'] for cs in class_subject_data]
    class_ids = list({cs['class_assigned_id'] for cs in class_subject_data})

    # Build a map of (class_id, subject_id) -> ClassSubject id
    cs_id_map = {
        (cs['class_assigned_id'], cs['subject_id']): cs['id']
        for cs in class_subject_data
    }

    subject_classes = {}
    for cs in class_subject_data:
        subject_classes.setdefault(cs['subject_id'], set()).add(cs['class_assigned_id'])

    enrollment_counts = _get_enrollment_counts(cs_ids)

    subject_assignment_counts = dict(
        Assignment.objects.filter(
            term=current_term
        ).values('subject_id').annotate(
            count=Count('id')
        ).values_list('subject_id', 'count')
    )

    # Build per-subject enrolled student IDs for per-subject score filtering.
    assigned_subject_ids = list({cs['subject_id'] for cs in class_subject_data})
    enrolled_ids_by_cs = {}
    if cs_ids:
        for row in StudentSubjectEnrollment.objects.filter(
            class_subject_id__in=cs_ids,
            is_active=True,
            student__current_class_id=F('class_subject__class_assigned_id'),
        ).values('class_subject_id', 'student_id'):
            enrolled_ids_by_cs.setdefault(row['class_subject_id'], set()).add(row['student_id'])

    # Count scores per (class, subject, student) for per-subject filtering
    raw_score_counts = Score.objects.filter(
        assignment__term=current_term,
        assignment__subject_id__in=assigned_subject_ids,
        student__current_class_id__in=class_ids,
    ).values(
        'student__current_class_id', 'assignment__subject_id', 'student_id'
    ).annotate(count=Count('id'))

    # Build lookup: {(class_id, subject_id): {student_id: count}}
    score_by_class_subject_student = {}
    for row in raw_score_counts:
        key = (row['student__current_class_id'], row['assignment__subject_id'])
        score_by_class_subject_student.setdefault(key, {})[row['student_id']] = row['count']

    total_possible_scores = 0
    scores_entered = 0
    for subject_id, class_ids_for_subj in subject_classes.items():
        assignment_count = subject_assignment_counts.get(subject_id, 0)
        for class_id in class_ids_for_subj:
            cs_id = cs_id_map.get((class_id, subject_id))
            enrolled = enrollment_counts.get(cs_id, 0) if cs_id else 0
            total_possible_scores += assignment_count * enrolled

            # Only count scores from enrolled students
            per_student = score_by_class_subject_student.get((class_id, subject_id), {})
            enrolled_ids = enrolled_ids_by_cs.get(cs_id, set()) if cs_id else set()
            scores_entered += sum(cnt for sid, cnt in per_student.items() if sid in enrolled_ids)

    score_progress = round((scores_entered / total_possible_scores * 100) if total_possible_scores > 0 else 0, 1)

    return scores_entered, total_possible_scores, score_progress


def get_classes_needing_scores(current_term, classes, limit=None):
    """Get a list of classes with incomplete score entries."""
    if not current_term:
        return []

    # Get all classes if no limit, otherwise respect the limit
    top_classes = list(classes[:limit]) if limit else list(classes)
    top_class_ids = [c.id for c in top_classes]

    class_student_counts = _get_class_student_counts(top_class_ids)

    # Map ClassSubject records per class: {class_id: {subject_id: cs_id}}
    class_subjects_map = {}
    all_cs_ids = []
    for cs in ClassSubject.objects.filter(class_assigned_id__in=top_class_ids).values('id', 'class_assigned_id', 'subject_id'):
        class_subjects_map.setdefault(cs['class_assigned_id'], {})[cs['subject_id']] = cs['id']
        all_cs_ids.append(cs['id'])

    enrollment_counts = _get_enrollment_counts(all_cs_ids)

    subject_assignment_counts = dict(
        Assignment.objects.filter(term=current_term).values('subject_id').annotate(
            count=Count('id')
        ).values_list('subject_id', 'count')
    )

    all_subject_ids = set()
    for subj_map in class_subjects_map.values():
        all_subject_ids.update(subj_map.keys())

    # Get enrolled student IDs per ClassSubject for per-subject score filtering.
    enrolled_ids_by_cs = {}
    if all_cs_ids:
        for row in StudentSubjectEnrollment.objects.filter(
            class_subject_id__in=all_cs_ids,
            is_active=True,
            student__current_class_id=F('class_subject__class_assigned_id'),
        ).values('class_subject_id', 'student_id'):
            enrolled_ids_by_cs.setdefault(row['class_subject_id'], set()).add(row['student_id'])

    # Count scores per (class, subject, student) for per-subject filtering.
    class_subject_student_scores = {}
    if all_subject_ids:
        for row in Score.objects.filter(
            assignment__term=current_term,
            assignment__subject_id__in=all_subject_ids,
            student__current_class_id__in=top_class_ids,
        ).values(
            'student__current_class_id', 'assignment__subject_id', 'student_id'
        ).annotate(count=Count('id')):
            class_id = row['student__current_class_id']
            subj_id = row['assignment__subject_id']
            if subj_id in class_subjects_map.get(class_id, {}):
                class_subject_student_scores.setdefault(
                    (class_id, subj_id), {}
                )[row['student_id']] = row['count']

    classes_needing_scores = []
    for cls in top_classes:
        all_class_students = class_student_counts.get(cls.id, 0)
        subject_cs_map = class_subjects_map.get(cls.id, {})
        total_assignments = 0
        expected_scores = 0
        actual_scores = 0

        # Collect unique enrolled students across all subjects in this class
        class_enrolled_ids = set()
        for subj_id, cs_id in subject_cs_map.items():
            class_enrolled_ids.update(enrolled_ids_by_cs.get(cs_id, set()))

            assign_count = subject_assignment_counts.get(subj_id, 0)
            if assign_count > 0:
                total_assignments += assign_count
                enrolled = enrollment_counts.get(cs_id, 0)
                expected_scores += assign_count * enrolled

                # Only count scores from enrolled students
                per_student = class_subject_student_scores.get((cls.id, subj_id), {})
                enrolled_ids = enrolled_ids_by_cs.get(cs_id, set()) if cs_id else set()
                actual_scores += sum(
                    cnt for sid, cnt in per_student.items() if sid in enrolled_ids
                )

        enrolled_count = len(class_enrolled_ids)
        unenrolled_count = all_class_students - enrolled_count if all_class_students > enrolled_count else 0

        if total_assignments > 0:
            progress = round((actual_scores / expected_scores * 100) if expected_scores > 0 else 0)
            classes_needing_scores.append({
                'class': cls,
                'student_count': enrolled_count,
                'total_in_class': all_class_students,
                'unenrolled_count': unenrolled_count,
                'progress': progress,
                'assignments': total_assignments,
                'expected_scores': expected_scores,
                'actual_scores': actual_scores,
                'remaining_scores': expected_scores - actual_scores,
            })
    return classes_needing_scores


def get_class_subject_progress(current_term, class_id):
    """Get per-subject score entry progress for a given class."""
    if not current_term:
        return []

    class_subjects = ClassSubject.objects.filter(
        class_assigned_id=class_id
    ).select_related('subject', 'teacher')

    if not class_subjects.exists():
        return []

    cs_ids = [cs.id for cs in class_subjects]
    subject_ids = [cs.subject_id for cs in class_subjects]

    enrollment_counts = _get_enrollment_counts(cs_ids)

    assignment_counts = dict(
        Assignment.objects.filter(
            term=current_term, subject_id__in=subject_ids
        ).values('subject_id').annotate(
            count=Count('id')
        ).values_list('subject_id', 'count')
    )

    # Get enrolled student IDs per subject for per-subject score filtering.
    enrolled_student_ids_by_subject = {}
    if cs_ids:
        for row in StudentSubjectEnrollment.objects.filter(
            class_subject_id__in=cs_ids,
            is_active=True,
            student__current_class_id=F('class_subject__class_assigned_id'),
        ).values('class_subject__subject_id', 'student_id'):
            enrolled_student_ids_by_subject.setdefault(
                row['class_subject__subject_id'], set()
            ).add(row['student_id'])

    # Count scores per (subject, student) for per-subject enrollment filtering.
    raw_score_qs = Score.objects.filter(
        assignment__term=current_term,
        assignment__subject_id__in=subject_ids,
        student__current_class_id=class_id,
    ).values('assignment__subject_id', 'student_id').annotate(
        count=Count('id'),
        last_activity=Max('updated_at'),
    )

    # Build per-subject score data: {subject_id: {student_id: {count, last_activity}}}
    subject_student_scores = {}
    for row in raw_score_qs:
        subj_id = row['assignment__subject_id']
        subject_student_scores.setdefault(subj_id, {})[row['student_id']] = {
            'count': row['count'],
            'last_activity': row['last_activity'],
        }

    results = []
    for cs in class_subjects:
        assignments = assignment_counts.get(cs.subject_id, 0)
        enrolled = enrollment_counts.get(cs.id, 0)
        expected = assignments * enrolled

        # Only count scores from enrolled students
        per_subject_scores = subject_student_scores.get(cs.subject_id, {})
        enrolled_ids = enrolled_student_ids_by_subject.get(cs.subject_id, set())
        actual = sum(s['count'] for sid, s in per_subject_scores.items() if sid in enrolled_ids)
        last_activity = max(
            (s['last_activity'] for sid, s in per_subject_scores.items() if sid in enrolled_ids and s['last_activity']),
            default=None,
        )

        progress = round((actual / expected * 100) if expected > 0 else 0)
        results.append({
            'subject': cs.subject,
            'teacher': cs.teacher,
            'assignments': assignments,
            'expected_scores': expected,
            'actual_scores': actual,
            'progress': progress,
            'remaining_scores': expected - actual,
            'last_activity': last_activity,
        })
    return results


def check_transcript_permission(user, student):
    """
    Check if user has permission to view a student's transcript.

    Args:
        user: The requesting user
        student: The Student instance

    Returns:
        tuple: (has_permission: bool, error_message: str or None)
    """
    from core.utils import is_school_admin

    if is_school_admin(user):
        return True, None

    if getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile') and user.teacher_profile:
        if student.current_class and student.current_class.class_teacher == user.teacher_profile:
            return True, None
        return False, 'You can only view transcripts for students in your homeroom class.'

    return False, 'You do not have permission to view this transcript.'


def get_transcript_data(student):
    """
    Fetch term reports and grades for a student's transcript.

    Args:
        student: The Student instance

    Returns:
        tuple: (term_reports queryset, all_grades queryset, grades_by_term dict)
    """
    from .models import TermReport, SubjectTermGrade

    # Get all term reports for the student, ordered by academic year and term
    term_reports = TermReport.objects.filter(
        student=student
    ).select_related(
        'term__academic_year', 'promoted_to'
    ).order_by('term__academic_year__start_date', 'term__term_number')

    # Get all subject grades
    all_grades = SubjectTermGrade.objects.filter(
        student=student
    ).select_related(
        'subject', 'term__academic_year'
    ).order_by(
        'term__academic_year__start_date',
        'term__term_number',
        '-subject__is_core',
        'subject__name'
    )

    # Group grades by term
    grades_by_term = {}
    for grade in all_grades:
        term_id = grade.term_id
        if term_id not in grades_by_term:
            grades_by_term[term_id] = []
        grades_by_term[term_id].append(grade)

    return term_reports, all_grades, grades_by_term


def build_academic_history(term_reports, grades_by_term, include_all_grades=False):
    """
    Build academic history and calculate cumulative statistics.

    Args:
        term_reports: Queryset of TermReport instances
        grades_by_term: Dictionary mapping term_id to list of grades
        include_all_grades: If True, include 'all_grades' key in each entry

    Returns:
        dict: {
            'academic_history': list of term data dicts,
            'cumulative_average': float,
            'term_count': int,
            'total_credits': int,
            'total_subjects_taken': int,
            'total_subjects_passed': int,
            'unique_subjects': set of subject names
        }
    """
    academic_history = []
    cumulative_score_sum = 0
    term_count = 0
    total_credits = 0
    total_subjects_taken = 0
    total_subjects_passed = 0
    unique_subjects = set()

    for report in term_reports:
        term_grades = grades_by_term.get(report.term_id, [])

        # Separate core and elective
        core_grades = [g for g in term_grades if g.subject.is_core]
        elective_grades = [g for g in term_grades if not g.subject.is_core]

        entry = {
            'report': report,
            'core_grades': core_grades,
            'elective_grades': elective_grades,
        }
        if include_all_grades:
            entry['all_grades'] = term_grades

        academic_history.append(entry)

        # Cumulative calculations
        total_subjects_taken += report.subjects_taken or 0
        total_subjects_passed += report.subjects_passed or 0
        total_credits += report.credits_count or 0

        if report.average is not None:
            cumulative_score_sum += float(report.average)
            term_count += 1

        # Track unique subjects
        for grade in term_grades:
            unique_subjects.add(grade.subject.name)

    cumulative_average = cumulative_score_sum / term_count if term_count > 0 else 0

    return {
        'academic_history': academic_history,
        'cumulative_average': round(cumulative_average, 2),
        'term_count': term_count,
        'total_credits': total_credits,
        'total_subjects_taken': total_subjects_taken,
        'total_subjects_passed': total_subjects_passed,
        'unique_subjects': unique_subjects,
    }


def get_school_context(include_logo_base64=False):
    """
    Get school context for templates and PDF generation.

    Uses connection.tenant (already loaded by django-tenants middleware)
    to avoid an extra database query.

    Args:
        include_logo_base64: If True, encode logo as base64 data URI for PDF

    Returns:
        dict: {'school': School or None,
               'logo_base64': str or None (if include_logo_base64=True)}
    """
    school = getattr(connection, 'tenant', None)
    logo_base64 = None

    try:
        if include_logo_base64 and school and school.logo:
            logo_base64 = encode_logo_base64(school.logo, connection.schema_name)
    except Exception as e:
        logger.debug(f"Error encoding logo: {e}")

    result = {
        'school': school,
    }
    if include_logo_base64:
        result['logo_base64'] = logo_base64

    return result


def encode_image_base64(image_field):
    """
    Encode any ImageField as a base64 data URI.

    Args:
        image_field: ImageField instance with a file

    Returns:
        str: Data URI string or None if encoding fails
    """
    try:
        if not image_field or not image_field.name:
            return None

        image_field.open('rb')
        image_data = image_field.read()
        image_field.close()

        encoded = base64.b64encode(image_data).decode('utf-8')

        ext = image_field.name.lower().rsplit('.', 1)[-1]
        mime_types = {
            'png': 'image/png',
            'gif': 'image/gif',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'webp': 'image/webp',
        }
        mime_type = mime_types.get(ext, 'image/jpeg')

        return f"data:{mime_type};base64,{encoded}"

    except Exception as e:
        logger.debug(f"Error encoding image as base64: {e}")
        return None


def encode_logo_base64(logo_field, schema_name):
    """
    Encode a logo image file as a base64 data URI.

    Args:
        logo_field: ImageField instance
        schema_name: Tenant schema name for path construction

    Returns:
        str: Data URI string or None if encoding fails
    """
    try:
        # Build path to logo file in tenant's media directory
        logo_path = os.path.join(
            django_settings.MEDIA_ROOT,
            'schools',
            schema_name,
            logo_field.name
        )

        if not os.path.exists(logo_path):
            logger.debug(f"Logo file not found at {logo_path}")
            return None

        with open(logo_path, 'rb') as f:
            logo_data = f.read()

        encoded = base64.b64encode(logo_data).decode('utf-8')

        # Detect image type from extension
        ext = logo_path.lower().split('.')[-1]
        mime_types = {
            'png': 'image/png',
            'gif': 'image/gif',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'webp': 'image/webp',
        }
        mime_type = mime_types.get(ext, 'image/jpeg')

        return f"data:{mime_type};base64,{encoded}"

    except Exception as e:
        logger.debug(f"Error encoding logo as base64: {e}")
        return None


# ============ Cached Queries ============

def get_active_categories():
    """
    Get active assessment categories with caching.
    Categories rarely change, so caching for 1 hour is safe.

    Returns:
        List of AssessmentCategory objects
    """
    from django.core.cache import cache

    from django.db import connection
    cache_key = f'assessment_categories_active_{connection.schema_name}'
    categories = cache.get(cache_key)

    if categories is None:
        categories = list(AssessmentCategory.objects.filter(is_active=True).order_by('order'))
        cache.set(cache_key, categories, 3600)  # Cache for 1 hour

    return categories


def invalidate_categories_cache():
    """Invalidate the categories cache when categories are modified."""
    from django.core.cache import cache
    from django.db import connection
    cache.delete(f'assessment_categories_active_{connection.schema_name}')