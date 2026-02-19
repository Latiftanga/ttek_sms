import logging
import requests
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)

# API endpoints
ARKESEL_API_URL = "https://sms.arkesel.com/api/v2/sms/send"
HUBTEL_API_URL = "https://smsc.hubtel.com/v1/messages/send"
AT_API_URL = "https://api.africastalking.com/version1/messaging"
AT_SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"


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
    Send SMS via Africa's Talking REST API (no SDK, avoids global state).
    API Documentation: https://africastalking.com/docs/sms
    API key format: "username:api_key"
    """
    if not api_key:
        raise ValueError("Africa's Talking API key is required")

    if ':' not in api_key:
        raise ValueError("Africa's Talking API key must be in format 'username:api_key'")

    username, at_api_key = api_key.split(':', 1)

    recipient = format_phone_ghana(recipient)
    if not recipient.startswith('+'):
        recipient = '+' + recipient

    sender = sender_id[:11] if sender_id else None
    api_url = AT_SANDBOX_URL if username == 'sandbox' else AT_API_URL

    headers = {
        'apiKey': at_api_key,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
    }

    payload = {
        'username': username,
        'to': recipient,
        'message': message,
    }
    if sender:
        payload['from'] = sender

    response = requests.post(api_url, data=payload, headers=headers, timeout=30)
    response.raise_for_status()

    result = response.json()
    recipients = result.get('SMSMessageData', {}).get('Recipients', [])
    if recipients:
        recipient_data = recipients[0]
        if recipient_data.get('status') == 'Success':
            return result
        raise ValueError(
            f"Africa's Talking error: {recipient_data.get('status')}"
        )

    raise ValueError("Africa's Talking: No recipients in response")


def get_school_sms_settings():
    """
    Get SMS settings from SchoolSettings model.

    Returns:
        dict: SMS configuration with keys: backend, api_key, sender_id, enabled
    """
    try:
        from django.db import connection
        from core.models import SchoolSettings
        settings = SchoolSettings.load()
        if settings:
            # Use configured sender_id or derive from school name
            sender_id = settings.sms_sender_id
            if not sender_id:
                tenant = getattr(connection, 'tenant', None)
                if tenant and tenant.display_name:
                    sender_id = ''.join(c for c in tenant.display_name if c.isalnum())[:11]

            return {
                'backend': settings.sms_backend or 'console',
                'api_key': settings.sms_api_key or '',
                'sender_id': sender_id or 'SchoolSMS',
                'enabled': settings.sms_enabled,
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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_communication_task(self, schema_name, recipient, message, sms_record_id=None):
    """
    Send SMS message with retry logic for transient failures.

    Args:
        schema_name: The tenant schema to operate under
        recipient: Phone number in E.164 format
        message: SMS message content
        sms_record_id: Optional UUID of SMSMessage record to update status
    """
    with schema_context(schema_name):
        # Get SMSMessage record if ID provided
        sms_record = None
        if sms_record_id:
            try:
                from .models import SMSMessage
                sms_record = SMSMessage.objects.get(pk=sms_record_id)
            except Exception as e:
                logger.warning(f"Could not load SMSMessage {sms_record_id}: {e}")

        try:
            # Get school-specific SMS settings
            sms_settings = get_school_sms_settings()

            # Check if SMS is enabled for this school
            if not sms_settings['enabled']:
                logger.info(f"[SMS DISABLED] SMS not enabled for this school. Message to {recipient} not sent.")
                if sms_record:
                    sms_record.mark_failed("SMS not enabled for this school")
                return {"status": "disabled", "message": "SMS not enabled for this school"}

            backend = sms_settings['backend']
            sender_id = sms_settings['sender_id']
            api_key = sms_settings['api_key']

            response = None

            if backend == 'arkesel':
                if not api_key:
                    raise ValueError("Arkesel API key not configured for this school")
                response = send_via_arkesel(recipient, message, sender_id=sender_id, api_key=api_key)
                logger.info(f"Arkesel SMS sent to {recipient}: {response}")

            elif backend == 'hubtel':
                if not api_key:
                    raise ValueError("Hubtel API key not configured for this school")
                response = send_via_hubtel(recipient, message, sender_id=sender_id, api_key=api_key)
                logger.info(f"Hubtel SMS sent to {recipient}: {response}")

            elif backend == 'africastalking':
                if not api_key:
                    raise ValueError("Africa's Talking API key not configured for this school")
                response = send_via_africastalking(recipient, message, sender_id=sender_id, api_key=api_key)
                logger.info(f"Africa's Talking SMS sent to {recipient}: {response}")

            else:
                # Console backend for development
                logger.info(f"[CONSOLE SMS] To: {recipient}")
                logger.info(f"[CONSOLE SMS] From: {sender_id}")
                logger.info(f"[CONSOLE SMS] Message: {message}")
                if sms_record:
                    sms_record.mark_sent("Console: logged only")
                return {"status": "logged", "provider": "console"}

            # Mark as sent if we have a record
            if sms_record:
                sms_record.mark_sent(str(response) if response else '')

            return {"status": "sent", "provider": backend, "response": str(response)}

        except Exception as e:
            logger.error(f"SMS Error to {recipient}: {e}")
            if self.request.retries >= self.max_retries:
                # Final retry exhausted — mark as failed
                if sms_record:
                    sms_record.mark_failed(str(e))
                return {"status": "failed", "error": str(e)}
            # Retry with backoff
            try:
                raise self.retry(exc=e)
            except MaxRetriesExceededError:
                if sms_record:
                    sms_record.mark_failed("Max retries exceeded")
                return {"status": "failed", "error": "Max retries exceeded"}
