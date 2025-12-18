import re
import logging
from django.db import connection
from django.core.exceptions import ValidationError
from .tasks import send_communication_task

logger = logging.getLogger(__name__)

# E.164 phone number pattern (international format)
E164_PATTERN = re.compile(r'^\+[1-9]\d{1,14}$')

# Maximum SMS length (standard GSM-7 encoding)
MAX_SMS_LENGTH = 160


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

    # Strip whitespace
    phone = phone.strip()

    if not E164_PATTERN.match(phone):
        raise ValidationError(
            f"Invalid phone number format: {phone}. "
            "Must be in E.164 format (e.g., +233541234567)"
        )

    return phone


def send_sms(to_phone, message):
    """
    Queue an SMS message for delivery.

    Args:
        to_phone: Phone number in E.164 format (e.g., +233541234567)
        message: SMS message content

    Returns:
        AsyncResult: Celery task result object for tracking

    Raises:
        ValidationError: If phone number is invalid
    """
    # Validate phone number
    validated_phone = validate_phone_number(to_phone)

    # Warn about long messages (but don't block)
    if len(message) > MAX_SMS_LENGTH:
        logger.warning(
            f"SMS message exceeds {MAX_SMS_LENGTH} chars ({len(message)} chars). "
            "Message may be split into multiple parts."
        )

    # Pass current schema to Celery so it knows which school sent it
    return send_communication_task.delay(connection.schema_name, validated_phone, message)