"""
Signals for automatic grade recalculation when scores change.

When a Score is saved or deleted, the corresponding SubjectTermGrade
is recalculated automatically.
"""
import logging
import threading
from decimal import Decimal

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import (
    Score, SubjectTermGrade, TermReport,
    AssessmentCategory, Assignment, GradingSystem
)

logger = logging.getLogger(__name__)

# Thread-local storage for signal disabling (thread-safe)
_thread_locals = threading.local()


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
    Supports multiple assessment categories with dynamic score storage.
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
        categories = AssessmentCategory.objects.filter(is_active=True).order_by('order')

        # Prefetch all assignments for this subject/term (single query)
        all_assignments = list(Assignment.objects.filter(
            subject=subject,
            term=term
        ).select_related('assessment_category'))

        # Get all assignment IDs for score lookup
        assignment_ids = [a.pk for a in all_assignments]

        # Prefetch all scores for this student and these assignments (single query)
        scores_by_assignment = {}
        if assignment_ids:
            student_scores = Score.objects.filter(
                student=student,
                assignment_id__in=assignment_ids
            )
            for score in student_scores:
                scores_by_assignment[score.assignment_id] = score

        # Group assignments by category
        assignments_by_category = {}
        for assignment in all_assignments:
            cat_id = assignment.assessment_category_id
            if cat_id not in assignments_by_category:
                assignments_by_category[cat_id] = []
            assignments_by_category[cat_id].append(assignment)

        # Calculate scores
        category_totals = {}
        category_scores_json = {}
        total = Decimal('0.0')
        class_score_total = Decimal('0.0')
        exam_score_total = Decimal('0.0')

        for category in categories:
            category_assignments = assignments_by_category.get(category.pk, [])

            if not category_assignments:
                continue

            # Calculate weight per assignment
            assignment_count = len(category_assignments)
            weight_per_assignment = Decimal(str(category.percentage)) / Decimal(str(assignment_count))
            category_total = Decimal('0.0')

            for assignment in category_assignments:
                score = scores_by_assignment.get(assignment.pk)

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

            # Store by short_name for backwards compatibility
            category_totals[category.short_name] = rounded_total
            total += category_total

            # Aggregate by category type for legacy fields
            if category.category_type == 'CLASS_SCORE':
                class_score_total += category_total
            elif category.category_type == 'EXAM':
                exam_score_total += category_total

        # Store dynamic category scores
        grade.category_scores = category_scores_json

        # Store legacy fields (aggregated by category_type)
        grade.class_score = round(class_score_total, 2)
        grade.exam_score = round(exam_score_total, 2)
        grade.total_score = round(total, 2)

        # Determine grade from grading system
        # Try to get appropriate grading system based on student's class level
        grading_system = None
        if student.current_class:
            level = 'SHS' if student.current_class.level_type == 'shs' else 'BASIC'
            grading_system = GradingSystem.objects.filter(
                level=level,
                is_active=True
            ).first()

        if not grading_system:
            grading_system = GradingSystem.objects.filter(is_active=True).first()

        grade.is_passing = False
        if grading_system and grade.total_score is not None:
            scale = grading_system.scales.filter(
                min_percentage__lte=grade.total_score,
                max_percentage__gte=grade.total_score
            ).first()

            if scale:
                grade.grade = scale.grade_label
                grade.grade_remark = scale.interpretation
                grade.is_passing = scale.is_pass

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
