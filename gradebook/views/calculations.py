from collections import defaultdict
from decimal import Decimal
import logging
import json

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.db import IntegrityError, transaction

from .base import admin_required, htmx_render, is_school_admin
from ..models import (
    GradingSystem, AssessmentCategory, Assignment,
    Score, SubjectTermGrade, TermReport,
)
from ..signals import signals_disabled
from .. import config
from academics.models import Class, ClassSubject, StudentSubjectEnrollment
from students.models import Student
from core.models import Term

logger = logging.getLogger(__name__)


# ============ Grade Calculation ============

@login_required
@admin_required
def calculate_grades(request):
    """Calculate grades page - select class (Admin only)."""
    current_term = Term.get_current()
    classes = Class.objects.filter(is_active=True).order_by('level_number', 'name')
    grading_systems = GradingSystem.objects.filter(is_active=True)

    context = {
        'current_term': current_term,
        'classes': classes,
        'grading_systems': grading_systems,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook', 'url': '/gradebook/'},
            {'label': 'Calculate Grades'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/calculate.html',
        'gradebook/partials/calculate_content.html',
        context
    )


@login_required
@admin_required
def calculate_class_grades(request, class_id):
    """
    Calculate grades for all students in a class.
    Uses Ghana grading standards with configurable pass marks,
    WAEC aggregate calculation, and promotion eligibility checks.

    OPTIMIZED: Uses bulk prefetching and bulk_update to minimize queries.
    Before: ~3000+ queries for 40 students x 12 subjects
    After: ~20 queries total
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    current_term = Term.get_current()
    if not current_term:
        return HttpResponse('No current term set', status=400)

    class_obj = get_object_or_404(Class, pk=class_id)
    grading_system_id = request.POST.get('grading_system_id')
    if not grading_system_id:
        return HttpResponse('A grading system is required to calculate grades', status=400)
    grading_system = get_object_or_404(GradingSystem, pk=grading_system_id)

    # Check if this is the final term (Term 3) for promotion decisions
    is_final_term = current_term.term_number == 3 if hasattr(current_term, 'term_number') else False

    try:
        # Disable auto-calculation signals during bulk operation
        with signals_disabled(), transaction.atomic():
            # ========== PHASE 1: Bulk prefetch all data ==========

            # Get students
            students = list(Student.objects.filter(
                current_class=class_obj
            ).order_by('last_name', 'first_name'))

            if not students:
                return HttpResponse('No students in this class', status=400)

            student_ids = [s.id for s in students]

            # Get subjects for this class
            class_subjects = ClassSubject.objects.filter(
                class_assigned=class_obj
            ).select_related('subject')
            subjects = [cs.subject for cs in class_subjects]

            if not subjects:
                return HttpResponse('No subjects assigned to this class', status=400)

            subject_ids = [s.id for s in subjects]

            # Build student -> enrolled subjects map
            # This respects elective selections for SHS students
            student_subject_map = {}  # {student_id: set of subject_ids}

            # Check if this class uses subject enrollments (typically SHS)
            enrollments = StudentSubjectEnrollment.objects.filter(
                student_id__in=student_ids,
                class_subject__class_assigned=class_obj,
                is_active=True
            ).select_related('class_subject__subject')

            has_enrollments = enrollments.exists()

            if has_enrollments:
                # Use enrollments to determine which subjects each student takes
                for enrollment in enrollments:
                    sid = enrollment.student_id
                    subj_id = enrollment.class_subject.subject_id
                    if sid not in student_subject_map:
                        student_subject_map[sid] = set()
                    student_subject_map[sid].add(subj_id)

                logger.info(
                    f'Using subject enrollments for {class_obj.name}: '
                    f'{len(student_subject_map)} students with specific subjects'
                )
            else:
                # No enrollments - all students take all subjects (Basic school behavior)
                all_subject_ids = set(subject_ids)
                for student in students:
                    student_subject_map[student.id] = all_subject_ids

                logger.info(
                    f'No subject enrollments for {class_obj.name}: '
                    f'all students will be graded on all {len(subjects)} subjects'
                )

            # Prefetch all categories (small table, usually 2-3 rows)
            categories = list(AssessmentCategory.objects.filter(is_active=True))

            # Prefetch all assignments for these subjects in this term
            assignments = list(Assignment.objects.filter(
                subject_id__in=subject_ids,
                term=current_term
            ).select_related('assessment_category'))

            # Build assignment lookup: {(subject_id, category_id): [assignments]}
            assignments_by_subject_category = defaultdict(list)
            for assign in assignments:
                key = (assign.subject_id, assign.assessment_category_id)
                assignments_by_subject_category[key].append(assign)

            # Prefetch all scores for these students and assignments
            assignment_ids = [a.id for a in assignments]
            scores = Score.objects.filter(
                student_id__in=student_ids,
                assignment_id__in=assignment_ids
            ).select_related('assignment')

            # Build score lookup: {(student_id, assignment_id): score}
            scores_lookup = {
                (s.student_id, s.assignment_id): s for s in scores
            }

            # Prefetch grade scales for the grading system
            grade_scales = []
            if grading_system:
                grade_scales = list(grading_system.scales.all().order_by('-min_percentage'))

            # ========== PHASE 2: Calculate grades in memory ==========

            # Get or create SubjectTermGrade objects in bulk
            existing_grades = {
                (g.student_id, g.subject_id): g
                for g in SubjectTermGrade.objects.filter(
                    student_id__in=student_ids,
                    subject_id__in=subject_ids,
                    term=current_term
                )
            }

            grades_to_create = []
            grades_to_update = []

            for student in students:
                # Get subjects this student is enrolled in
                enrolled_subject_ids = student_subject_map.get(student.id, set())

                for subject in subjects:
                    # Skip if student is not enrolled in this subject
                    if subject.id not in enrolled_subject_ids:
                        continue

                    key = (student.id, subject.id)

                    if key in existing_grades:
                        grade = existing_grades[key]
                    else:
                        grade = SubjectTermGrade(
                            student=student,
                            subject=subject,
                            term=current_term
                        )
                        grades_to_create.append(grade)
                        existing_grades[key] = grade

            # Bulk create new grades
            if grades_to_create:
                SubjectTermGrade.objects.bulk_create(grades_to_create)
                # Refresh to get IDs
                for grade in grades_to_create:
                    existing_grades[(grade.student_id, grade.subject_id)] = grade

            # Calculate scores for each grade using prefetched data
            for student in students:
                # Get subjects this student is enrolled in
                enrolled_subject_ids = student_subject_map.get(student.id, set())

                for subject in subjects:
                    # Skip if student is not enrolled in this subject
                    if subject.id not in enrolled_subject_ids:
                        continue

                    grade = existing_grades.get((student.id, subject.id))
                    if not grade:
                        continue

                    # Calculate scores using prefetched data (no DB queries)
                    category_totals = {}
                    total = Decimal('0.0')

                    for category in categories:
                        cat_assignments = assignments_by_subject_category.get(
                            (subject.id, category.id), []
                        )

                        if not cat_assignments:
                            continue

                        # Calculate weight per assignment
                        weight_per_assignment = (
                            Decimal(str(category.percentage)) / Decimal(str(len(cat_assignments)))
                        )
                        category_total = Decimal('0.0')

                        for assign in cat_assignments:
                            score = scores_lookup.get((student.id, assign.id))
                            if score:
                                score_pct = Decimal(str(score.points)) / Decimal(str(assign.points_possible))
                                category_total += score_pct * weight_per_assignment

                        # Store by both short_name and category_type for flexibility
                        category_totals[category.short_name] = round(category_total, 2)
                        category_totals[f'_type_{category.category_type}'] = round(category_total, 2)
                        total += category_total

                    # Update grade object using category_type (with fallback to short_name)
                    grade.class_score = category_totals.get(
                        '_type_CLASS_SCORE', category_totals.get('CA', Decimal('0.0'))
                    )
                    grade.exam_score = category_totals.get(
                        '_type_EXAM', category_totals.get('EXAM', Decimal('0.0'))
                    )
                    grade.total_score = round(total, 2)
                    grade.category_scores = {
                        short_name: float(val)
                        for short_name, val in category_totals.items()
                        if not short_name.startswith('_type_')
                    }

                    # Determine grade from scale (no DB query - uses prefetched scales)
                    grade.is_passing = False  # Default to not passing
                    if grading_system and grade.total_score is not None:
                        for scale in grade_scales:
                            if scale.min_percentage <= grade.total_score <= scale.max_percentage:
                                grade.grade = scale.grade_label
                                grade.grade_remark = scale.interpretation
                                grade.is_passing = scale.is_pass
                                break

                    grades_to_update.append(grade)

            # Bulk update all grades
            SubjectTermGrade.objects.bulk_update(
                grades_to_update,
                ['class_score', 'exam_score', 'total_score', 'category_scores', 'grade', 'grade_remark', 'is_passing'],
                batch_size=config.BULK_UPDATE_BATCH_SIZE
            )

            # ========== PHASE 3: Calculate positions per subject ==========

            # Refresh grades for position calculation
            all_grades = list(SubjectTermGrade.objects.filter(
                student_id__in=student_ids,
                subject_id__in=subject_ids,
                term=current_term,
                total_score__isnull=False
            ).select_related('subject'))

            # Group by subject and calculate positions
            grades_by_subject = defaultdict(list)
            for grade in all_grades:
                grades_by_subject[grade.subject_id].append(grade)

            position_updates = []
            for subject_id, subject_grades in grades_by_subject.items():
                # Sort by total_score descending
                subject_grades.sort(key=lambda g: g.total_score or Decimal('0'), reverse=True)

                position = 0
                last_score = None
                for i, grade in enumerate(subject_grades, 1):
                    if grade.total_score != last_score:
                        position = i
                    grade.position = position
                    position_updates.append(grade)
                    last_score = grade.total_score

            # Bulk update positions
            SubjectTermGrade.objects.bulk_update(
                position_updates,
                ['position'],
                batch_size=config.BULK_UPDATE_BATCH_SIZE
            )

            # ========== PHASE 4: Calculate term reports ==========

            # Get or create TermReport objects
            existing_reports = {
                r.student_id: r
                for r in TermReport.objects.filter(
                    student_id__in=student_ids,
                    term=current_term
                )
            }

            reports_to_create = []
            for student in students:
                if student.id not in existing_reports:
                    report = TermReport(student=student, term=current_term)
                    reports_to_create.append(report)
                    existing_reports[student.id] = report

            if reports_to_create:
                TermReport.objects.bulk_create(reports_to_create)

            # Build grade lookup for aggregates
            grades_by_student = defaultdict(list)
            for grade in all_grades:
                grades_by_student[grade.student_id].append(grade)

            # Get subjects for core check
            subjects_dict = {s.id: s for s in subjects}

            # Calculate aggregates for each report
            reports_to_update = []

            for student in students:
                report = existing_reports[student.id]
                student_grades = grades_by_student.get(student.id, [])

                if student_grades:
                    total = sum(g.total_score for g in student_grades if g.total_score)
                    count = len([g for g in student_grades if g.total_score is not None])

                    report.total_marks = total
                    report.average = round(total / count, 2) if count > 0 else Decimal('0.0')
                    report.subjects_taken = count

                    # Count passed/failed using the is_passing flag set by grade scale
                    passed = [g for g in student_grades if g.is_passing]
                    report.subjects_passed = len(passed)
                    report.subjects_failed = count - len(passed)

                    # Count credits by looking up each score in grade scales
                    credits = 0
                    for g in student_grades:
                        if g.total_score is not None and grade_scales:
                            for scale in grade_scales:
                                if scale.min_percentage <= g.total_score <= scale.max_percentage:
                                    if scale.is_credit:
                                        credits += 1
                                    break
                    report.credits_count = credits

                    # Core subjects
                    core_grades = [
                        g for g in student_grades
                        if subjects_dict.get(g.subject_id) and subjects_dict[g.subject_id].is_core
                    ]
                    report.core_subjects_total = len(core_grades)
                    report.core_subjects_passed = len([
                        g for g in core_grades if g.is_passing
                    ])

                    # Calculate aggregate if grading system provided
                    if grading_system:
                        grade_points = []
                        for g in student_grades:
                            if g.total_score is not None:
                                for scale in grade_scales:
                                    if scale.min_percentage <= g.total_score <= scale.max_percentage:
                                        if scale.aggregate_points:
                                            grade_points.append(scale.aggregate_points)
                                        break

                        if grade_points:
                            grade_points.sort()
                            best_n = grade_points[:grading_system.aggregate_subjects_count]
                            report.aggregate = sum(best_n)

                report.out_of = len(students)

                # Calculate attendance from attendance records
                report.calculate_attendance()

                # Check promotion eligibility for final term
                if is_final_term and grading_system:
                    is_eligible, reasons = grading_system.check_promotion_eligibility(
                        report, core_grades=core_grades
                    )
                    report.promoted = is_eligible
                    report.promotion_remarks = '; '.join(reasons) if reasons else 'Meets all requirements'

                reports_to_update.append(report)

            # Bulk update reports
            TermReport.objects.bulk_update(
                reports_to_update,
                ['total_marks', 'average', 'subjects_taken', 'subjects_passed',
                 'subjects_failed', 'credits_count', 'core_subjects_total',
                 'core_subjects_passed', 'aggregate', 'out_of', 'promoted',
                 'promotion_remarks', 'days_present', 'days_absent',
                 'total_school_days', 'times_late', 'attendance_percentage',
                 'attendance_rating'],
                batch_size=config.BULK_UPDATE_BATCH_SIZE
            )

            # ========== PHASE 5: Calculate overall positions ==========

            # SHS uses aggregate (lower is better), Basic uses average (higher is better)
            if grading_system and grading_system.level == 'SHS':
                reports_to_update.sort(
                    key=lambda r: (r.aggregate is None, r.aggregate or 999, -(r.average or 0))
                )
            else:
                reports_to_update.sort(key=lambda r: -(r.average or 0))

            position = 0
            last_value = None
            for i, report in enumerate(reports_to_update, 1):
                if grading_system and grading_system.level == 'SHS':
                    current_value = report.aggregate
                else:
                    current_value = report.average

                if current_value != last_value:
                    position = i
                report.position = position
                last_value = current_value

            # Bulk update positions
            TermReport.objects.bulk_update(
                reports_to_update,
                ['position'],
                batch_size=config.BULK_UPDATE_BATCH_SIZE
            )

            logger.info(
                f'Calculated grades for {len(students)} students in {class_obj.name} '
                f'using {grading_system.name if grading_system else "default"} grading system'
            )

    except (ValueError, ValidationError, IntegrityError) as e:
        logger.error(f'Error calculating grades for class {class_id}: {str(e)}')
        return HttpResponse(f'Error: {str(e)}', status=500)

    # Return success HTML
    return HttpResponse(f'''
        <div class="alert alert-success mt-2">
            <i class="fa-solid fa-check-circle"></i>
            <div>
                <div class="font-bold">Grades Calculated Successfully!</div>
                <div class="text-sm">{len(students)} students in {class_obj.name} \
using {grading_system.name if grading_system else "default"} grading system</div>
            </div>
            <a href="/gradebook/reports/?class={class_id}" class="btn btn-sm btn-ghost">View Reports</a>
        </div>
    ''')


# ============ Grade Locking ============

@login_required
@admin_required
def toggle_grade_lock(request, term_id):
    """Toggle grade lock status for a term."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    term = get_object_or_404(Term, pk=term_id)

    if term.grades_locked:
        term.unlock_grades()
        message = f"Grades unlocked for {term.name}"
    else:
        term.lock_grades(request.user)
        message = f"Grades locked for {term.name}"

    response = HttpResponse(status=204)
    response['HX-Trigger'] = json.dumps({
        'showToast': {'message': message, 'type': 'success'},
        'refreshLockStatus': True
    })
    return response


@login_required
def grade_lock_status(request):
    """Get current term's lock status (for HTMX refresh)."""
    current_term = Term.get_current()
    return render(request, 'gradebook/partials/grade_lock_status.html', {
        'current_term': current_term,
        'is_admin': is_school_admin(request.user),
    })
