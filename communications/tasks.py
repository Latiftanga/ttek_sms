import logging
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django_tenants.utils import schema_context
from django.conf import settings

logger = logging.getLogger(__name__)

# Lazy initialization of SMS client
_sms_client = None


def get_sms_client():
    """Lazily initialize and return the SMS client"""
    global _sms_client
    if _sms_client is None and settings.SMS_BACKEND == 'africastalking':
        import africastalking
        africastalking.initialize(settings.AT_USERNAME, settings.AT_API_KEY)
        _sms_client = africastalking.SMS
    return _sms_client


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
            if settings.SMS_BACKEND == 'africastalking':
                sms_client = get_sms_client()
                if sms_client is None:
                    raise ValueError("SMS backend is africastalking but client failed to initialize")
                response = sms_client.send(message, [recipient], sender_id=settings.AT_SENDER_ID)
                logger.info(f"SMS sent to {recipient}: {response}")
                return {"status": "sent", "provider": "africastalking", "response": str(response)}
            else:
                logger.info(f"CONSOLE SMS to {recipient}: {message}")
                return {"status": "logged", "provider": "console"}
        except MaxRetriesExceededError:
            logger.error(f"SMS to {recipient} failed after {self.max_retries} retries")
            return {"status": "failed", "error": "Max retries exceeded"}
        except Exception as e:
            logger.error(f"SMS Error to {recipient}: {e}")
            # Re-raise to trigger retry (handled by autoretry_for)
            raise