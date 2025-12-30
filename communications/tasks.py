import logging
import requests
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)

# API endpoints
ARKESEL_API_URL = "https://sms.arkesel.com/api/v2/sms/send"
HUBTEL_API_URL = "https://smsc.hubtel.com/v1/messages/send"


def format_phone_ghana(phone):
    """Format phone number to Ghana international format (233XXXXXXXXX)."""
    phone = phone.strip()
    if phone.startswith('+'):
        phone = phone[1:]
    elif phone.startswith('0'):
        phone = '233' + phone[1:]
    return phone


def send_via_arkesel(recipient, message, sender_id=None, api_key=None):
    """
    Send SMS via Arkesel API v2.
    API Documentation: https://developers.arkesel.com/
    """
    if not api_key:
        raise ValueError("Arkesel API key is required")

    recipient = format_phone_ghana(recipient)
    sender = (sender_id or 'SchoolSMS')[:11]

    headers = {
        'api-key': api_key,
        'Content-Type': 'application/json',
    }

    payload = {
        'sender': sender,
        'message': message,
        'recipients': [recipient],
    }

    response = requests.post(ARKESEL_API_URL, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    result = response.json()
    if result.get('status') != 'success':
        raise ValueError(f"Arkesel API error: {result.get('message', 'Unknown error')}")

    return result


def send_via_hubtel(recipient, message, sender_id=None, api_key=None):
    """
    Send SMS via Hubtel API.
    API Documentation: https://developers.hubtel.com/
    API key format: "client_id:client_secret"
    """
    if not api_key:
        raise ValueError("Hubtel API key is required")

    # Parse client_id and client_secret from api_key
    if ':' not in api_key:
        raise ValueError("Hubtel API key must be in format 'client_id:client_secret'")

    recipient = format_phone_ghana(recipient)
    sender = (sender_id or 'SchoolSMS')[:11]

    params = {
        'From': sender,
        'To': recipient,
        'Content': message,
    }

    response = requests.get(
        HUBTEL_API_URL,
        params=params,
        auth=tuple(api_key.split(':', 1)),
        timeout=30
    )
    response.raise_for_status()

    result = response.json()
    if result.get('status') != 0:
        raise ValueError(f"Hubtel API error: {result.get('message', 'Unknown error')}")

    return result


def send_via_africastalking(recipient, message, sender_id=None, api_key=None):
    """
    Send SMS via Africa's Talking API.
    API Documentation: https://africastalking.com/docs/sms
    API key format: "username:api_key"
    """
    if not api_key:
        raise ValueError("Africa's Talking API key is required")

    # Parse username and api_key
    if ':' not in api_key:
        raise ValueError("Africa's Talking API key must be in format 'username:api_key'")

    username, at_api_key = api_key.split(':', 1)

    try:
        import africastalking
        africastalking.initialize(username, at_api_key)
        sms = africastalking.SMS

        recipient = format_phone_ghana(recipient)
        if not recipient.startswith('+'):
            recipient = '+' + recipient

        sender = sender_id[:11] if sender_id else None

        # Send message
        response = sms.send(message, [recipient], sender_id=sender)

        # Check response
        if response.get('SMSMessageData', {}).get('Recipients'):
            recipient_data = response['SMSMessageData']['Recipients'][0]
            if recipient_data.get('status') == 'Success':
                return response
            raise ValueError(f"Africa's Talking error: {recipient_data.get('status')}")

        raise ValueError("Africa's Talking: No recipients in response")

    except ImportError:
        raise ValueError("africastalking package not installed")


def get_school_sms_settings():
    """
    Get SMS settings from SchoolSettings model.

    Returns:
        dict: SMS configuration with keys: backend, api_key, sender_id, enabled
    """
    try:
        from core.models import SchoolSettings
        school = SchoolSettings.load()
        if school:
            # Use configured sender_id or derive from school name
            sender_id = school.sms_sender_id
            if not sender_id and school.display_name:
                # Fallback: derive from school name (alphanumeric, max 11 chars)
                sender_id = ''.join(c for c in school.display_name if c.isalnum())[:11]

            return {
                'backend': school.sms_backend or 'console',
                'api_key': school.sms_api_key or '',
                'sender_id': sender_id or 'SchoolSMS',
                'enabled': school.sms_enabled,
            }
    except Exception as e:
        logger.warning(f"Could not load school SMS settings: {e}")

    # Default fallback
    return {
        'backend': 'console',
        'api_key': '',
        'sender_id': 'SchoolSMS',
        'enabled': False,
    }


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
            # Get school-specific SMS settings
            sms_settings = get_school_sms_settings()

            # Check if SMS is enabled for this school
            if not sms_settings['enabled']:
                logger.info(f"[SMS DISABLED] SMS not enabled for this school. Message to {recipient} not sent.")
                return {"status": "disabled", "message": "SMS not enabled for this school"}

            backend = sms_settings['backend']
            sender_id = sms_settings['sender_id']

            api_key = sms_settings['api_key']

            if backend == 'arkesel':
                if not api_key:
                    raise ValueError("Arkesel API key not configured for this school")
                response = send_via_arkesel(recipient, message, sender_id=sender_id, api_key=api_key)
                logger.info(f"Arkesel SMS sent to {recipient}: {response}")
                return {"status": "sent", "provider": "arkesel", "response": str(response)}

            elif backend == 'hubtel':
                if not api_key:
                    raise ValueError("Hubtel API key not configured for this school")
                response = send_via_hubtel(recipient, message, sender_id=sender_id, api_key=api_key)
                logger.info(f"Hubtel SMS sent to {recipient}: {response}")
                return {"status": "sent", "provider": "hubtel", "response": str(response)}

            elif backend == 'africastalking':
                if not api_key:
                    raise ValueError("Africa's Talking API key not configured for this school")
                response = send_via_africastalking(recipient, message, sender_id=sender_id, api_key=api_key)
                logger.info(f"Africa's Talking SMS sent to {recipient}: {response}")
                return {"status": "sent", "provider": "africastalking", "response": str(response)}

            else:
                # Console backend for development
                logger.info(f"[CONSOLE SMS] To: {recipient}")
                logger.info(f"[CONSOLE SMS] From: {sender_id}")
                logger.info(f"[CONSOLE SMS] Message: {message}")
                return {"status": "logged", "provider": "console"}

        except MaxRetriesExceededError:
            logger.error(f"SMS to {recipient} failed after {self.max_retries} retries")
            return {"status": "failed", "error": "Max retries exceeded"}
        except Exception as e:
            logger.error(f"SMS Error to {recipient}: {e}")
            # Re-raise to trigger retry (handled by autoretry_for)
            raise
