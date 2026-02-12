"""
Signals for automatic grade recalculation when scores change.

When a Score is saved or deleted, the corresponding SubjectTermGrade
is recalculated automatically.
"""
import logging
import threading
from decimal import Decimal

from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import (
    Score, SubjectTermGrade, TermReport,
    AssessmentCategory, Assignment, GradingSystem
)
from .utils import (
    calculate_category_scores,
    determine_grade_from_scales,
    build_assignments_lookup,
    build_scores_lookup,
)

logger = logging.getLogger(__name__)

# Thread-local storage for signal disabling (thread-safe)
_thread_locals = threading.local()

# Cache timeout for grading system lookup (5 minutes)
GRADING_SYSTEM_CACHE_TIMEOUT = 300


def get_grading_system_cached(level):
    """
    Get grading system with caching to avoid repeated queries during rapid score entry.

    Args:
        level: 'SHS' or 'BASIC'

    Returns:
        GradingSystem instance or None
    """
    cache_key = f'grading_system_{level}'
    grading_system = cache.get(cache_key)

    if grading_system is None:
        grading_system = GradingSystem.objects.filter(
            level=level,
            is_active=True
        ).first()

        # Also try fallback if level-specific not found
        if not grading_system:
            grading_system = GradingSystem.objects.filter(is_active=True).first()
            cache_key = 'grading_system_fallback'

        # Cache the result (even if None, to avoid repeated queries)
        # Use a sentinel value for None since cache.get returns None for missing keys
        cache.set(cache_key, grading_system if grading_system else 'NONE', GRADING_SYSTEM_CACHE_TIMEOUT)
    elif grading_system == 'NONE':
        grading_system = None

    return grading_system


def get_grade_scales_cached(grading_system):
    """
    Get grade scales for a grading system with caching.

    Args:
        grading_system: GradingSystem instance

    Returns:
        List of GradeScale objects ordered by -min_percentage
    """
    if not grading_system:
        return []

    cache_key = f'grade_scales_{grading_system.pk}'
    grade_scales = cache.get(cache_key)

    if grade_scales is None:
        grade_scales = list(grading_system.scales.all().order_by('-min_percentage'))
        cache.set(cache_key, grade_scales, GRADING_SYSTEM_CACHE_TIMEOUT)

    return grade_scales


def _is_signals_disabled():
    """Check if signals are disabled for the current thread."""
    return getattr(_thread_locals, 'signals_disabled', False)


def disable_signals():
    """Disable auto-calculation signals for the current thread (for bulk operations)."""
    _thread_locals.signals_disabled = True


def enable_signals():
    """Re-enable auto-calculation signals for the current thread."""
    _thread_locals.signals_disabled = False


class signals_disabled:
    """Context manager to temporarily disable signals (thread-safe)."""

    def __enter__(self):
        self._previous_state = _is_signals_disabled()
        disable_signals()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._previous_state:
            enable_signals()
        return False


def recalculate_subject_grade(student, subject, term):
    """
    Recalculate SubjectTermGrade for a student/subject/term.

    This is called when a score changes to update the aggregated grade.
    Uses the consolidated calculate_category_scores utility to avoid duplication.
    """
    if _is_signals_disabled():
        return

    try:
        # Get or create the SubjectTermGrade
        grade, created = SubjectTermGrade.objects.get_or_create(
            student=student,
            subject=subject,
            term=term
        )

        # Get active categories ordered by display order
        categories = list(AssessmentCategory.objects.filter(is_active=True).order_by('order'))

        # Prefetch all assignments for this subject/term (single query)
        all_assignments = list(Assignment.objects.filter(
            subject=subject,
            term=term
        ).select_related('assessment_category'))

        # Build lookups using shared utilities
        assignments_lookup = build_assignments_lookup(all_assignments)

        # Prefetch all scores for this student
        assignment_ids = [a.pk for a in all_assignments]
        scores = []
        if assignment_ids:
            scores = list(Score.objects.filter(
                student=student,
                assignment_id__in=assignment_ids
            ))
        scores_lookup = build_scores_lookup(scores)

        # Use consolidated calculation utility
        calc_result = calculate_category_scores(
            student_id=student.id,
            subject_id=subject.id,
            categories=categories,
            assignments_by_subject_category=assignments_lookup,
            scores_lookup=scores_lookup
        )

        # Apply results to grade object
        grade.category_scores = calc_result['category_scores_json']
        grade.class_score = calc_result['class_score']
        grade.exam_score = calc_result['exam_score']
        grade.total_score = calc_result['total_score']

        # Determine grade from grading system (cached lookup for efficiency)
        grading_system = None
        if student.current_class:
            level = 'SHS' if student.current_class.level_type == 'shs' else 'BASIC'
            grading_system = get_grading_system_cached(level)
        else:
            grading_system = get_grading_system_cached('BASIC')

        # Use consolidated grade lookup utility (with cached grade scales)
        grade.is_passing = False
        if grading_system and grade.total_score is not None:
            grade_scales = get_grade_scales_cached(grading_system)
            grade_info = determine_grade_from_scales(grade.total_score, grade_scales)
            grade.grade = grade_info['grade']
            grade.grade_remark = grade_info['grade_remark']
            grade.is_passing = grade_info['is_passing']

        grade.save()

        logger.debug(
            f"Recalculated grade for {student} in {subject.name}: "
            f"{grade.total_score}% ({grade.grade})"
        )

        return grade

    except Exception as e:
        logger.error(f"Error recalculating grade: {e}")
        return None


def recalculate_term_report(student, term):
    """
    Recalculate TermReport for a student/term.

    This updates the overall term statistics based on SubjectTermGrades.
    """
    if _is_signals_disabled():
        return

    try:
        # Get all subject grades for this student/term
        subject_grades = SubjectTermGrade.objects.filter(
            student=student,
            term=term,
            total_score__isnull=False
        )

        if not subject_grades.exists():
            return None

        # Get or create term report
        report, created = TermReport.objects.get_or_create(
            student=student,
            term=term
        )

        # Calculate aggregates
        total_marks = Decimal('0.0')
        subjects_taken = 0
        subjects_passed = 0

        for grade in subject_grades:
            if grade.total_score is not None:
                total_marks += grade.total_score
                subjects_taken += 1
                if grade.is_passing:
                    subjects_passed += 1

        report.total_marks = total_marks
        report.subjects_taken = subjects_taken
        report.subjects_passed = subjects_passed
        report.subjects_failed = subjects_taken - subjects_passed
        report.average = round(total_marks / subjects_taken, 2) if subjects_taken > 0 else Decimal('0.0')

        report.save()

        logger.debug(
            f"Recalculated term report for {student}: "
            f"avg={report.average}%, passed={subjects_passed}/{subjects_taken}"
        )

        return report

    except Exception as e:
        logger.error(f"Error recalculating term report: {e}")
        return None


@receiver(post_save, sender=Score)
def score_saved(sender, instance, created, **kwargs):
    """Recalculate grades when a score is saved."""
    if _is_signals_disabled():
        return

    assignment = instance.assignment
    student = instance.student

    # Recalculate subject grade
    recalculate_subject_grade(
        student=student,
        subject=assignment.subject,
        term=assignment.term
    )

    # Recalculate term report
    recalculate_term_report(
        student=student,
        term=assignment.term
    )


@receiver(post_delete, sender=Score)
def score_deleted(sender, instance, **kwargs):
    """Recalculate grades when a score is deleted."""
    if _is_signals_disabled():
        return

    assignment = instance.assignment
    student = instance.student

    # Recalculate subject grade
    recalculate_subject_grade(
        student=student,
        subject=assignment.subject,
        term=assignment.term
    )

    # Recalculate term report
    recalculate_term_report(
        student=student,
        term=assignment.term
    )


# ============ Cache Invalidation Signals ============

@receiver(post_save, sender=AssessmentCategory)
@receiver(post_delete, sender=AssessmentCategory)
def invalidate_categories_cache(sender, instance, **kwargs):
    """Invalidate categories cache when categories are modified."""
    from .utils import invalidate_categories_cache as clear_cache
    clear_cache()
    logger.debug(f"Categories cache invalidated due to {sender.__name__} change")
