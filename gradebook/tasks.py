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

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django_tenants.utils import schema_context

from core.email_backend import get_from_email
from . import config


logger = logging.getLogger(__name__)


def generate_report_pdf(term_report, tenant_schema, shared_context=None):
    """
    Generate PDF report card for a student.

    Args:
        term_report: TermReport instance
        tenant_schema: Schema name for tenant context
        shared_context: Optional dict with pre-fetched data shared across
            students (school, rc_config, grading_system, categories,
            next_term_date). Avoids redundant DB queries in bulk exports.

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
        ).select_related('subject').order_by('-subject__is_core', 'subject__name'))

        # Get assessment categories (use shared if available)
        if shared_context and 'categories' in shared_context:
            categories = shared_context['categories']
        else:
            categories = list(AssessmentCategory.objects.filter(
                is_active=True
            ).order_by('order'))

        # Compute and attach category-wise scores for report card display
        from .utils import compute_report_category_scores, attach_category_scores
        category_scores_map = compute_report_category_scores(student, current_term, categories)
        attach_category_scores(subject_grades, categories, category_scores_map)

        # Get school info (use shared if available)
        if shared_context and 'school' in shared_context:
            school = shared_context['school']
            logo_base64 = shared_context.get('logo_base64')
            signature_base64 = shared_context.get('signature_base64')
        else:
            school = None
            logo_base64 = None
            signature_base64 = None
            try:
                from schools.models import School
                from .utils import encode_image_base64

                school = School.objects.get(schema_name=tenant_schema)
                if school and school.logo:
                    logo_base64 = encode_image_base64(school.logo)
                if school and school.headmaster_signature:
                    signature_base64 = encode_image_base64(school.headmaster_signature)
            except (IOError, OSError):
                pass

        student_photo_base64 = None
        core_grades = []
        elective_grades = []
        try:
            from .utils import encode_image_base64

            # Separate core and elective grades for SHS
            is_shs_class = (
                student.current_class
                and student.current_class.level_type == 'shs'
            )
            show_core_elective = (
                school and (
                    school.education_system == 'shs'
                    or (school.has_shs_levels and is_shs_class)
                )
            )
            if show_core_elective:
                core_grades = [
                    sg for sg in subject_grades if sg.subject.is_core
                ]
                elective_grades = [
                    sg for sg in subject_grades if not sg.subject.is_core
                ]

            # Encode student photo as base64 for PDF
            if student.photo:
                student_photo_base64 = encode_image_base64(student.photo)

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

        if shared_context and 'rc_config' in shared_context:
            rc_config = shared_context['rc_config']
            grading_system = shared_context.get('grading_system')
            next_term_date = shared_context.get('next_term_date')
        else:
            from core.models import SchoolSettings, Term
            from .models import GradingSystem
            rc_config = SchoolSettings.load()
            grading_system = GradingSystem.objects.filter(
                is_active=True
            ).prefetch_related('scales').first()

            # Get next term start date if available
            next_term_date = None
            if current_term:
                next_term = Term.objects.filter(
                    start_date__gt=current_term.end_date
                ).order_by('start_date').first()
                next_term_date = next_term.start_date if next_term else None

        context = {
            'student': student,
            'term_report': term_report,
            'current_term': current_term,
            'subject_grades': subject_grades,
            'core_grades': core_grades,
            'elective_grades': elective_grades,
            'categories': categories,
            'school': school,
            'logo_base64': logo_base64,
            'signature_base64': signature_base64,
            'student_photo_base64': student_photo_base64,
            'verification': verification,
            'qr_code_base64': qr_code_base64,
            'rc_config': rc_config,
            'grading_system': grading_system,
            'next_term_date': next_term_date,
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
        from django.db import connection
        school = getattr(connection, 'tenant', None)
        school_name = school.display_name if school else ''
    except Exception:
        pass

    import re as _re

    # Strip HTML from user-submitted text fields to prevent injection
    def _strip_html(text):
        return _re.sub(r'<[^>]+>', '', text) if text else ''

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
        'remark': _strip_html(term_report.class_teacher_remark or '')[:50],
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
            logger.error(f"TermReport {term_report_id} not found")
            return {'success': False, 'error': 'Report not found'}

        student = term_report.student
        sent_by = None
        if sent_by_id:
            try:
                sent_by = User.objects.get(pk=sent_by_id)
            except User.DoesNotExist:
                pass

        # Get guardian contact info
        guardian_email = getattr(student, 'guardian_email', None) or getattr(student, 'parent_email', None)
        guardian_phone = getattr(student, 'guardian_phone', None) or getattr(student, 'parent_phone', None)

        # Track results — log is only created once at the end (no partial saves)
        email_status = email_error = email_sent_to = email_sent_at = None
        sms_status = sms_error = sms_sent_to = sms_sent_at = sms_message = None
        results = {'email': None, 'sms': None}

        # Fetch school and logo for email template
        school = None
        logo_base64 = None
        try:
            from schools.models import School
            from .utils import encode_image_base64

            school = School.objects.get(schema_name=tenant_schema)
            if school and school.logo:
                logo_base64 = encode_image_base64(school.logo)
        except (IOError, OSError):
            pass

        # Send Email
        if distribution_type in ('EMAIL', 'BOTH') and guardian_email:
            try:
                pdf_buffer = generate_report_pdf(term_report, tenant_schema)

                subject = f"Report Card - {student.first_name} {student.last_name} - {term_report.term.name}"
                email_context = {
                    'student': student,
                    'term_report': term_report,
                    'term': term_report.term,
                    'school': school,
                    'logo_base64': logo_base64,
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

                email_status = 'SENT'
                email_sent_to = guardian_email
                email_sent_at = timezone.now()
                results['email'] = 'sent'

            except RETRYABLE_EXCEPTIONS as e:
                logger.warning(f"Retryable error sending email for report {term_report_id}: {str(e)}")
                raise self.retry(exc=e, countdown=config.TASK_RETRY_DELAY * (2 ** self.request.retries))

            except Exception as e:
                logger.error(f"Failed to send email for report {term_report_id}: {str(e)}")
                email_status = 'FAILED'
                email_error = str(e)[:500]
                results['email'] = f'failed: {str(e)}'

        # Send SMS
        if distribution_type in ('SMS', 'BOTH') and guardian_phone:
            try:
                from communications.utils import send_sms_sync
                from communications.models import SMSMessage

                sms_text = generate_sms_summary(term_report, custom_template=sms_template)

                sms_record = SMSMessage.objects.create(
                    recipient_phone=guardian_phone,
                    recipient_name=getattr(student, 'guardian_name', ''),
                    student=student,
                    message=sms_text,
                    message_type=SMSMessage.MessageType.REPORT_FEEDBACK,
                    status=SMSMessage.Status.PENDING,
                    created_by=sent_by,
                )

                sms_result = send_sms_sync(guardian_phone, sms_text)

                if sms_result.get('success'):
                    sms_status = 'SENT'
                    sms_sent_to = guardian_phone
                    sms_sent_at = timezone.now()
                    sms_message = sms_record
                    sms_record.mark_sent(sms_result.get('response', ''))
                    results['sms'] = 'sent'
                else:
                    sms_status = 'FAILED'
                    sms_error = sms_result.get('error', 'Unknown error')[:500]
                    sms_record.mark_failed(sms_result.get('error', ''))
                    results['sms'] = f"failed: {sms_result.get('error')}"

            except RETRYABLE_EXCEPTIONS as e:
                # Don't retry if email already sent — would cause duplicate emails
                if email_status == 'SENT':
                    logger.warning(
                        f"SMS failed for report {term_report_id} but email already sent. "
                        f"Not retrying to avoid duplicate email. SMS error: {str(e)}"
                    )
                    sms_status = 'FAILED'
                    sms_error = f'Retryable error (not retried to avoid duplicate email): {str(e)[:400]}'
                    results['sms'] = f'failed: {str(e)}'
                else:
                    logger.warning(f"Retryable error sending SMS for report {term_report_id}: {str(e)}")
                    raise self.retry(exc=e, countdown=config.TASK_RETRY_DELAY * (2 ** self.request.retries))

            except Exception as e:
                logger.error(f"Failed to send SMS for report {term_report_id}: {str(e)}")
                sms_status = 'FAILED'
                sms_error = str(e)[:500]
                results['sms'] = f'failed: {str(e)}'

        # Create distribution log once with final state (no partial saves)
        log = ReportDistributionLog.objects.create(
            term_report=term_report,
            distribution_type=distribution_type,
            sent_by=sent_by,
            email_status=email_status or '',
            email_sent_to=email_sent_to or '',
            email_sent_at=email_sent_at,
            email_error=email_error or '',
            sms_status=sms_status or '',
            sms_sent_to=sms_sent_to or '',
            sms_sent_at=sms_sent_at,
            sms_error=sms_error or '',
            sms_message=sms_message,
        )

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

        # Pre-fetch shared data to avoid redundant queries per student
        from .models import AssessmentCategory, GradingSystem
        from core.models import SchoolSettings
        shared_context = {
            'categories': list(AssessmentCategory.objects.filter(is_active=True).order_by('order')),
            'rc_config': SchoolSettings.load(),
            'grading_system': GradingSystem.objects.filter(is_active=True).prefetch_related('scales').first(),
        }
        try:
            from schools.models import School
            from .utils import encode_image_base64
            school = School.objects.get(schema_name=tenant_schema)
            shared_context['school'] = school
            shared_context['logo_base64'] = encode_image_base64(school.logo) if school.logo else None
            shared_context['signature_base64'] = encode_image_base64(school.headmaster_signature) if school.headmaster_signature else None
        except Exception:
            shared_context['school'] = None
            shared_context['logo_base64'] = None
            shared_context['signature_base64'] = None

        next_term = Term.objects.filter(
            start_date__gt=current_term.end_date
        ).order_by('start_date').first()
        shared_context['next_term_date'] = next_term.start_date if next_term else None

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, term_report in enumerate(term_reports):
                    self.update_state(
                        state='PROGRESS',
                        meta={'current': i + 1, 'total': total},
                    )
                    try:
                        pdf_buffer = generate_report_pdf(term_report, tenant_schema, shared_context=shared_context)
                        admission = term_report.student.admission_number
                        zf.writestr(
                            f"report_card_{admission}.pdf",
                            pdf_buffer.getvalue(),
                        )
                    except Exception as e:
                        student_name = str(term_report.student)
                        logger.error(f"PDF generation failed for {student_name}: {e}")
                        errors.append(f"{student_name}: {str(e)[:100]}")
        except Exception:
            # Clean up partial ZIP on failure
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except OSError:
                    logger.warning(f"Could not delete failed ZIP: {zip_path}")
            raise

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
        failed_count = 0
        for report_id in term_reports:
            try:
                distribute_single_report.delay(
                    str(report_id),
                    distribution_type,
                    tenant_schema,
                    sent_by_id,
                    sms_template
                )
                queued_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to queue report {report_id}: {e}")

        if failed_count and queued_count == 0:
            return {
                'success': False,
                'error': f'Failed to queue all {failed_count} reports',
            }

        return {
            'success': True,
            'class': class_obj.name,
            'queued': queued_count,
            'failed': failed_count,
        }


DEFAULT_GRADE_ALERT_TEMPLATE = (
    "Dear Parent, {student_name}'s current average in {class_name} "
    "is {average}% ({term}). Please encourage them to improve. - {school_name}"
)


@shared_task(bind=True, max_retries=2)
def send_grade_alerts(self, class_id, tenant_schema):
    """
    Send SMS alerts to parents of students whose average
    falls below the configured threshold after grade calculation.
    """
    with schema_context(tenant_schema):
        from .models import TermReport
        from academics.models import Class
        from core.models import Term, SchoolSettings
        from communications.utils import send_sms
        from schools.models import School

        settings_obj = SchoolSettings.load()
        if not settings_obj.grade_alert_enabled:
            return {'sent': 0, 'reason': 'alerts disabled'}

        threshold = settings_obj.grade_alert_threshold
        sms_template = settings_obj.grade_alert_sms_template or DEFAULT_GRADE_ALERT_TEMPLATE

        current_term = Term.get_current()
        if not current_term:
            return {'sent': 0, 'reason': 'no current term'}

        try:
            class_obj = Class.objects.get(pk=class_id)
        except Class.DoesNotExist:
            return {'sent': 0, 'reason': 'class not found'}

        try:
            tenant = School.objects.get(schema_name=tenant_schema)
        except School.DoesNotExist:
            return {'sent': 0, 'reason': 'school not found'}

        # Find students below threshold
        reports = TermReport.objects.filter(
            student__current_class=class_obj,
            term=current_term,
            average__lt=threshold,
            average__gt=0,
        ).select_related('student')

        sent = 0
        for report in reports:
            student = report.student
            guardian = student.get_primary_guardian() if hasattr(student, 'get_primary_guardian') else None
            phone = guardian.phone_number if guardian else student.guardian_phone
            if not phone:
                continue

            # Respect notification preference
            pref = getattr(guardian, 'notification_preference', 'sms') if guardian else 'sms'
            if pref == 'none':
                continue

            try:
                message = sms_template.format(
                    student_name=student.first_name,
                    class_name=class_obj.name,
                    average=report.average,
                    term=current_term.name,
                    school_name=tenant.name,
                )
            except (KeyError, IndexError, ValueError):
                # Fallback if template has unknown placeholders
                message = (
                    f"Dear Parent, {student.first_name}'s average of "
                    f"{report.average}% in {current_term.name} is below "
                    f"the expected threshold. Please follow up. - {tenant.name}"
                )

            try:
                if pref in ('sms', 'both'):
                    send_sms(phone, message)
                if pref in ('email', 'both') and guardian and guardian.email:
                    from django.core.mail import send_mail
                    send_mail(
                        subject=f"Grade Alert - {student.first_name}",
                        message=message,
                        from_email=None,
                        recipient_list=[guardian.email],
                        fail_silently=True,
                    )
                sent += 1
                logger.info(
                    f"Grade alert sent for {student.full_name} "
                    f"(avg: {report.average}%) via {pref}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to send grade alert for {student.full_name}: {e}"
                )

        return {'sent': sent, 'class': class_obj.name, 'threshold': str(threshold)}


@shared_task(bind=True)
def check_scheduled_reports(self):
    """
    Periodic task: check all tenants for scheduled report distribution.
    Run every 15 minutes via django-celery-beat.
    """
    from schools.models import School

    tenants = School.objects.exclude(schema_name='public')
    distributed = 0

    for tenant in tenants:
        try:
            with schema_context(tenant.schema_name):
                from core.models import SchoolSettings, Term
                from academics.models import Class

                settings_obj = SchoolSettings.load()
                if not settings_obj.scheduled_report_date:
                    continue

                now = timezone.now()
                if settings_obj.scheduled_report_date > now:
                    continue  # Not yet time

                current_term = Term.get_current()
                if not current_term:
                    continue

                # Distribute reports for all classes
                classes = Class.objects.filter(
                    students__status='active'
                ).distinct()

                for cls in classes:
                    distribute_bulk_reports.delay(
                        cls.pk, 'EMAIL', tenant.schema_name
                    )
                    distributed += 1

                # Clear the schedule so it doesn't re-trigger
                settings_obj.scheduled_report_date = None
                settings_obj.save(update_fields=['scheduled_report_date'])

                logger.info(
                    f"Scheduled report distribution triggered for "
                    f"{tenant.schema_name}: {classes.count()} classes"
                )
        except Exception as e:
            logger.error(
                f"Error checking scheduled reports for {tenant.schema_name}: {e}"
            )

    return {'distributed': distributed}
