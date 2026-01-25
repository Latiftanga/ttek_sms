"""
Utility functions for the gradebook app.
Extracted helpers to reduce code duplication.
"""
import base64
import os
import logging

from django.db import connection
from django.conf import settings as django_settings
from django.db.models import Count

from .models import Assignment, Score, AssessmentCategory
from academics.models import ClassSubject
from students.models import Student

logger = logging.getLogger(__name__)


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