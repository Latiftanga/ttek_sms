import logging

from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.db import IntegrityError
from django.contrib import messages

from .base import htmx_render
from ..utils import (
    check_transcript_permission,
    get_transcript_data,
    build_academic_history,
    get_school_context,
)
from students.models import Student

logger = logging.getLogger(__name__)


# ============ Transcripts ============

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
    except (ValidationError, IntegrityError) as e:
        logger.warning(f"Could not create verification record: {e}")

    context = {
        'student': student,
        'academic_history': history_data['academic_history'],
        'cumulative_average': history_data['cumulative_average'],
        'total_terms': history_data['term_count'],
        'total_credits': history_data['total_credits'],
        'generated_date': timezone.now(),
        'school': school_ctx['school'],
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
    except (ValidationError, IntegrityError) as e:
        logger.warning(f"Could not create verification record: {e}")

    context = {
        'student': student,
        'academic_history': history_data['academic_history'],
        'cumulative_average': history_data['cumulative_average'],
        'total_terms': history_data['term_count'],
        'total_credits': history_data['total_credits'],
        'generated_date': timezone.now(),
        'request': request,
        'school': school_ctx['school'],
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
    except (ValueError, ValidationError, IOError) as e:
        import traceback
        logger.error(f"Failed to generate transcript PDF: {str(e)}\n{traceback.format_exc()}")
        messages.error(request, f'Failed to generate PDF: {str(e)}')
        return redirect('gradebook:transcript', student_id=student_id)
