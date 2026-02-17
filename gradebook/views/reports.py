from collections import Counter
import logging
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import HttpResponse, JsonResponse
from django.db.models import OuterRef, Subquery
from django.db import IntegrityError
from django.conf import settings
from django.contrib import messages

from .base import (
    htmx_render, is_school_admin, teacher_or_admin_required
)
from ..models import (
    GradingSystem, AssessmentCategory,
    Score, SubjectTermGrade, TermReport,
    ReportDistributionLog,
)
from ..utils import get_school_context
from academics.models import Class
from students.models import Student, Enrollment
from core.models import Term, SchoolSettings
from schools.models import School

logger = logging.getLogger(__name__)


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
    response['HX-Trigger'] = json.dumps({
        'showToast': {'message': 'Remark saved successfully', 'type': 'success'},
        'closeModal': True,
    })
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
    except ObjectDoesNotExist:
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
    except (ValidationError, IntegrityError) as e:
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

    # Prefetch primary guardians to avoid N+1 on guardian_phone/guardian_email
    from students.models import StudentGuardian
    sg_qs = StudentGuardian.objects.filter(
        student__in=students, is_primary=True
    ).select_related('guardian')
    guardian_map = {sg.student_id: sg.guardian for sg in sg_qs}
    for student in students:
        student._cached_primary_guardian = guardian_map.get(student.id)

    # Prefetch term reports and distribution logs
    student_ids = [s.id for s in students]
    reports = {
        r.student_id: r for r in TermReport.objects.filter(
            student_id__in=student_ids,
            term=current_term
        )
    }

    # Get latest distribution log per student via subquery (returns 1 row per student)
    latest_log_id = Subquery(
        ReportDistributionLog.objects.filter(
            term_report__student_id=OuterRef('term_report__student_id'),
            term_report__term=current_term
        ).order_by('-created_at').values('pk')[:1]
    )
    distribution_logs = {
        log.term_report.student_id: log
        for log in ReportDistributionLog.objects.filter(
            term_report__student_id__in=student_ids,
            term_report__term=current_term,
            pk=latest_log_id
        ).select_related('term_report')
    }

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

    except (ValueError, ValidationError, IOError) as e:
        logger.error(f"Failed to generate PDF: {str(e)}")
        messages.error(request, f'Failed to generate PDF: {str(e)}')
        return redirect('gradebook:reports')


# ============ Bulk PDF Export ============

@login_required
@teacher_or_admin_required
def export_class_reports(request, class_id):
    """Queue a Celery task to generate a ZIP of all report PDFs for a class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    class_obj = get_object_or_404(Class, pk=class_id)
    user = request.user

    # Permission check - must be class teacher or admin
    if not is_school_admin(user):
        if not (getattr(user, 'is_teacher', False) and hasattr(user, 'teacher_profile')):
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        if class_obj.class_teacher != user.teacher_profile:
            return JsonResponse({'success': False, 'error': 'Permission denied'})

    from ..tasks import export_class_reports_zip
    from django.db import connection

    result = export_class_reports_zip.delay(class_id, connection.schema_name)
    return JsonResponse({'success': True, 'task_id': result.id})


@login_required
@teacher_or_admin_required
def check_export_status(request, task_id):
    """Poll Celery task status for a ZIP export."""
    from celery.result import AsyncResult

    result = AsyncResult(task_id)
    state = result.state

    if state == 'PROGRESS':
        meta = result.info or {}
        return JsonResponse({
            'state': 'PROGRESS',
            'current': meta.get('current', 0),
            'total': meta.get('total', 0),
        })

    if state == 'SUCCESS':
        info = result.result or {}
        if not info.get('success'):
            return JsonResponse({
                'state': 'FAILURE',
                'error': info.get('error', 'Export failed'),
            })
        from django.urls import reverse
        download_url = reverse(
            'gradebook:download_class_reports',
            kwargs={'filename': info['filename']},
        )
        return JsonResponse({
            'state': 'SUCCESS',
            'download_url': download_url,
            'total': info.get('total', 0),
            'errors': info.get('errors', []),
        })

    if state == 'FAILURE':
        return JsonResponse({
            'state': 'FAILURE',
            'error': str(result.result) if result.result else 'Task failed',
        })

    # PENDING / STARTED / other
    return JsonResponse({'state': state})


@login_required
@teacher_or_admin_required
def download_class_reports(request, filename):
    """Serve a generated ZIP file for download."""
    import os
    from pathlib import Path
    from django.http import FileResponse

    media_root = Path(settings.MEDIA_ROOT).resolve()
    exports_root = media_root / 'exports'
    file_path = (exports_root / filename).resolve()

    # Path traversal protection
    if not str(file_path).startswith(str(exports_root)):
        return HttpResponse('Invalid path', status=400)

    if not file_path.exists():
        return HttpResponse('File not found', status=404)

    return FileResponse(
        open(file_path, 'rb'),
        as_attachment=True,
        content_type='application/zip',
        filename=file_path.name,
    )
