"""
Finance notification tasks.
Handles async invoice/payment notifications via email (with PDF) and SMS.
"""
import logging
from io import BytesIO
from celery import shared_task
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from core.email_backend import get_from_email

logger = logging.getLogger(__name__)

# Configuration
TASK_MAX_RETRIES = 3
TASK_RETRY_DELAY = 60  # seconds
SMS_MAX_LENGTH = 320


# =============================================================================
# SMS TEMPLATES
# =============================================================================

FINANCE_SMS_TEMPLATES = {
    'invoice_issued': (
        "Dear Parent, {student_name}'s fees for {term}: GHS {total_amount}. "
        "Due: {due_date}. Pay here: {pay_url} - {school_name}"
    ),
    'payment_received': (
        "Dear Parent, payment of GHS {amount_paid} received for {student_name}. "
        "Balance: GHS {balance}. Receipt: {receipt_number}. Thank you! - {school_name}"
    ),
    'overdue_reminder': (
        "REMINDER: {student_name}'s fees of GHS {balance} is overdue since {due_date}. "
        "Please pay urgently: {pay_url} - {school_name}"
    ),
    'balance_reminder': (
        "Dear Parent, {student_name} has outstanding fees of GHS {balance}. "
        "Due: {due_date}. Pay here: {pay_url} - {school_name}"
    ),
}


def build_invoice_context(invoice):
    """Build context dictionary from invoice for SMS/email personalization."""
    student = invoice.student
    primary_guardian = student.get_primary_guardian() if hasattr(student, 'get_primary_guardian') else None

    # Get school name from tenant
    school_name = "School"
    try:
        from django.db import connection
        if hasattr(connection, 'tenant'):
            school_name = connection.tenant.name
    except Exception:
        pass

    # Build payment URL from tenant domain (no request available in Celery tasks)
    pay_url = ''
    try:
        from django_tenants.utils import get_tenant_domain_model
        Domain = get_tenant_domain_model()
        domain = Domain.objects.filter(tenant=connection.tenant, is_primary=True).first()
        if domain and invoice.status in ('ISSUED', 'PARTIALLY_PAID', 'OVERDUE') and invoice.balance > 0:
            pay_url = f"https://{domain.domain}/finance/fee-payments/pay/{invoice.pk}/"
    except Exception:
        pass

    return {
        'student_name': student.full_name,
        'first_name': student.first_name,
        'class_name': student.current_class.name if student.current_class else 'N/A',
        'invoice_number': invoice.invoice_number,
        'total_amount': f"{invoice.total_amount:.2f}",
        'amount_paid': f"{invoice.amount_paid:.2f}",
        'balance': f"{invoice.balance:.2f}",
        'due_date': invoice.due_date.strftime('%b %d, %Y') if invoice.due_date else 'N/A',
        'issue_date': invoice.issue_date.strftime('%b %d, %Y') if invoice.issue_date else 'N/A',
        'term': invoice.term.name if invoice.term else 'N/A',
        'academic_year': invoice.academic_year.name if invoice.academic_year else 'N/A',
        'school_name': school_name,
        'guardian_name': primary_guardian.full_name if primary_guardian else 'Parent/Guardian',
        'date': timezone.now().strftime('%b %d, %Y'),
        'pay_url': pay_url,
    }


def build_payment_context(payment):
    """Build context dictionary from payment for SMS/email personalization."""
    invoice = payment.invoice
    context = build_invoice_context(invoice)
    context.update({
        'receipt_number': payment.receipt_number,
        'payment_amount': f"{payment.amount:.2f}",
        'payment_method': payment.get_method_display(),
        'payment_date': payment.transaction_date.strftime('%b %d, %Y') if payment.transaction_date else 'N/A',
    })
    return context


def render_sms_template(template_key, context, custom_template=None):
    """Render SMS template with context variables."""
    if custom_template:
        template = custom_template
    else:
        template = FINANCE_SMS_TEMPLATES.get(template_key, FINANCE_SMS_TEMPLATES['balance_reminder'])

    # Strip HTML from context values
    clean_context = {k: strip_tags(str(v)) if v else '' for k, v in context.items()}

    try:
        message = template.format(**clean_context)
    except KeyError as e:
        logger.warning(f"Missing placeholder in template: {e}")
        message = template

    # Truncate to SMS limit
    if len(message) > SMS_MAX_LENGTH:
        message = message[:SMS_MAX_LENGTH - 3] + '...'

    return message


# =============================================================================
# PDF GENERATION
# =============================================================================

def generate_invoice_pdf(invoice, tenant_schema):
    """
    Generate PDF invoice using WeasyPrint.
    Returns BytesIO buffer containing PDF data.
    """
    from django_tenants.utils import schema_context
    from weasyprint import HTML
    import base64

    with schema_context(tenant_schema):
        # Get school info
        school_name = "School"
        school_logo_base64 = None
        school_address = ""
        school_phone = ""
        school_email = ""

        try:
            from django.db import connection
            if hasattr(connection, 'tenant'):
                tenant = connection.tenant
                school_name = tenant.name
                school_address = getattr(tenant, 'address', '')
                school_phone = getattr(tenant, 'phone', '')
                school_email = getattr(tenant, 'email', '')

                # Encode logo as base64
                if hasattr(tenant, 'logo') and tenant.logo:
                    try:
                        with tenant.logo.open('rb') as f:
                            school_logo_base64 = base64.b64encode(f.read()).decode('utf-8')
                    except Exception as e:
                        logger.warning(f"Could not load school logo: {e}")
        except Exception as e:
            logger.warning(f"Error getting tenant info: {e}")

        # Build context
        context = {
            'invoice': invoice,
            'items': invoice.items.all(),
            'payments': invoice.payments.filter(status='COMPLETED'),
            'school_name': school_name,
            'school_logo_base64': school_logo_base64,
            'school_address': school_address,
            'school_phone': school_phone,
            'school_email': school_email,
            'generated_at': timezone.now(),
        }

        # Render HTML
        html_string = render_to_string('finance/invoice_pdf.html', context)

        # Generate PDF
        pdf_buffer = BytesIO()
        HTML(string=html_string).write_pdf(pdf_buffer)
        pdf_buffer.seek(0)

        return pdf_buffer


# =============================================================================
# NOTIFICATION TASKS
# =============================================================================

@shared_task(bind=True, max_retries=TASK_MAX_RETRIES, default_retry_delay=TASK_RETRY_DELAY)
def send_invoice_notification(self, invoice_id, notification_type, distribution_type, tenant_schema, sent_by_id=None, custom_sms=None):
    """
    Send notification for a single invoice via email and/or SMS.

    Args:
        invoice_id: UUID of the Invoice
        notification_type: 'INVOICE_ISSUED', 'PAYMENT_RECEIVED', 'OVERDUE_REMINDER', 'BALANCE_REMINDER'
        distribution_type: 'EMAIL', 'SMS', or 'BOTH'
        tenant_schema: Schema name for tenant context
        sent_by_id: ID of the user who initiated the notification
        custom_sms: Optional custom SMS message template

    Retries up to 3 times with exponential backoff for transient failures.
    """
    from django_tenants.utils import schema_context
    from smtplib import SMTPException
    from socket import error as SocketError
    import ssl

    # Transient errors that should trigger retry
    RETRYABLE_EXCEPTIONS = (SMTPException, SocketError, ssl.SSLError, ConnectionError, TimeoutError)

    with schema_context(tenant_schema):
        from .models import Invoice, FinanceNotificationLog
        from django.contrib.auth import get_user_model

        User = get_user_model()

        try:
            invoice = Invoice.objects.select_related(
                'student', 'student__current_class', 'term', 'academic_year'
            ).get(pk=invoice_id)
        except Invoice.DoesNotExist:
            logger.error(f"Invoice {invoice_id} not found")
            return {'success': False, 'error': 'Invoice not found'}

        student = invoice.student
        sent_by = None
        if sent_by_id:
            try:
                sent_by = User.objects.get(pk=sent_by_id)
            except User.DoesNotExist:
                pass

        # Create notification log
        log = FinanceNotificationLog.objects.create(
            invoice=invoice,
            notification_type=notification_type,
            distribution_type=distribution_type,
            sent_by=sent_by,
        )

        # Get guardian contact info
        primary_guardian = student.get_primary_guardian() if hasattr(student, 'get_primary_guardian') else None
        guardian_email = primary_guardian.email if primary_guardian and primary_guardian.email else None
        guardian_phone = primary_guardian.phone_number if primary_guardian else None

        # Fallback to legacy fields if available
        if not guardian_email:
            guardian_email = getattr(student, 'guardian_email', None)
        if not guardian_phone:
            guardian_phone = getattr(student, 'guardian_phone', None)

        results = {'email': None, 'sms': None}
        context = build_invoice_context(invoice)

        # Warn if no contact info available for the requested distribution type
        if distribution_type in ('EMAIL', 'BOTH') and not guardian_email:
            logger.warning(f"No guardian email for student {student.full_name} (invoice {invoice_id})")
            log.email_status = 'FAILED'
            log.email_error = 'No guardian email address available'
            results['email'] = 'skipped: no email'
        if distribution_type in ('SMS', 'BOTH') and not guardian_phone:
            logger.warning(f"No guardian phone for student {student.full_name} (invoice {invoice_id})")
            log.sms_status = 'FAILED'
            log.sms_error = 'No guardian phone number available'
            results['sms'] = 'skipped: no phone'

        # Send Email
        if distribution_type in ('EMAIL', 'BOTH') and guardian_email:
            try:
                # Generate PDF
                pdf_buffer = generate_invoice_pdf(invoice, tenant_schema)

                # Prepare email
                notification_subjects = {
                    'INVOICE_ISSUED': f"Invoice #{invoice.invoice_number} - {student.full_name}",
                    'PAYMENT_RECEIVED': f"Payment Confirmation - {student.full_name}",
                    'OVERDUE_REMINDER': f"Overdue Notice - Invoice #{invoice.invoice_number}",
                    'BALANCE_REMINDER': f"Fee Reminder - {student.full_name}",
                }
                subject = notification_subjects.get(notification_type, f"Invoice #{invoice.invoice_number}")

                email_context = {
                    **context,
                    'notification_type': notification_type,
                }
                html_message = render_to_string('finance/emails/invoice_email.html', email_context)

                email = EmailMessage(
                    subject=subject,
                    body=html_message,
                    from_email=get_from_email(),
                    to=[guardian_email],
                )
                email.content_subtype = 'html'
                email.attach(
                    f"invoice_{invoice.invoice_number}.pdf",
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
                logger.warning(f"Retryable error sending email for invoice {invoice_id}: {str(e)}")
                log.email_status = 'FAILED'
                log.email_error = f"Retry {self.request.retries + 1}: {str(e)[:450]}"
                log.save()
                raise self.retry(exc=e, countdown=TASK_RETRY_DELAY * (2 ** self.request.retries))

            except Exception as e:
                logger.error(f"Failed to send email for invoice {invoice_id}: {str(e)}")
                log.email_status = 'FAILED'
                log.email_error = str(e)[:500]
                results['email'] = f'failed: {str(e)}'

        # Send SMS
        if distribution_type in ('SMS', 'BOTH') and guardian_phone:
            try:
                from communications.utils import send_sms_sync
                from communications.models import SMSMessage

                # Map notification type to SMS template key
                template_map = {
                    'INVOICE_ISSUED': 'invoice_issued',
                    'PAYMENT_RECEIVED': 'payment_received',
                    'OVERDUE_REMINDER': 'overdue_reminder',
                    'BALANCE_REMINDER': 'balance_reminder',
                }
                template_key = template_map.get(notification_type, 'balance_reminder')
                sms_text = render_sms_template(template_key, context, custom_template=custom_sms)

                # Create SMS record
                sms_record = SMSMessage.objects.create(
                    recipient_phone=guardian_phone,
                    recipient_name=context.get('guardian_name', ''),
                    student=student,
                    message=sms_text,
                    message_type=SMSMessage.MessageType.FEE_REMINDER,
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
                logger.warning(f"Retryable error sending SMS for invoice {invoice_id}: {str(e)}")
                log.sms_status = 'FAILED'
                log.sms_error = f"Retry {self.request.retries + 1}: {str(e)[:450]}"
                log.save()
                raise self.retry(exc=e, countdown=TASK_RETRY_DELAY * (2 ** self.request.retries))

            except Exception as e:
                logger.error(f"Failed to send SMS for invoice {invoice_id}: {str(e)}")
                log.sms_status = 'FAILED'
                log.sms_error = str(e)[:500]
                results['sms'] = f'failed: {str(e)}'

        log.save()

        return {
            'success': True,
            'invoice_id': str(invoice_id),
            'invoice_number': invoice.invoice_number,
            'results': results,
            'log_id': str(log.id),
        }


@shared_task(bind=True, max_retries=TASK_MAX_RETRIES, default_retry_delay=TASK_RETRY_DELAY)
def send_bulk_notifications(self, notification_type, distribution_type, tenant_schema, sent_by_id=None, filters=None, custom_sms=None):
    """
    Send notifications for multiple invoices.

    Args:
        notification_type: 'OVERDUE_REMINDER', 'BALANCE_REMINDER'
        distribution_type: 'EMAIL', 'SMS', or 'BOTH'
        tenant_schema: Schema name for tenant context
        sent_by_id: ID of the user who initiated
        filters: Dict with filters like {'status': 'OVERDUE', 'class_id': 1}
        custom_sms: Optional custom SMS message template

    Queues individual send_invoice_notification tasks for each invoice.
    """
    from django_tenants.utils import schema_context

    with schema_context(tenant_schema):
        from .models import Invoice

        # Base query - only invoices with balance
        invoices = Invoice.objects.filter(
            balance__gt=0,
            status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']
        ).select_related('student', 'student__current_class')

        # Apply filters (only allow known safe keys)
        ALLOWED_STATUSES = {'ISSUED', 'PARTIALLY_PAID', 'OVERDUE'}
        if filters:
            status = filters.get('status')
            if status and status in ALLOWED_STATUSES:
                invoices = invoices.filter(status=status)
            class_id = filters.get('class_id')
            if class_id:
                try:
                    invoices = invoices.filter(student__current_class_id=int(class_id))
                except (ValueError, TypeError):
                    pass
            student_ids = filters.get('student_ids')
            if student_ids and isinstance(student_ids, list):
                invoices = invoices.filter(student_id__in=student_ids)

        # Queue individual tasks (limit batch size to prevent queue flooding)
        MAX_BATCH = 500
        queued_count = 0
        for invoice in invoices.iterator():
            if queued_count >= MAX_BATCH:
                logger.warning(f"Bulk notification batch limit ({MAX_BATCH}) reached, remaining invoices skipped")
                break
            send_invoice_notification.delay(
                invoice_id=str(invoice.pk),
                notification_type=notification_type,
                distribution_type=distribution_type,
                tenant_schema=tenant_schema,
                sent_by_id=sent_by_id,
                custom_sms=custom_sms,
            )
            queued_count += 1

        logger.info(f"Queued {queued_count} invoice notifications")
        return {
            'success': True,
            'queued_count': queued_count,
        }


@shared_task(bind=True, max_retries=TASK_MAX_RETRIES, default_retry_delay=TASK_RETRY_DELAY)
def send_payment_confirmation_sms(self, payment_id, tenant_schema):
    """
    Send SMS confirmation to guardian after a successful payment.

    Args:
        payment_id: UUID of the Payment
        tenant_schema: Schema name for tenant context
    """
    from django_tenants.utils import schema_context

    with schema_context(tenant_schema):
        from .models import Payment, FinanceNotificationLog
        from communications.utils import send_sms_sync
        from communications.models import SMSMessage

        try:
            payment = Payment.objects.select_related(
                'invoice__student', 'invoice__term', 'invoice__academic_year'
            ).get(pk=payment_id)
        except Payment.DoesNotExist:
            logger.error(f"Payment {payment_id} not found for confirmation SMS")
            return {'success': False, 'error': 'Payment not found'}

        invoice = payment.invoice
        student = invoice.student

        # Get guardian phone
        primary_guardian = student.get_primary_guardian() if hasattr(student, 'get_primary_guardian') else None
        guardian_phone = primary_guardian.phone_number if primary_guardian else None
        if not guardian_phone:
            guardian_phone = getattr(student, 'guardian_phone', None)

        if not guardian_phone:
            logger.warning(f"No guardian phone for student {student.full_name} (payment {payment_id})")
            return {'success': False, 'error': 'No guardian phone number'}

        # Build and render SMS
        context = build_payment_context(payment)
        sms_text = render_sms_template('payment_received', context)

        try:
            # Create SMS record
            sms_record = SMSMessage.objects.create(
                recipient_phone=guardian_phone,
                recipient_name=context.get('guardian_name', ''),
                student=student,
                message=sms_text,
                message_type=SMSMessage.MessageType.FEE_REMINDER,
                status=SMSMessage.Status.PENDING,
            )

            # Send synchronously
            sms_result = send_sms_sync(guardian_phone, sms_text)

            # Create notification log
            log = FinanceNotificationLog.objects.create(
                invoice=invoice,
                notification_type='PAYMENT_RECEIVED',
                distribution_type='SMS',
            )

            if sms_result.get('success'):
                log.sms_status = 'SENT'
                log.sms_sent_to = guardian_phone
                log.sms_sent_at = timezone.now()
                log.sms_message = sms_record
                sms_record.mark_sent(sms_result.get('response', ''))
                log.save()
                return {'success': True, 'payment_id': str(payment_id)}
            else:
                log.sms_status = 'FAILED'
                log.sms_error = sms_result.get('error', 'Unknown error')[:500]
                sms_record.mark_failed(sms_result.get('error', ''))
                log.save()
                return {'success': False, 'error': sms_result.get('error')}

        except Exception as e:
            logger.error(f"Failed to send payment confirmation SMS for {payment_id}: {e}")
            return {'success': False, 'error': str(e)}
