import re
import logging
from django.db import connection
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def get_sms_gateway_status():
    """
    Check if SMS gateway is properly configured and enabled.

    Returns:
        dict: Status with keys:
            - enabled: bool - Whether SMS is enabled in settings
            - configured: bool - Whether API key is set (for non-console backends)
            - backend: str - The SMS backend being used
            - sender_id: str - The configured sender ID
            - message: str - Human-readable status message
    """
    try:
        from core.models import SchoolSettings
        school = SchoolSettings.load()

        if not school:
            return {
                'enabled': False,
                'configured': False,
                'backend': 'none',
                'sender_id': '',
                'message': 'School settings not configured',
            }

        backend = school.sms_backend or 'console'
        sender_id = school.sms_sender_id or ''
        api_key = school.sms_api_key or ''
        sms_enabled = school.sms_enabled

        # Check if properly configured
        if backend == 'console':
            # Console backend is always "configured" (for testing)
            configured = True
            if sms_enabled:
                message = 'SMS is in test mode (console)'
            else:
                message = 'SMS is disabled'
        else:
            # Real backends need API key
            configured = bool(api_key)
            if not sms_enabled:
                message = 'SMS is disabled'
            elif not configured:
                message = f'{backend.title()} API key not configured'
            else:
                message = f'SMS enabled via {backend.title()}'

        return {
            'enabled': sms_enabled,
            'configured': configured,
            'backend': backend,
            'sender_id': sender_id,
            'message': message,
            'ready': sms_enabled and configured,
        }

    except Exception as e:
        logger.warning(f"Could not check SMS gateway status: {e}")
        return {
            'enabled': False,
            'configured': False,
            'backend': 'none',
            'sender_id': '',
            'message': 'Error checking SMS configuration',
            'ready': False,
        }

# E.164 phone number pattern (international format)
E164_PATTERN = re.compile(r'^\+[1-9]\d{1,14}$')

# Maximum SMS length (standard GSM-7 encoding)
MAX_SMS_LENGTH = 160


def normalize_phone_number(phone):
    """
    Normalize phone number to E.164 format for Ghana.

    Args:
        phone: Phone number string in various formats

    Returns:
        Normalized phone number in E.164 format (+233XXXXXXXXX)
    """
    if not phone:
        return None

    # Strip whitespace and common separators
    phone = re.sub(r'[\s\-\.\(\)]', '', phone.strip())

    # Already in E.164 format
    if phone.startswith('+'):
        return phone

    # Ghana local format (0XX XXX XXXX)
    if phone.startswith('0') and len(phone) == 10:
        return '+233' + phone[1:]

    # Ghana format without leading zero (233XXXXXXXXX)
    if phone.startswith('233') and len(phone) == 12:
        return '+' + phone

    # Assume Ghana number without prefix
    if len(phone) == 9 and phone[0] in '235':
        return '+233' + phone

    # Return as-is with + prefix
    return '+' + phone if not phone.startswith('+') else phone


def validate_phone_number(phone):
    """
    Validate phone number is in E.164 format.

    Args:
        phone: Phone number string

    Returns:
        Cleaned phone number

    Raises:
        ValidationError: If phone number is invalid
    """
    if not phone:
        raise ValidationError("Phone number is required")

    # Normalize first
    phone = normalize_phone_number(phone)

    if not E164_PATTERN.match(phone):
        raise ValidationError(
            f"Invalid phone number format: {phone}. "
            "Must be in E.164 format (e.g., +233541234567)"
        )

    return phone


def send_sms(to_phone, message, student=None, message_type='general', created_by=None):
    """
    Queue an SMS message for delivery.

    Args:
        to_phone: Phone number (will be normalized to E.164)
        message: SMS message content
        student: Optional Student instance to link message to
        message_type: Type of message (general, attendance, fee, announcement, report)
        created_by: Optional User who initiated the send

    Returns:
        dict: Result with 'success', 'message_id', 'error' keys

    Note:
        This queues the message for async delivery via Celery.
    """
    from .tasks import send_communication_task
    from .models import SMSMessage

    try:
        # Normalize and validate phone number
        validated_phone = normalize_phone_number(to_phone)
        if not validated_phone:
            return {'success': False, 'error': 'Phone number is required'}

        if not E164_PATTERN.match(validated_phone):
            return {'success': False, 'error': f'Invalid phone number: {to_phone}'}

        # Warn about long messages (but don't block)
        if len(message) > MAX_SMS_LENGTH:
            logger.warning(
                f"SMS message exceeds {MAX_SMS_LENGTH} chars ({len(message)} chars). "
                "Message may be split into multiple parts."
            )

        # Create SMSMessage record for tracking
        sms_record = SMSMessage.objects.create(
            recipient_phone=validated_phone,
            recipient_name=student.guardian_name if student else '',
            student=student,
            message=message,
            message_type=message_type,
            status=SMSMessage.Status.PENDING,
            created_by=created_by,
        )

        # Queue the Celery task with SMS record ID for status updates
        send_communication_task.delay(
            connection.schema_name,
            validated_phone,
            message,
            sms_record_id=str(sms_record.pk)
        )

        return {
            'success': True,
            'message_id': sms_record.pk,
            'phone': validated_phone,
        }

    except Exception as e:
        logger.error(f"Failed to queue SMS to {to_phone}: {e}")
        return {'success': False, 'error': str(e)}


def send_sms_sync(to_phone, message, sender_id=None, api_key=None):
    """
    Send SMS synchronously (blocking). Use within Celery tasks.

    Args:
        to_phone: Phone number (will be normalized)
        message: SMS message content
        sender_id: Optional sender ID override
        api_key: Optional API key override

    Returns:
        dict: Result with 'success', 'response', 'error' keys
    """
    from .tasks import get_school_sms_settings, send_via_arkesel, send_via_hubtel, send_via_africastalking

    try:
        # Normalize phone
        validated_phone = normalize_phone_number(to_phone)
        if not validated_phone:
            return {'success': False, 'error': 'Invalid phone number'}

        # Get settings
        sms_settings = get_school_sms_settings()

        if not sms_settings['enabled']:
            logger.info(f"[SMS DISABLED] Message to {validated_phone} not sent")
            return {'success': False, 'error': 'SMS not enabled for this school'}

        backend = sms_settings['backend']
        sender = sender_id or sms_settings['sender_id']
        key = api_key or sms_settings['api_key']

        if backend == 'arkesel':
            if not key:
                return {'success': False, 'error': 'Arkesel API key not configured'}
            response = send_via_arkesel(validated_phone, message, sender_id=sender, api_key=key)
            return {'success': True, 'response': response, 'provider': 'arkesel'}

        elif backend == 'hubtel':
            if not key:
                return {'success': False, 'error': 'Hubtel API key not configured'}
            response = send_via_hubtel(validated_phone, message, sender_id=sender, api_key=key)
            return {'success': True, 'response': response, 'provider': 'hubtel'}

        elif backend == 'africastalking':
            if not key:
                return {'success': False, 'error': "Africa's Talking API key not configured"}
            response = send_via_africastalking(validated_phone, message, sender_id=sender, api_key=key)
            return {'success': True, 'response': response, 'provider': 'africastalking'}

        else:
            # Console backend
            logger.info(f"[CONSOLE SMS] To: {validated_phone}, From: {sender}, Message: {message}")
            return {'success': True, 'response': 'logged', 'provider': 'console'}

    except Exception as e:
        logger.error(f"SMS send error to {to_phone}: {e}")
        return {'success': False, 'error': str(e)}