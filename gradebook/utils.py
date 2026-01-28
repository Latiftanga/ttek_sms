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
from django.db.models import Count

from .models import Assignment, Score, AssessmentCategory
from academics.models import ClassSubject
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
    categories = AssessmentCategory.objects.filter(is_active=True).order_by('order')
    results = []

    for category in categories:
        status = category.get_assessment_status(subject, term)
        status['category'] = category
        status['weight_per_assignment'] = float(category.get_weight_per_assignment(subject, term))
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

def calculate_score_entry_progress(current_term):
    """Calculate the overall score entry progress for the current term."""
    if not current_term:
        return 0, 0, 0

    scores_entered = Score.objects.filter(assignment__term=current_term).count()
    
    term_assignments = Assignment.objects.filter(term=current_term).values_list('subject_id', flat=True)
    if not term_assignments:
        return scores_entered, 0, 0

    class_subject_data = ClassSubject.objects.filter(
        subject_id__in=term_assignments
    ).select_related('class_assigned').values(
        'subject_id', 'class_assigned_id'
    )

    subject_classes = {}
    for cs in class_subject_data:
        subject_classes.setdefault(cs['subject_id'], set()).add(cs['class_assigned_id'])

    class_student_counts = dict(
        Student.objects.filter(
            status='active',
            current_class__isnull=False
        ).values('current_class_id').annotate(
            count=Count('id')
        ).values_list('current_class_id', 'count')
    )

    subject_assignment_counts = dict(
        Assignment.objects.filter(
            term=current_term
        ).values('subject_id').annotate(
            count=Count('id')
        ).values_list('subject_id', 'count')
    )

    total_possible_scores = 0
    for subject_id, class_ids in subject_classes.items():
        assignment_count = subject_assignment_counts.get(subject_id, 0)
        for class_id in class_ids:
            student_count = class_student_counts.get(class_id, 0)
            total_possible_scores += assignment_count * student_count
    
    score_progress = round((scores_entered / total_possible_scores * 100) if total_possible_scores > 0 else 0, 1)

    return scores_entered, total_possible_scores, score_progress


def get_classes_needing_scores(current_term, classes):
    """Get a list of classes with incomplete score entries."""
    if not current_term:
        return []

    top_classes = classes[:6]
    top_class_ids = [c.id for c in top_classes]

    class_student_counts = dict(
        Student.objects.filter(
            status='active',
            current_class_id__in=top_class_ids
        ).values('current_class_id').annotate(
            count=Count('id')
        ).values_list('current_class_id', 'count')
    )

    class_subjects_map = {}
    for cs in ClassSubject.objects.filter(class_assigned_id__in=top_class_ids).values('class_assigned_id', 'subject_id'):
        class_subjects_map.setdefault(cs['class_assigned_id'], set()).add(cs['subject_id'])

    subject_assignment_counts = dict(
        Assignment.objects.filter(term=current_term).values('subject_id').annotate(
            count=Count('id')
        ).values_list('subject_id', 'count')
    )

    class_score_counts = dict(
        Score.objects.filter(
            assignment__term=current_term,
            student__current_class_id__in=top_class_ids
        ).values('student__current_class_id').annotate(
            count=Count('id')
        ).values_list('student__current_class_id', 'count')
    )

    classes_needing_scores = []
    for cls in top_classes:
        student_count = class_student_counts.get(cls.id, 0)
        if student_count > 0:
            class_subject_ids = class_subjects_map.get(cls.id, set())
            total_assignments = sum(
                subject_assignment_counts.get(subj_id, 0)
                for subj_id in class_subject_ids
            )
            if total_assignments > 0:
                expected_scores = total_assignments * student_count
                actual_scores = class_score_counts.get(cls.id, 0)
                progress = round((actual_scores / expected_scores * 100) if expected_scores > 0 else 0)
                classes_needing_scores.append({
                    'class': cls,
                    'student_count': student_count,
                    'progress': progress,
                    'assignments': total_assignments,
                })
    return classes_needing_scores


def check_transcript_permission(user, student):
    """
    Check if user has permission to view a student's transcript.

    Args:
        user: The requesting user
        student: The Student instance

    Returns:
        tuple: (has_permission: bool, error_message: str or None)
    """
    # Import here to avoid circular imports
    from .views import is_school_admin

    if is_school_admin(user):
        return True, None

    if getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile'):
        teacher = user.teacher_profile
        if student.current_class and student.current_class.class_teacher == teacher:
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

        if report.average:
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
    Get school and school settings for context.

    Args:
        include_logo_base64: If True, encode logo as base64 data URI for PDF

    Returns:
        dict: {'school': School or None, 'school_settings': SchoolSettings or None,
               'logo_base64': str or None (if include_logo_base64=True)}
    """
    school = None
    school_settings = None
    logo_base64 = None

    try:
        from schools.models import School
        from core.models import SchoolSettings

        schema_name = connection.schema_name
        school = School.objects.get(schema_name=schema_name)
        school_settings = SchoolSettings.objects.first()

        if include_logo_base64 and school_settings and school_settings.logo:
            logo_base64 = encode_logo_base64(school_settings.logo, schema_name)

    except Exception as e:
        logger.debug(f"Error getting school context: {e}")

    result = {
        'school': school,
        'school_settings': school_settings,
    }
    if include_logo_base64:
        result['logo_base64'] = logo_base64

    return result


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