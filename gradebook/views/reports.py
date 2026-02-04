from collections import defaultdict, Counter
from decimal import Decimal
import logging
import json
from django.utils import timezone

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.db.models import Avg, Count, Q
from django.db import connection, transaction
from django.contrib import messages
from django.core.paginator import Paginator

from .base import (
    admin_required, htmx_render, is_school_admin, teacher_or_admin_required
)
from ..models import (
    GradingSystem, AssessmentCategory, Assignment,
    Score, SubjectTermGrade, TermReport, RemarkTemplate,
    ReportDistributionLog
)
from ..signals import signals_disabled
from .. import config
from ..utils import (
    check_transcript_permission,
    get_transcript_data,
    build_academic_history,
    get_school_context,
)
from academics.models import Class, ClassSubject, StudentSubjectEnrollment
from students.models import Student, Enrollment
from core.models import Term, SchoolSettings
from schools.models import School

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
    grading_system = get_object_or_404(GradingSystem, pk=grading_system_id) if grading_system_id else None

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
                    grade.class_score = category_totals.get('_type_CLASS_SCORE', category_totals.get('CA', Decimal('0.0')))
                    grade.exam_score = category_totals.get('_type_EXAM', category_totals.get('EXAM', Decimal('0.0')))
                    grade.total_score = round(total, 2)

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
                ['class_score', 'exam_score', 'total_score', 'grade', 'grade_remark', 'is_passing'],
                batch_size=config.BULK_UPDATE_BATCH_SIZE
            )

            # ========== PHASE 3: Calculate positions per subject ========== 

            # Refresh grades for position calculation
            all_grades = list(SubjectTermGrade.objects.filter(
                student_id__in=student_ids,
                subject_id__in=subject_ids,
                term=current_term,
                total_score__isnull=False
            ))

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
            pass_mark = grading_system.pass_mark if grading_system else config.DEFAULT_PASS_MARK
            credit_mark = grading_system.credit_mark if grading_system else config.DEFAULT_CREDIT_MARK

            for student in students:
                report = existing_reports[student.id]
                student_grades = grades_by_student.get(student.id, [])

                if student_grades:
                    total = sum(g.total_score for g in student_grades if g.total_score)
                    count = len([g for g in student_grades if g.total_score is not None])

                    report.total_marks = total
                    report.average = round(total / count, 2) if count > 0 else Decimal('0.0')
                    report.subjects_taken = count

                    # Count passed/failed
                    passed = [g for g in student_grades if g.total_score and g.total_score >= pass_mark]
                    report.subjects_passed = len(passed)
                    report.subjects_failed = count - len(passed)

                    # Count credits
                    report.credits_count = len([
                        g for g in student_grades if g.total_score and g.total_score >= credit_mark
                    ])

                    # Core subjects
                    core_grades = [
                        g for g in student_grades
                        if subjects_dict.get(g.subject_id) and subjects_dict[g.subject_id].is_core
                    ]
                    report.core_subjects_total = len(core_grades)
                    report.core_subjects_passed = len([
                        g for g in core_grades if g.total_score and g.total_score >= pass_mark
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

                # Check promotion eligibility for final term
                if is_final_term and grading_system:
                    is_eligible, reasons = grading_system.check_promotion_eligibility(report)
                    report.promoted = is_eligible
                    report.promotion_remarks = '; '.join(reasons) if reasons else 'Meets all requirements'

                reports_to_update.append(report)

            # Bulk update reports
            TermReport.objects.bulk_update(
                reports_to_update,
                ['total_marks', 'average', 'subjects_taken', 'subjects_passed',
                 'subjects_failed', 'credits_count', 'core_subjects_total',
                 'core_subjects_passed', 'aggregate', 'out_of', 'promoted',
                 'promotion_remarks'],
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

    except Exception as e:
        logger.error(f'Error calculating grades for class {class_id}: {str(e)}')
        return HttpResponse(f'Error: {str(e)}', status=500)

    # Return success HTML
    return HttpResponse(f'''
        <div class="alert alert-success mt-2">
            <i class="fa-solid fa-check-circle"></i>
            <div>
                <div class="font-bold">Grades Calculated Successfully!</div>
                <div class="text-sm">{len(students)} students in {class_obj.name} using {grading_system.name if grading_system else "default"} grading system</div>
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
    response['HX-Trigger'] = f'{{"showToast": {{"message": "{message}", "type": "success"}}, "refreshLockStatus": true}}'
    return response


@login_required
def grade_lock_status(request):
    """Get current term's lock status (for HTMX refresh)."""
    current_term = Term.get_current()
    return render(request, 'gradebook/partials/grade_lock_status.html', {
        'current_term': current_term,
        'is_admin': is_school_admin(request.user),
    })


# ============ Report Cards ============ 

@login_required
def report_cards(request):
    """Report cards page - select class/term.

    OPTIMIZED: Uses dict lookup for O(1) report access per student.

    For teachers: Only show classes where they are the form master (class_teacher).
    For admins: Show all classes. Admins can also filter by student status to view
    transcripts for past students (graduated, withdrawn, etc.).
    """
    current_term = Term.get_current()
    user = request.user
    is_admin = is_school_admin(user)

    # Filter classes based on user role
    if is_admin:
        # Admins see all classes
        classes = Class.objects.filter(is_active=True).only(
            'id', 'name', 'level_number'
        ).order_by('level_number', 'name')
    elif getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile'):
        # Teachers only see classes where they are the form master
        teacher = user.teacher_profile
        classes = Class.objects.filter(
            class_teacher=teacher,
            is_active=True
        ).only(
            'id', 'name', 'level_number'
        ).order_by('level_number', 'name')
    else:
        classes = Class.objects.none()

    # Get filters
    class_id = request.GET.get('class')
    status_filter = request.GET.get('status', 'active')  # Default to active
    students = []
    class_obj = None

    if class_id:
        class_obj = get_object_or_404(Class, pk=class_id)

        # Verify teacher has permission to view this class
        if not is_admin:
            if getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile'):
                teacher = user.teacher_profile
                if class_obj.class_teacher != teacher:
                    messages.error(request, 'You can only view reports for classes you are the form master of.')
                    return redirect('gradebook:reports')
            else:
                messages.error(request, 'You do not have permission to view reports.')
                return redirect('core:index')

        if status_filter == 'active':
            # Active students: filter by current_class (existing behavior)
            students = list(Student.objects.filter(
                current_class=class_obj
            ).only(
                'id', 'first_name', 'last_name', 'admission_number', 'status'
            ).order_by('last_name', 'first_name'))
        elif is_admin:
            # Non-active students (graduated, etc.): find via enrollment history
            # Get student IDs who were enrolled in this class with the selected status
            student_ids = Enrollment.objects.filter(
                class_assigned=class_obj,
                student__status=status_filter
            ).values_list('student_id', flat=True).distinct()

            students = list(Student.objects.filter(
                pk__in=student_ids,
                status=status_filter
            ).only(
                'id', 'first_name', 'last_name', 'admission_number', 'status'
            ).order_by('last_name', 'first_name'))

        if students:
            # Get term reports in single query - O(1) lookup per student
            student_ids = [s.id for s in students]
            reports = {
                r.student_id: r
                for r in TermReport.objects.filter(
                    student_id__in=student_ids,
                    term=current_term
                ).only(
                    'id', 'student_id', 'average', 'position', 'out_of',
                    'subjects_passed', 'subjects_failed', 'aggregate'
                )
            }
            for s in students:
                s.term_report = reports.get(s.id)

    context = {
        'current_term': current_term,
        'classes': classes,
        'selected_class': class_obj,
        'students': students,
        'is_admin': is_admin,
        'status_choices': Student.Status.choices if is_admin else [],
        'status_filter': status_filter,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook', 'url': '/gradebook/'},
            {'label': 'Report Cards'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/reports.html',
        'gradebook/partials/reports_content.html',
        context
    )


@login_required
def student_report(request, student_id):
    """View individual student report card with Ghana-specific data.

    OPTIMIZED: Uses select_related and computes grade summary in-memory.

    For teachers: Only allow viewing reports for students in their homeroom classes.
    For admins: Allow viewing all reports.
    """
    current_term = Term.get_current()
    student = get_object_or_404(Student.objects.select_related('current_class'), pk=student_id)
    user = request.user

    # Permission check for teachers
    if not is_school_admin(user):
        if getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile'):
            teacher = user.teacher_profile
            # Teacher must be the form master of the student's class
            if not student.current_class or student.current_class.class_teacher != teacher:
                messages.error(request, 'You can only view reports for students in your homeroom class.')
                return redirect('gradebook:reports')
        else:
            messages.error(request, 'You do not have permission to view this report.')
            return redirect('core:index')

    # Get subject grades - single query
    subject_grades = list(SubjectTermGrade.objects.filter(
        student=student,
        term=current_term
    ).select_related('subject').order_by('-subject__is_core', 'subject__name'))

    # Check school's education system to determine if we should show core/elective separation
    # Only SHS schools (or schools with SHS levels) have elective subjects
    school_ctx = get_school_context()
    school = school_ctx.get('school')
    is_shs_class = student.current_class and student.current_class.level_type == 'shs'

    # Show core/elective only for SHS-only schools, or for SHS classes in mixed schools
    if school:
        show_core_elective = school.education_system == 'shs' or (school.has_shs_levels and is_shs_class)
    else:
        show_core_elective = is_shs_class

    if show_core_elective:
        core_grades = [sg for sg in subject_grades if sg.subject.is_core]
        elective_grades = [sg for sg in subject_grades if not sg.subject.is_core]
    else:
        # For Basic-only schools, don't separate - show all subjects together
        core_grades = []
        elective_grades = []

    # Get term report
    term_report = TermReport.objects.filter(
        student=student,
        term=current_term
    ).first()

    # Compute grade summary in memory (no extra query)
    grade_summary = dict(Counter(
        sg.grade for sg in subject_grades if sg.grade
    ))

    # Get categories (small table)
    categories = list(AssessmentCategory.objects.filter(is_active=True).order_by('order'))

    # Get grading system with scales prefetched
    grading_system = GradingSystem.objects.filter(
        is_active=True
    ).prefetch_related('scales').first()

    context = {
        'student': student,
        'current_term': current_term,
        'subject_grades': subject_grades,
        'core_grades': core_grades,
        'elective_grades': elective_grades,
        'term_report': term_report,
        'grade_summary': grade_summary,
        'categories': categories,
        'grading_system': grading_system,
        'is_shs': show_core_elective,
    }

    return render(request, 'gradebook/partials/report_card.html', context)


@login_required
def report_remarks_edit(request, student_id):
    """Edit teacher remarks for a student's term report."""
    current_term = Term.get_current()
    student = get_object_or_404(Student, pk=student_id)

    if not current_term:
        return HttpResponse('No current term set', status=400)

    # Get or create term report
    term_report, created = TermReport.objects.get_or_create(
        student=student,
        term=current_term,
        defaults={'out_of': 1}
    )

    if request.method == 'GET':
        # Check if user can edit remarks
        can_edit_class_remark = False
        can_edit_head_remark = False

        # Class teacher can edit class teacher remark
        if hasattr(request.user, 'teacher_profile') and request.user.teacher_profile:
            teacher = request.user.teacher_profile
            # Check if teacher is class teacher for this student's class
            if student.current_class and student.current_class.class_teacher == teacher:
                can_edit_class_remark = True

        # School admin can edit both
        if is_school_admin(request.user):
            can_edit_class_remark = True
            can_edit_head_remark = True

        return render(request, 'gradebook/partials/remarks_edit.html', {
            'student': student,
            'term_report': term_report,
            'current_term': current_term,
            'can_edit_class_remark': can_edit_class_remark,
            'can_edit_head_remark': can_edit_head_remark,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    # Save remarks
    remark_type = request.POST.get('remark_type')
    remark_text = request.POST.get('remark', '').strip()

    if remark_type == 'class_teacher':
        # Verify permission
        can_edit = is_school_admin(request.user)
        if not can_edit and hasattr(request.user, 'teacher_profile') and request.user.teacher_profile:
            if student.current_class and student.current_class.class_teacher == request.user.teacher_profile:
                can_edit = True

        if can_edit:
            term_report.class_teacher_remark = remark_text
            term_report.save(update_fields=['class_teacher_remark'])

    elif remark_type == 'head_teacher':
        if is_school_admin(request.user):
            term_report.head_teacher_remark = remark_text
            term_report.save(update_fields=['head_teacher_remark'])

    response = HttpResponse(status=204)
    response['HX-Trigger'] = '{"showToast": {"message": "Remark saved successfully", "type": "success"}, "closeModal": true}'
    return response


@login_required
def report_card_print(request, student_id):
    """Print-friendly report card with Ghana-specific data.

    OPTIMIZED: Uses select_related and computes grade summary in-memory.

    For teachers: Only allow printing reports for students in their homeroom classes.
    For admins: Allow printing all reports.
    """
    current_term = Term.get_current()
    student = get_object_or_404(Student.objects.select_related('current_class'), pk=student_id)
    user = request.user

    # Permission check for teachers
    if not is_school_admin(user):
        if getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile'):
            teacher = user.teacher_profile
            # Teacher must be the form master of the student's class
            if not student.current_class or student.current_class.class_teacher != teacher:
                messages.error(request, 'You can only print reports for students in your homeroom class.')
                return redirect('gradebook:reports')
        else:
            messages.error(request, 'You do not have permission to print this report.')
            return redirect('core:index')

    # Get subject grades - single query
    subject_grades = list(SubjectTermGrade.objects.filter(
        student=student,
        term=current_term
    ).select_related('subject').order_by('-subject__is_core', 'subject__name'))

    # Check school's education system to determine if we should show core/elective separation
    # Only SHS schools (or schools with SHS levels) have elective subjects
    school_ctx = get_school_context()
    school_obj = school_ctx.get('school')
    is_shs_class = student.current_class and student.current_class.level_type == 'shs'

    # Show core/elective only for SHS-only schools, or for SHS classes in mixed schools
    if school_obj:
        show_core_elective = school_obj.education_system == 'shs' or (school_obj.has_shs_levels and is_shs_class)
    else:
        show_core_elective = is_shs_class

    if show_core_elective:
        core_grades = [sg for sg in subject_grades if sg.subject.is_core]
        elective_grades = [sg for sg in subject_grades if not sg.subject.is_core]
    else:
        # For Basic-only schools, don't separate - show all subjects together
        core_grades = []
        elective_grades = []

    term_report = TermReport.objects.filter(
        student=student,
        term=current_term
    ).first()

    # Compute grade summary in memory (no extra query)
    grade_summary = dict(Counter(
        sg.grade for sg in subject_grades if sg.grade
    ))

    categories = list(AssessmentCategory.objects.filter(is_active=True).order_by('order'))

    # Calculate category-wise scores for each subject
    # Get all scores for this student in current term, grouped by subject and category
    category_scores = {}
    scores_qs = Score.objects.filter(
        student=student,
        assignment__term=current_term
    ).select_related('assignment__subject', 'assignment__assessment_category')

    for score in scores_qs:
        subject_id = score.assignment.subject_id
        category_id = score.assignment.assessment_category_id

        if subject_id not in category_scores:
            category_scores[subject_id] = {}
        if category_id not in category_scores[subject_id]:
            category_scores[subject_id][category_id] = {'earned': 0, 'possible': 0}

        category_scores[subject_id][category_id]['earned'] += float(score.points)
        category_scores[subject_id][category_id]['possible'] += float(score.assignment.points_possible)

    # Attach category scores to each subject grade
    for sg in subject_grades:
        sg.category_scores = {}
        subject_cat_scores = category_scores.get(sg.subject_id, {})
        for cat in categories:
            cat_data = subject_cat_scores.get(cat.pk, {'earned': 0, 'possible': 0})
            if cat_data['possible'] > 0:
                # Calculate percentage and apply category weight
                percentage = (cat_data['earned'] / cat_data['possible']) * 100
                weighted = (percentage * cat.percentage) / 100
                sg.category_scores[cat.pk] = round(weighted, 1)
            else:
                sg.category_scores[cat.pk] = None

    # Get grading system with scales for the grade key
    grading_system = GradingSystem.objects.filter(
        is_active=True
    ).prefetch_related('scales').first()

    # Get school/tenant info
    school = None
    school_settings = None
    try:
        from django.db import connection
        school = School.objects.get(schema_name=connection.schema_name)
        school_settings = SchoolSettings.objects.first()
    except Exception:
        pass

    # Create verification record and generate QR code
    verification = None
    qr_code_base64 = None
    try:
        from core.models import DocumentVerification
        from core.utils import generate_verification_qr

        verification = DocumentVerification.create_for_document(
            document_type=DocumentVerification.DocumentType.REPORT_CARD,
            student=student,
            title=f"Report Card - {current_term.name}" if current_term else "Report Card",
            user=request.user,
            term=current_term,
            academic_year=current_term.academic_year.name if current_term and current_term.academic_year else '',
        )
        qr_code_base64 = generate_verification_qr(verification.verification_code, request=request)
    except Exception as e:
        logger.warning(f"Could not create verification record: {e}")

    context = {
        'student': student,
        'current_term': current_term,
        'subject_grades': subject_grades,
        'core_grades': core_grades,
        'elective_grades': elective_grades,
        'term_report': term_report,
        'grade_summary': grade_summary,
        'categories': categories,
        'grading_system': grading_system,
        'school': school,
        'school_settings': school_settings,
        'verification': verification,
        'qr_code_base64': qr_code_base64,
    }

    return render(request, 'gradebook/report_card_print.html', context)


# ============ Analytics Dashboard ============ 

@login_required
@admin_required
def analytics(request):
    """Analytics dashboard with grade trends and statistics (Admin only)."""
    current_term = Term.get_current()
    classes = Class.objects.filter(is_active=True).order_by('level_number', 'name')

    # Get filter parameters
    class_id = request.GET.get('class')
    selected_class = None

    if class_id:
        selected_class = get_object_or_404(Class, pk=class_id)

    context = {
        'current_term': current_term,
        'classes': classes,
        'selected_class': selected_class,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook', 'url': '/gradebook/'},
            {'label': 'Analytics'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/analytics.html',
        'gradebook/partials/analytics_content.html',
        context
    )


@login_required
def analytics_class_data(request, class_id):
    """Get analytics data for a specific class (HTMX partial)."""
    current_term = Term.get_current()
    class_obj = get_object_or_404(Class, pk=class_id)

    if not current_term:
        return render(request, 'gradebook/partials/analytics_class.html', {
            'error': 'No current term set'
        })

    # Get grading system based on class level
    grading_level = 'SHS' if class_obj.level_type == 'shs' else 'BASIC'
    grading_system = GradingSystem.objects.filter(
        level=grading_level,
        is_active=True
    ).first()

    # Use grading system thresholds or defaults
    pass_mark = grading_system.pass_mark if grading_system else config.DEFAULT_PASS_MARK
    min_avg_for_promotion = grading_system.min_average_for_promotion if grading_system else config.DEFAULT_MIN_AVERAGE_FOR_PROMOTION

    # Get all term reports for this class
    term_reports = list(TermReport.objects.filter(
        student__current_class=class_obj,
        term=current_term
    ).select_related('student').order_by('-average'))

    # Get subject grades for grade distribution
    subject_grades = list(SubjectTermGrade.objects.filter(
        student__current_class=class_obj,
        term=current_term,
        total_score__isnull=False
    ).select_related('subject', 'student'))

    # Calculate statistics
    stats = calculate_class_stats(term_reports, subject_grades)

    # Get subject performance comparison (using configurable pass mark)
    subject_performance = calculate_subject_performance(subject_grades, pass_mark=pass_mark)

    # Get grade distribution
    grade_distribution = calculate_grade_distribution(subject_grades)

    # Get top performers
    top_performers = term_reports[:config.TOP_PERFORMERS_LIMIT] if term_reports else []

    # Get students needing attention (failed 2+ subjects or avg below promotion threshold)
    at_risk = [
        r for r in term_reports
        if r.subjects_failed >= 2 or (r.average and r.average < min_avg_for_promotion)
    ][:config.AT_RISK_STUDENTS_LIMIT]

    context = {
        'class_obj': class_obj,
        'current_term': current_term,
        'stats': stats,
        'subject_performance': subject_performance,
        'grade_distribution': grade_distribution,
        'grade_distribution_json': json.dumps(grade_distribution),
        'subject_performance_json': json.dumps(subject_performance),
        'top_performers': top_performers,
        'at_risk_students': at_risk,
        'total_students': len(term_reports),
        'grading_system': grading_system,
        'pass_mark': pass_mark,
    }

    return render(request, 'gradebook/partials/analytics_class.html', context)


@login_required
@admin_required
def analytics_overview(request):
    """School-wide analytics overview (HTMX partial, Admin only)."""
    current_term = Term.get_current()

    if not current_term:
        return render(request, 'gradebook/partials/analytics_overview.html', {
            'error': 'No current term set'
        })

    # Get default pass mark from any active grading system (school-wide stats)
    default_grading_system = GradingSystem.objects.filter(is_active=True).first()
    default_pass_mark = default_grading_system.pass_mark if default_grading_system else config.DEFAULT_PASS_MARK

    # Get all classes with their stats
    classes = Class.objects.filter(is_active=True).order_by('level_number', 'name')

    class_stats = []
    for cls in classes:
        reports = TermReport.objects.filter(
            student__current_class=cls,
            term=current_term
        ).aggregate(
            avg_score=Avg('average'),
            total_students=Count('id'),
            passed=Count('id', filter=Q(subjects_failed=0)),
        )

        if reports['total_students'] > 0:
            class_stats.append({
                'class': cls,
                'average': round(reports['avg_score'] or 0, 1),
                'total_students': reports['total_students'],
                'passed': reports['passed'],
                'pass_rate': round((reports['passed'] / reports['total_students']) * 100, 1) if reports['total_students'] > 0 else 0,
            })

    # Sort by average descending
    class_stats.sort(key=lambda x: x['average'], reverse=True)

    # Overall school stats
    all_reports = TermReport.objects.filter(term=current_term)
    school_stats = all_reports.aggregate(
        total_students=Count('id'),
        avg_score=Avg('average'),
        total_passed=Count('id', filter=Q(subjects_failed=0)),
    )

    # Subject-wise school performance (using configurable pass mark)
    subject_stats = SubjectTermGrade.objects.filter(
        term=current_term,
        total_score__isnull=False
    ).values('subject__name', 'subject__short_name').annotate(
        avg_score=Avg('total_score'),
        students=Count('id'),
        passed=Count('id', filter=Q(total_score__gte=default_pass_mark)),
    ).order_by('-avg_score')[:config.TOP_SUBJECTS_LIMIT]

    context = {
        'current_term': current_term,
        'class_stats': class_stats,
        'class_stats_json': json.dumps([
            {'name': s['class'].name, 'average': float(s['average'])}
            for s in class_stats
        ]),
        'school_stats': {
            'total_students': school_stats['total_students'] or 0,
            'average': round(school_stats['avg_score'] or 0, 1),
            'passed': school_stats['total_passed'] or 0,
            'pass_rate': round((school_stats['total_passed'] / school_stats['total_students']) * 100, 1) if school_stats['total_students'] else 0,
        },
        'subject_stats': list(subject_stats),
        'pass_mark': default_pass_mark,
    }

    return render(request, 'gradebook/partials/analytics_overview.html', context)


@login_required
@admin_required
def analytics_term_comparison(request):
    """Compare performance across terms (HTMX partial, Admin only)."""
    # Get all terms from current academic year
    current_term = Term.get_current()
    if not current_term:
        return render(request, 'gradebook/partials/analytics_terms.html', {
            'error': 'No current term set'
        })

    terms = Term.objects.filter(
        academic_year=current_term.academic_year
    ).order_by('term_number')

    term_data = []
    for term in terms:
        stats = TermReport.objects.filter(term=term).aggregate(
            avg_score=Avg('average'),
            total_students=Count('id'),
            passed=Count('id', filter=Q(subjects_failed=0)),
        )

        if stats['total_students'] > 0:
            term_data.append({
                'term': term,
                'average': round(stats['avg_score'] or 0, 1),
                'total_students': stats['total_students'],
                'passed': stats['passed'],
                'pass_rate': round((stats['passed'] / stats['total_students']) * 100, 1),
            })

    context = {
        'terms': term_data,
        'terms_json': json.dumps([
            {'name': t['term'].name, 'average': float(t['average']), 'pass_rate': float(t['pass_rate'])}
            for t in term_data
        ]),
        'current_term': current_term,
    }

    return render(request, 'gradebook/partials/analytics_terms.html', context)


def calculate_class_stats(term_reports, subject_grades):
    """Calculate comprehensive class statistics."""
    if not term_reports:
        return {
            'average': 0,
            'highest': 0,
            'lowest': 0,
            'pass_rate': 0,
            'subjects_avg_passed': 0,
        }

    averages = [r.average for r in term_reports if r.average is not None]

    if not averages:
        return {
            'average': 0,
            'highest': 0,
            'lowest': 0,
            'pass_rate': 0,
            'subjects_avg_passed': 0,
        }

    total_students = len(term_reports)
    passed = sum(1 for r in term_reports if r.subjects_failed == 0)
    avg_subjects_passed = sum(r.subjects_passed for r in term_reports) / total_students if total_students else 0

    return {
        'average': round(sum(averages) / len(averages), 1),
        'highest': round(max(averages), 1),
        'lowest': round(min(averages), 1),
        'pass_rate': round((passed / total_students) * 100, 1) if total_students else 0,
        'subjects_avg_passed': round(avg_subjects_passed, 1),
    }


def calculate_subject_performance(subject_grades, pass_mark=None):
    """
    Calculate per-subject performance metrics.

    Args:
        subject_grades: List of SubjectTermGrade objects
        pass_mark: The pass mark threshold (defaults to grading system standard)
    """
    if pass_mark is None:
        pass_mark = config.DEFAULT_PASS_MARK

    subject_data = defaultdict(lambda: {'scores': [], 'passed': 0, 'total': 0})

    for grade in subject_grades:
        subj = grade.subject.short_name or grade.subject.name[:10]
        subject_data[subj]['scores'].append(float(grade.total_score))
        subject_data[subj]['total'] += 1
        if grade.total_score >= pass_mark:
            subject_data[subj]['passed'] += 1

    result = []
    for name, data in subject_data.items():
        if data['scores']:
            result.append({
                'name': name,
                'average': round(sum(data['scores']) / len(data['scores']), 1),
                'pass_rate': round((data['passed'] / data['total']) * 100, 1) if data['total'] else 0,
                'students': data['total'],
            })

    # Sort by average descending
    result.sort(key=lambda x: x['average'], reverse=True)
    return result


def calculate_grade_distribution(subject_grades, grading_system=None):
    """Calculate grade distribution across all subjects.

    Args:
        subject_grades: List of SubjectTermGrade objects
        grading_system: Optional GradingSystem to get grade order from.
                       If not provided, fetches the active one.
    """
    grade_counts = Counter(g.grade for g in subject_grades if g.grade)

    # Get grade order from grading system (ordered by min_percentage descending)
    if grading_system is None:
        grading_system = GradingSystem.objects.filter(
            is_active=True
        ).prefetch_related('scales').first()

    if grading_system:
        # Get grades ordered by min_percentage descending (highest grades first)
        grade_order = list(
            grading_system.scales.order_by('-min_percentage')
            .values_list('grade_label', flat=True)
        )
        # Determine key grades (first, middle, pass threshold, and last)
        key_grades = set()
        if grade_order:
            key_grades.add(grade_order[0])  # Best grade
            key_grades.add(grade_order[-1])  # Worst grade
            if len(grade_order) > 2:
                key_grades.add(grade_order[len(grade_order) // 2])  # Middle grade
    else:
        # Fallback to WASSCE grades if no grading system configured
        grade_order = ['A1', 'B2', 'B3', 'C4', 'C5', 'C6', 'D7', 'E8', 'F9']
        key_grades = {'A1', 'B2', 'C6', 'F9'}

    result = []
    for grade in grade_order:
        count = grade_counts.get(grade, 0)
        if count > 0 or grade in key_grades:
            result.append({
                'grade': grade,
                'count': count,
            })

    return result


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


# ============ Report Distribution ============ 

@login_required
def report_distribution(request, class_id):
    """
    Report distribution page for a class.
    Shows students with their contact info and distribution status.
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
            messages.error(request, 'You can only distribute reports for your homeroom class.')
            return redirect('gradebook:reports')

    # Get students with term reports
    students = list(Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('last_name', 'first_name'))

    if not students:
        messages.info(request, 'No active students found in this class.')
        return redirect('gradebook:reports')

    # Prefetch term reports and distribution logs
    student_ids = [s.id for s in students]
    reports = {
        r.student_id: r for r in TermReport.objects.filter(
            student_id__in=student_ids,
            term=current_term
        )
    }

    # Get latest distribution logs per student
    distribution_logs = {}
    for log in ReportDistributionLog.objects.filter(
        term_report__student_id__in=student_ids,
        term_report__term=current_term
    ).select_related('term_report').order_by('-created_at'):
        student_id = log.term_report.student_id
        if student_id not in distribution_logs:
            distribution_logs[student_id] = log

    # Calculate stats
    with_email = 0
    with_phone = 0
    already_sent = 0

    for student in students:
        student.term_report = reports.get(student.id)
        student.last_distribution = distribution_logs.get(student.id)

        # Check for guardian contact (use different attr names to avoid conflict with properties)
        contact_email = getattr(student, 'guardian_email', None) or getattr(student, 'parent_email', None)
        contact_phone = getattr(student, 'guardian_phone', None) or getattr(student, 'parent_phone', None)

        student.has_email = bool(contact_email)
        student.has_phone = bool(contact_phone)
        student.contact_email = contact_email
        student.contact_phone = contact_phone

        if student.has_email:
            with_email += 1
        if student.has_phone:
            with_phone += 1
        if student.last_distribution:
            already_sent += 1

    context = {
        'class_obj': class_obj,
        'students': students,
        'current_term': current_term,
        'is_admin': is_school_admin(user),
        'stats': {
            'total': len(students),
            'with_email': with_email,
            'with_phone': with_phone,
            'already_sent': already_sent,
        },
        'distribution_types': [
            ('EMAIL', 'Email with PDF'),
            ('SMS', 'SMS Summary'),
            ('BOTH', 'Email and SMS'),
        ],
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook', 'url': '/gradebook/'},
            {'label': 'Reports', 'url': '/gradebook/reports/'},
            {'label': f'{class_obj.name} Distribution'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/report_distribution.html',
        'gradebook/partials/report_distribution_content.html',
        context
    )


@login_required
@teacher_or_admin_required
def send_single_report(request, student_id):
    """Send report to a single student's guardian."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    current_term = Term.get_current()
    if not current_term:
        return JsonResponse({'success': False, 'error': 'No current term'})

    student = get_object_or_404(Student.objects.select_related('current_class'), pk=student_id)
    user = request.user

    # Permission check
    if not is_school_admin(user):
        if not (getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile')):
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        if not student.current_class or student.current_class.class_teacher != user.teacher_profile:
            return JsonResponse({'success': False, 'error': 'Permission denied'})

    # Get term report
    try:
        term_report = TermReport.objects.get(student=student, term=current_term)
    except TermReport.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No report found for this student'})

    distribution_type = request.POST.get('type', 'EMAIL')
    sms_template = request.POST.get('sms_template', '').strip() or None

    # Queue the task
    from ..tasks import distribute_single_report
    from django.db import connection

    distribute_single_report.delay(
        str(term_report.pk),
        distribution_type,
        connection.schema_name,
        user.pk,
        sms_template
    )

    response = HttpResponse(status=200)
    response['HX-Trigger'] = json.dumps({
        'showToast': {
            'message': f'Report queued for {student.first_name}',
            'type': 'success'
        },
        'refreshRow': str(student_id)
    })
    return response


@login_required
@teacher_or_admin_required
def send_bulk_reports(request, class_id):
    """Send reports for all students in a class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    current_term = Term.get_current()
    if not current_term:
        return JsonResponse({'success': False, 'error': 'No current term'})

    class_obj = get_object_or_404(Class, pk=class_id)
    user = request.user

    # Permission check
    if not is_school_admin(user):
        if not (getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile')):
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        if class_obj.class_teacher != user.teacher_profile:
            return JsonResponse({'success': False, 'error': 'Permission denied'})

    distribution_type = request.POST.get('type', 'EMAIL')
    sms_template = request.POST.get('sms_template', '').strip() or None

    # Queue the bulk task
    from ..tasks import distribute_bulk_reports
    from django.db import connection

    distribute_bulk_reports.delay(
        class_obj.pk,
        distribution_type,
        connection.schema_name,
        user.pk,
        sms_template
    )

    response = HttpResponse(status=200)
    response['HX-Trigger'] = json.dumps({
        'showToast': {
            'message': f'Reports queued for all students in {class_obj.name}',
            'type': 'success'
        }
    })
    return response


@login_required
def download_report_pdf(request, student_id):
    """Download PDF report for a student."""
    current_term = Term.get_current()
    if not current_term:
        messages.error(request, 'No current term set.')
        return redirect('gradebook:reports')

    student = get_object_or_404(Student.objects.select_related('current_class'), pk=student_id)
    user = request.user

    # Permission check
    if not is_school_admin(user):
        if not (getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile')):
            messages.error(request, 'Permission denied.')
            return redirect('gradebook:reports')
        if not student.current_class or student.current_class.class_teacher != user.teacher_profile:
            messages.error(request, 'Permission denied.')
            return redirect('gradebook:reports')

    try:
        term_report = TermReport.objects.get(student=student, term=current_term)
    except TermReport.DoesNotExist:
        messages.error(request, 'No report found for this student.')
        return redirect('gradebook:reports')

    # Generate PDF
    from ..tasks import generate_report_pdf
    from django.db import connection

    try:
        pdf_buffer = generate_report_pdf(term_report, connection.schema_name)

        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="report_card_{student.admission_number}.pdf"'
        return response

    except Exception as e:
        logger.error(f"Failed to generate PDF: {str(e)}")
        messages.error(request, f'Failed to generate PDF: {str(e)}')
        return redirect('gradebook:reports')


# =============================================================================
# TRANSCRIPT
# =============================================================================

@login_required
def transcript(request, student_id):
    """
    View a student's complete academic transcript.
    Shows all terms, grades, and cumulative performance.
    """
    student = get_object_or_404(
        Student.objects.select_related('current_class'),
        pk=student_id
    )

    # Permission check
    has_permission, error_msg = check_transcript_permission(request.user, student)
    if not has_permission:
        messages.error(request, error_msg)
        return redirect('gradebook:reports' if 'homeroom' in error_msg else 'core:index')

    # Get transcript data
    term_reports, all_grades, grades_by_term = get_transcript_data(student)

    # Build academic history with cumulative stats
    history_data = build_academic_history(term_reports, grades_by_term, include_all_grades=True)

    # Promotion history
    promotion_history = term_reports.filter(promoted__isnull=False).values(
        'term__academic_year__name',
        'term__name',
        'promoted',
        'promoted_to__name',
        'promotion_remarks'
    )

    # Get school context
    school_ctx = get_school_context()

    context = {
        'student': student,
        'academic_history': history_data['academic_history'],
        'term_reports': term_reports,
        'cumulative_stats': {
            'total_terms': history_data['term_count'],
            'total_subjects_taken': history_data['total_subjects_taken'],
            'total_subjects_passed': history_data['total_subjects_passed'],
            'total_credits': history_data['total_credits'],
            'cumulative_average': history_data['cumulative_average'],
            'unique_subjects': len(history_data['unique_subjects']),
        },
        'promotion_history': list(promotion_history),
        'school': school_ctx['school'],
        'school_settings': school_ctx['school_settings'],
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook', 'url': '/gradebook/'},
            {'label': 'Reports', 'url': '/gradebook/reports/'},
            {'label': f'{student.full_name} Transcript'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/transcript.html',
        'gradebook/partials/transcript_content.html',
        context
    )


@login_required
def transcript_print(request, student_id):
    """Print-friendly transcript view."""
    student = get_object_or_404(
        Student.objects.select_related('current_class'),
        pk=student_id
    )

    # Permission check
    has_permission, error_msg = check_transcript_permission(request.user, student)
    if not has_permission:
        messages.error(request, 'Permission denied.')
        return redirect('gradebook:reports' if 'homeroom' in (error_msg or '') else 'core:index')

    # Get transcript data and build academic history
    term_reports, _, grades_by_term = get_transcript_data(student)
    history_data = build_academic_history(term_reports, grades_by_term)

    # Get school context
    school_ctx = get_school_context()

    # Create verification record and generate QR code
    verification = None
    qr_code_base64 = None
    try:
        from core.models import DocumentVerification
        from core.utils import generate_verification_qr

        verification = DocumentVerification.create_for_document(
            document_type=DocumentVerification.DocumentType.TRANSCRIPT,
            student=student,
            title=f"Academic Transcript - {student.full_name}",
            user=request.user,
        )
        qr_code_base64 = generate_verification_qr(verification.verification_code, request=request)
    except Exception as e:
        logger.warning(f"Could not create verification record: {e}")

    context = {
        'student': student,
        'academic_history': history_data['academic_history'],
        'cumulative_average': history_data['cumulative_average'],
        'total_terms': history_data['term_count'],
        'total_credits': history_data['total_credits'],
        'generated_date': timezone.now(),
        'school': school_ctx['school'],
        'school_settings': school_ctx['school_settings'],
        'verification': verification,
        'qr_code_base64': qr_code_base64,
    }

    return render(request, 'gradebook/transcript_print.html', context)


@login_required
def download_transcript_pdf(request, student_id):
    """Download PDF transcript for a student."""
    student = get_object_or_404(
        Student.objects.select_related('current_class'),
        pk=student_id
    )

    # Permission check
    has_permission, error_msg = check_transcript_permission(request.user, student)
    if not has_permission:
        messages.error(request, 'Permission denied.')
        return redirect('gradebook:reports')

    # Get transcript data
    term_reports, _, grades_by_term = get_transcript_data(student)

    if not term_reports.exists():
        messages.error(request, 'No academic records found for this student.')
        return redirect('gradebook:reports')

    # Build academic history
    history_data = build_academic_history(term_reports, grades_by_term)

    # Get school context with base64 logo for PDF
    school_ctx = get_school_context(include_logo_base64=True)

    # Create verification record and generate QR code
    from core.models import DocumentVerification
    from core.utils import generate_verification_qr

    verification = DocumentVerification.create_for_document(
        document_type=DocumentVerification.DocumentType.TRANSCRIPT,
        student=student,
        title=f"Academic Transcript - {student.full_name}",
        user=request.user,
    )
    qr_code_base64 = generate_verification_qr(verification.verification_code, request=request)

    context = {
        'student': student,
        'academic_history': history_data['academic_history'],
        'cumulative_average': history_data['cumulative_average'],
        'total_terms': history_data['term_count'],
        'total_credits': history_data['total_credits'],
        'generated_date': timezone.now(),
        'request': request,
        'school': school_ctx['school'],
        'school_settings': school_ctx['school_settings'],
        'logo_base64': school_ctx['logo_base64'],
        'verification': verification,
        'qr_code_base64': qr_code_base64,
    }

    # Generate PDF using WeasyPrint
    try:
        from weasyprint import HTML
        from django.template.loader import render_to_string
        from django.conf import settings as django_settings
        from io import BytesIO

        html_string = render_to_string('gradebook/transcript_pdf.html', context)
        html = HTML(string=html_string, base_url=str(django_settings.BASE_DIR))
        pdf_buffer = BytesIO()
        html.write_pdf(pdf_buffer)
        pdf_buffer.seek(0)

        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="transcript_{student.admission_number}.pdf"'
        return response

    except ImportError:
        logger.error("WeasyPrint not installed")
        messages.error(request, 'PDF generation is not available. WeasyPrint is not installed.')
        return redirect('gradebook:transcript', student_id=student_id)
    except Exception as e:
        import traceback
        logger.error(f"Failed to generate transcript PDF: {str(e)}\n{traceback.format_exc()}")
        messages.error(request, f'Failed to generate PDF: {str(e)}')
        return redirect('gradebook:transcript', student_id=student_id)