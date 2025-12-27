import logging
import requests
from base64 import b64encode
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django_tenants.utils import schema_context
from django.conf import settings

logger = logging.getLogger(__name__)

# Lazy initialization of SMS clients
_africastalking_client = None

# Hubtel API endpoint (Quick Send)
HUBTEL_API_URL = "https://smsc.hubtel.com/v1/messages/send"


def get_africastalking_client():
    """Lazily initialize Africa's Talking SMS client."""
    global _africastalking_client
    if _africastalking_client is None:
        import africastalking
        africastalking.initialize(settings.AT_USERNAME, settings.AT_API_KEY)
        _africastalking_client = africastalking.SMS
    return _africastalking_client


def send_via_hubtel(recipient, message, sender_id=None):
    """Send SMS via Hubtel Quick Send API."""
    # Format phone number for Hubtel (with country code, no +)
    if recipient.startswith('+'):
        recipient = recipient[1:]  # Remove + prefix
    elif recipient.startswith('0'):
        recipient = '233' + recipient[1:]  # Convert 0xx to 233xx

    # Use provided sender_id or fall back to settings
    sender = sender_id or settings.HUBTEL_SENDER_ID or 'SchoolSMS'

    # Quick Send API uses query parameters
    params = {
        "clientsecret": settings.HUBTEL_CLIENT_SECRET,
        "clientid": settings.HUBTEL_CLIENT_ID,
        "from": sender,
        "to": recipient,
        "content": message
    }

    response = requests.get(HUBTEL_API_URL, params=params)
    response.raise_for_status()

    return response.json()


def send_via_africastalking(recipient, message):
    """Send SMS via Africa's Talking."""
    client = get_africastalking_client()
    if client is None:
        raise ValueError("Africa's Talking client failed to initialize")

    response = client.send(message, [recipient], sender_id=settings.AT_SENDER_ID)
    return response


def get_school_sender_id():
    """Get sender ID from school settings (max 11 chars for Hubtel)."""
    try:
        from core.models import SchoolSettings
        school = SchoolSettings.load()
        # Use short_name or first 11 chars of display_name
        if school:
            name = school.display_name or ''
            # Remove spaces and special chars, limit to 11 chars
            sender = ''.join(c for c in name if c.isalnum())[:11]
            return sender if sender else None
    except Exception:
        pass
    return None


@shared_task(bind=True, max_retries=3, default_retry_delay=60, autoretry_for=(Exception,))
def send_communication_task(self, schema_name, recipient, message):
    """
    Send SMS message with retry logic for transient failures.

    Args:
        schema_name: The tenant schema to operate under
        recipient: Phone number in E.164 format
        message: SMS message content
    """
    with schema_context(schema_name):
        try:
            backend = settings.SMS_BACKEND

            # Get school name as sender ID
            sender_id = get_school_sender_id()

            if backend == 'hubtel':
                response = send_via_hubtel(recipient, message, sender_id=sender_id)
                logger.info(f"Hubtel SMS sent to {recipient}: {response}")
                return {"status": "sent", "provider": "hubtel", "response": str(response)}

            elif backend == 'africastalking':
                response = send_via_africastalking(recipient, message)
                logger.info(f"Africa's Talking SMS sent to {recipient}: {response}")
                return {"status": "sent", "provider": "africastalking", "response": str(response)}

            else:
                # Console backend for development
                logger.info(f"CONSOLE SMS to {recipient}: {message}")
                return {"status": "logged", "provider": "console"}

        except MaxRetriesExceededError:
            logger.error(f"SMS to {recipient} failed after {self.max_retries} retries")
            return {"status": "failed", "error": "Max retries exceeded"}
        except Exception as e:
            logger.error(f"SMS Error to {recipient}: {e}")
            # Re-raise to trigger retry (handled by autoretry_for)
            raise
