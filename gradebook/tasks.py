"""
Celery tasks for gradebook app.
Handles async report distribution via email and SMS.
"""
import logging
from io import BytesIO

from celery import shared_task
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.utils import timezone
from django.conf import settings

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError
from django_tenants.utils import schema_context

from core.email_backend import get_from_email
from . import config


logger = logging.getLogger(__name__)


def generate_report_pdf(term_report, tenant_schema):
    """
    Generate PDF report card for a student.

    Args:
        term_report: TermReport instance
        tenant_schema: Schema name for tenant context

    Returns:
        BytesIO: PDF content as bytes buffer
    """
    try:
        from weasyprint import HTML
    except ImportError:
        logger.error("WeasyPrint not installed. Install with: pip install weasyprint")
        raise

    with schema_context(tenant_schema):
        from .models import SubjectTermGrade, AssessmentCategory

        student = term_report.student
        current_term = term_report.term

        # Get subject grades
        subject_grades = list(SubjectTermGrade.objects.filter(
            student=student,
            term=current_term
        ).select_related('subject').order_by('subject__name'))

        # Get assessment categories
        categories = list(AssessmentCategory.objects.filter(
            is_active=True
        ).order_by('order'))

        # Calculate category-wise scores for each subject
        from .models import Score
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
                    percentage = (cat_data['earned'] / cat_data['possible']) * 100
                    weighted = (percentage * cat.percentage) / 100
                    sg.category_scores[cat.pk] = round(weighted, 1)
                else:
                    sg.category_scores[cat.pk] = None

        # Get school info
        school = None
        school_settings = None
        logo_base64 = None
        try:
            from schools.models import School
            from core.models import SchoolSettings
            import base64

            school = School.objects.get(schema_name=tenant_schema)
            school_settings = SchoolSettings.objects.first()

            # Encode logo as base64 for PDF by reading directly from filesystem
            if school_settings and school_settings.logo:
                from pathlib import Path

                # Build and validate logo path to prevent path traversal attacks
                media_root = Path(settings.MEDIA_ROOT).resolve()
                logo_path = (media_root / 'schools' / tenant_schema / school_settings.logo.name).resolve()

                # Security check: ensure path is within MEDIA_ROOT
                if not str(logo_path).startswith(str(media_root)):
                    logger.warning(f"Potential path traversal attempt blocked: {school_settings.logo.name}")
                    logo_path = None

                if logo_path and logo_path.exists():
                    with open(logo_path, 'rb') as f:
                        logo_data = f.read()
                    logo_base64 = base64.b64encode(logo_data).decode('utf-8')
                    # Detect image type
                    if str(logo_path).lower().endswith('.png'):
                        logo_base64 = f"data:image/png;base64,{logo_base64}"
                    elif str(logo_path).lower().endswith('.gif'):
                        logo_base64 = f"data:image/gif;base64,{logo_base64}"
                    else:
                        logo_base64 = f"data:image/jpeg;base64,{logo_base64}"
        except (IOError, OSError):
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
                title=f"Report Card - {current_term.name}",
                term=current_term,
                academic_year=current_term.academic_year.name if current_term.academic_year else '',
            )
            # Get domain from school for QR code URL
            domain = school.domain_url if school and hasattr(school, 'domain_url') else None
            qr_code_base64 = generate_verification_qr(verification.verification_code, domain=domain)
        except (ValueError, ValidationError, IntegrityError) as e:
            logger.warning(f"Could not create verification record: {e}")

        context = {
            'student': student,
            'term_report': term_report,
            'current_term': current_term,
            'subject_grades': subject_grades,
            'categories': categories,
            'school': school,
            'school_settings': school_settings,
            'logo_base64': logo_base64,
            'verification': verification,
            'qr_code_base64': qr_code_base64,
        }

        html_string = render_to_string('gradebook/report_card_pdf.html', context)

        # Generate PDF
        html = HTML(string=html_string, base_url=settings.BASE_DIR)
        pdf_buffer = BytesIO()
        html.write_pdf(pdf_buffer)
        pdf_buffer.seek(0)

        return pdf_buffer


def build_feedback_context(term_report):
    """
    Build context dictionary from term report for SMS personalization.

    Args:
        term_report: TermReport instance

    Returns:
        dict: Context with all available placeholders
    """
    student = term_report.student
    term = term_report.term

    # Get conduct display value
    conduct_display = ''
    if term_report.conduct_rating:
        conduct_map = {'A': 'Excellent', 'B': 'Very Good', 'C': 'Good', 'D': 'Fair', 'E': 'Poor'}
        conduct_display = conduct_map.get(term_report.conduct_rating, term_report.conduct_rating)

    # Get school name
    school_name = ''
    try:
        from core.models import SchoolSettings
        settings = SchoolSettings.load()
        school_name = settings.display_name if settings else ''
    except ObjectDoesNotExist:
        pass

    return {
        'student_name': student.first_name,
        'full_name': str(student),
        'class_name': student.current_class.name if student.current_class else '',
        'term': term.name if term else '',
        'position': term_report.position or '-',
        'out_of': term_report.out_of or '-',
        'average': f"{term_report.average:.1f}" if term_report.average else '-',
        'conduct': conduct_display,
        'attendance': f"{term_report.attendance_percentage:.0f}" if term_report.attendance_percentage else '-',
        'subjects_passed': term_report.subjects_passed or 0,
        'subjects_failed': term_report.subjects_failed or 0,
        'remark': (term_report.class_teacher_remark or '')[:50],  # Truncate long remarks
        'school_name': school_name,
        'date': timezone.now().strftime('%b %d, %Y'),
    }


def render_sms_template(template_text, context):
    """
    Render SMS template with context variables.

    Args:
        template_text: Template string with {placeholders}
        context: Dictionary of placeholder values

    Returns:
        str: Rendered message (plain text, HTML tags stripped)
    """
    import re
    message = template_text
    for key, value in context.items():
        # Strip HTML tags from values for SMS (plain text)
        str_value = str(value)
        clean_value = re.sub(r'<[^>]+>', '', str_value)
        message = message.replace(f'{{{key}}}', clean_value)
    return message


def generate_sms_summary(term_report, custom_template=None):
    """
    Generate SMS summary text for a report (max 160 chars).

    Args:
        term_report: TermReport instance
        custom_template: Optional custom template string

    Returns:
        str: SMS text
    """
    context = build_feedback_context(term_report)

    if custom_template:
        message = render_sms_template(custom_template, context)
    else:
        # Default template - position and average focused
        message = (
            f"Dear Parent, {context['student_name']}'s {context['term']} results: "
            f"Position {context['position']}/{context['out_of']}, Average {context['average']}%. "
        )

        # Add conduct if available
        if context['conduct']:
            message += f"Conduct: {context['conduct']}."

    # Truncate if needed
    max_length = config.SMS_MAX_LENGTH
    if len(message) > max_length:
        message = message[:max_length - 3] + "..."

    return message


# Pre-defined feedback templates
FEEDBACK_TEMPLATES = {
    'basic': "Dear Parent, {student_name}'s {term} results: Position {position}/{out_of}, Average {average}%.",
    'detailed': "Dear Parent, {student_name} is {position}/{out_of} with {average}% avg. Conduct: {conduct}. Attendance: {attendance}%.",
    'encouraging': "Great news! {student_name} achieved Position {position} with {average}%. Keep encouraging them!",
    'needs_improvement': "Dear Parent, {student_name} needs support. Position: {position}/{out_of}, Avg: {average}%. Please contact school.",
    'custom_remark': "Dear Parent, {student_name}'s {term} feedback: {remark}",
}


@shared_task(
    bind=True,
    max_retries=config.TASK_MAX_RETRIES,
    default_retry_delay=config.TASK_RETRY_DELAY,
    soft_time_limit=config.TASK_SOFT_TIME_LIMIT,
    time_limit=config.TASK_TIME_LIMIT,
)
def distribute_single_report(self, term_report_id, distribution_type, tenant_schema, sent_by_id=None, sms_template=None):
    """
    Distribute a single student report via email and/or SMS.

    Args:
        term_report_id: ID of the TermReport
        distribution_type: 'EMAIL', 'SMS', or 'BOTH'
        tenant_schema: Schema name for tenant context
        sent_by_id: ID of the user who initiated the distribution
        sms_template: Optional custom SMS template string

    Retries up to 3 times with exponential backoff for transient failures.
    """
    from django_tenants.utils import schema_context
    from smtplib import SMTPException
    from socket import error as SocketError
    import ssl

    # Transient errors that should trigger retry
    RETRYABLE_EXCEPTIONS = (SMTPException, SocketError, ssl.SSLError, ConnectionError, TimeoutError)

    with schema_context(tenant_schema):
        from .models import TermReport, ReportDistributionLog
        from django.contrib.auth import get_user_model

        User = get_user_model()

        try:
            term_report = TermReport.objects.select_related(
                'student', 'student__current_class', 'term'
            ).get(pk=term_report_id)
        except TermReport.DoesNotExist:
            # Non-retryable - report doesn't exist
            logger.error(f"TermReport {term_report_id} not found")
            return {'success': False, 'error': 'Report not found'}

        student = term_report.student
        sent_by = None
        if sent_by_id:
            try:
                sent_by = User.objects.get(pk=sent_by_id)
            except User.DoesNotExist:
                pass

        # Create distribution log
        log = ReportDistributionLog.objects.create(
            term_report=term_report,
            distribution_type=distribution_type,
            sent_by=sent_by,
        )

        # Get guardian contact info
        guardian_email = getattr(student, 'guardian_email', None) or getattr(student, 'parent_email', None)
        guardian_phone = getattr(student, 'guardian_phone', None) or getattr(student, 'parent_phone', None)

        results = {'email': None, 'sms': None}

        # Send Email
        if distribution_type in ('EMAIL', 'BOTH') and guardian_email:
            try:
                # Generate PDF
                pdf_buffer = generate_report_pdf(term_report, tenant_schema)

                # Prepare email
                subject = f"Report Card - {student.first_name} {student.last_name} - {term_report.term.name}"

                email_context = {
                    'student': student,
                    'term_report': term_report,
                    'term': term_report.term,
                }
                html_message = render_to_string('gradebook/emails/report_email.html', email_context)

                email = EmailMessage(
                    subject=subject,
                    body=html_message,
                    from_email=get_from_email(),
                    to=[guardian_email],
                )
                email.content_subtype = 'html'
                email.attach(
                    f"report_card_{student.admission_number}.pdf",
                    pdf_buffer.getvalue(),
                    'application/pdf'
                )
                email.send()

                # Update log
                log.email_status = 'SENT'
                log.email_sent_to = guardian_email
                log.email_sent_at = timezone.now()
                results['email'] = 'sent'

            except RETRYABLE_EXCEPTIONS as e:
                # Transient error - retry with exponential backoff
                logger.warning(f"Retryable error sending email for report {term_report_id}: {str(e)}")
                log.email_status = 'FAILED'
                log.email_error = f"Retry {self.request.retries + 1}: {str(e)[:450]}"
                log.save()
                raise self.retry(exc=e, countdown=config.TASK_RETRY_DELAY * (2 ** self.request.retries))

            except Exception as e:
                # Non-retryable error
                logger.error(f"Failed to send email for report {term_report_id}: {str(e)}")
                log.email_status = 'FAILED'
                log.email_error = str(e)[:500]
                results['email'] = f'failed: {str(e)}'

        # Send SMS
        if distribution_type in ('SMS', 'BOTH') and guardian_phone:
            try:
                from communications.utils import send_sms_sync
                from communications.models import SMSMessage

                sms_text = generate_sms_summary(term_report, custom_template=sms_template)

                # Create SMS record first
                sms_record = SMSMessage.objects.create(
                    recipient_phone=guardian_phone,
                    recipient_name=getattr(student, 'guardian_name', ''),
                    student=student,
                    message=sms_text,
                    message_type=SMSMessage.MessageType.REPORT_FEEDBACK,
                    status=SMSMessage.Status.PENDING,
                    created_by=sent_by,
                )

                # Send synchronously (we're already in a Celery task)
                sms_result = send_sms_sync(guardian_phone, sms_text)

                if sms_result.get('success'):
                    log.sms_status = 'SENT'
                    log.sms_sent_to = guardian_phone
                    log.sms_sent_at = timezone.now()
                    log.sms_message = sms_record
                    sms_record.mark_sent(sms_result.get('response', ''))
                    results['sms'] = 'sent'
                else:
                    log.sms_status = 'FAILED'
                    log.sms_error = sms_result.get('error', 'Unknown error')[:500]
                    sms_record.mark_failed(sms_result.get('error', ''))
                    results['sms'] = f"failed: {sms_result.get('error')}"

            except RETRYABLE_EXCEPTIONS as e:
                # Transient error - retry with exponential backoff
                logger.warning(f"Retryable error sending SMS for report {term_report_id}: {str(e)}")
                log.sms_status = 'FAILED'
                log.sms_error = f"Retry {self.request.retries + 1}: {str(e)[:450]}"
                log.save()
                raise self.retry(exc=e, countdown=config.TASK_RETRY_DELAY * (2 ** self.request.retries))

            except Exception as e:
                # Non-retryable error
                logger.error(f"Failed to send SMS for report {term_report_id}: {str(e)}")
                log.sms_status = 'FAILED'
                log.sms_error = str(e)[:500]
                results['sms'] = f'failed: {str(e)}'

        log.save()

        return {
            'success': True,
            'term_report_id': str(term_report_id),
            'student': f"{student.first_name} {student.last_name}",
            'results': results,
            'log_id': str(log.pk),
        }


@shared_task(
    bind=True,
    max_retries=0,
    soft_time_limit=config.BULK_TASK_SOFT_TIME_LIMIT,
    time_limit=config.BULK_TASK_TIME_LIMIT,
)
def export_class_reports_zip(self, class_id, tenant_schema):
    """
    Generate a ZIP file containing PDF report cards for all students in a class.

    Updates task state with progress so the frontend can poll for status.

    Args:
        class_id: ID of the Class
        tenant_schema: Schema name for tenant context

    Returns:
        dict with success, filename, total, and errors list
    """
    import os
    import uuid
    import zipfile

    with schema_context(tenant_schema):
        from .models import TermReport
        from academics.models import Class
        from core.models import Term

        try:
            class_obj = Class.objects.get(pk=class_id)
        except Class.DoesNotExist:
            logger.error(f"Class {class_id} not found for ZIP export")
            return {'success': False, 'error': 'Class not found'}

        current_term = Term.get_current()
        if not current_term:
            return {'success': False, 'error': 'No current term'}

        term_reports = list(TermReport.objects.filter(
            student__current_class=class_obj,
            term=current_term,
        ).select_related('student', 'term'))

        total = len(term_reports)
        if total == 0:
            return {'success': False, 'error': 'No reports found for this class'}

        # Create exports directory
        export_dir = os.path.join(
            settings.MEDIA_ROOT, 'exports', tenant_schema
        )
        os.makedirs(export_dir, exist_ok=True)

        # Build ZIP filename
        class_name = class_obj.name.replace(' ', '_')
        term_name = current_term.name.replace(' ', '_')
        short_uuid = uuid.uuid4().hex[:8]
        zip_filename = f"{class_name}_{term_name}_{short_uuid}.zip"
        zip_path = os.path.join(export_dir, zip_filename)

        errors = []

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, term_report in enumerate(term_reports):
                self.update_state(
                    state='PROGRESS',
                    meta={'current': i + 1, 'total': total},
                )
                try:
                    pdf_buffer = generate_report_pdf(term_report, tenant_schema)
                    admission = term_report.student.admission_number
                    zf.writestr(
                        f"report_card_{admission}.pdf",
                        pdf_buffer.getvalue(),
                    )
                except Exception as e:
                    student_name = str(term_report.student)
                    logger.error(f"PDF generation failed for {student_name}: {e}")
                    errors.append(f"{student_name}: {str(e)[:100]}")

        relative_filename = f"{tenant_schema}/{zip_filename}"
        return {
            'success': True,
            'filename': relative_filename,
            'total': total,
            'errors': errors,
        }


@shared_task
def cleanup_export_zips():
    """
    Remove ZIP export files older than EXPORT_ZIP_MAX_AGE_HOURS.

    Intended to be registered as a periodic task in django_celery_beat admin.
    """
    import os
    import time

    max_age_hours = config.EXPORT_ZIP_MAX_AGE_HOURS
    exports_root = os.path.join(settings.MEDIA_ROOT, 'exports')

    if not os.path.exists(exports_root):
        return {'deleted': 0}

    cutoff = time.time() - (max_age_hours * 3600)
    deleted = 0

    for dirpath, dirnames, filenames in os.walk(exports_root):
        for filename in filenames:
            if not filename.endswith('.zip'):
                continue
            filepath = os.path.join(dirpath, filename)
            if os.path.getmtime(filepath) < cutoff:
                os.remove(filepath)
                deleted += 1

        # Remove empty subdirectories
        for dirname in dirnames:
            subdir = os.path.join(dirpath, dirname)
            if not os.listdir(subdir):
                os.rmdir(subdir)

    return {'deleted': deleted}


@shared_task(
    bind=True,
    max_retries=config.TASK_MAX_RETRIES,
    soft_time_limit=config.BULK_TASK_SOFT_TIME_LIMIT,
    time_limit=config.BULK_TASK_TIME_LIMIT,
)
def distribute_bulk_reports(self, class_id, distribution_type, tenant_schema, sent_by_id=None, sms_template=None):
    """
    Distribute reports for all students in a class.
    Queues individual distribution tasks for each student.

    Args:
        class_id: ID of the Class
        distribution_type: 'EMAIL', 'SMS', or 'BOTH'
        tenant_schema: Schema name for tenant context
        sent_by_id: ID of the user who initiated the distribution
        sms_template: Optional custom SMS template string
    """
    from django_tenants.utils import schema_context

    with schema_context(tenant_schema):
        from .models import TermReport
        from academics.models import Class
        from core.models import Term

        try:
            class_obj = Class.objects.get(pk=class_id)
        except Class.DoesNotExist:
            logger.error(f"Class {class_id} not found")
            return {'success': False, 'error': 'Class not found'}

        current_term = Term.get_current()
        if not current_term:
            return {'success': False, 'error': 'No current term'}

        # Get all term reports for students in this class
        term_reports = TermReport.objects.filter(
            student__current_class=class_obj,
            term=current_term,
        ).values_list('pk', flat=True)

        queued_count = 0
        for report_id in term_reports:
            distribute_single_report.delay(
                str(report_id),
                distribution_type,
                tenant_schema,
                sent_by_id,
                sms_template
            )
            queued_count += 1

        return {
            'success': True,
            'class': class_obj.name,
            'queued': queued_count,
        }
