"""
Tenant-aware email backend for multi-tenant Django application.

This backend allows each tenant (school) to configure their own SMTP settings.
When a school has email_enabled=True, it uses the school's SMTP configuration.
Otherwise, it falls back to Django's global email settings.
"""
import logging

from django.conf import settings as django_settings
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend
from django.core.mail.backends.console import EmailBackend as ConsoleBackend

logger = logging.getLogger(__name__)


def get_from_email():
    """
    Get the appropriate 'from' email address for the current tenant.
    Returns school's configured email if enabled, otherwise global default.
    """
    from django.db import connection

    # Use global default for public schema
    if connection.schema_name == 'public':
        return django_settings.DEFAULT_FROM_EMAIL

    try:
        from core.models import SchoolSettings
        school_settings = SchoolSettings.load()

        if school_settings.email_enabled and school_settings.email_from_address:
            # Format with display name if available
            if school_settings.email_from_name:
                return f'"{school_settings.email_from_name}" <{school_settings.email_from_address}>'
            return school_settings.email_from_address
    except Exception as e:
        logger.warning(f"Failed to get tenant from email: {e}")

    return django_settings.DEFAULT_FROM_EMAIL


class TenantEmailBackend:
    """
    Tenant-aware email backend that uses per-school SMTP settings.
    Falls back to global Django settings if school email is disabled.
    """

    def __init__(self, fail_silently=False, **kwargs):
        self.fail_silently = fail_silently
        self._backend = None

    def _get_backend(self):
        """Get the appropriate email backend based on tenant settings."""
        from django.db import connection

        # Check if we're in a tenant schema
        if connection.schema_name == 'public':
            return self._get_global_backend()

        try:
            from core.models import SchoolSettings
            school_settings = SchoolSettings.load()

            if not school_settings.email_enabled:
                return self._get_global_backend()

            if school_settings.email_backend == 'console':
                return ConsoleBackend(fail_silently=self.fail_silently)

            # SMTP backend with school settings
            return DjangoSMTPBackend(
                host=school_settings.email_host or django_settings.EMAIL_HOST,
                port=school_settings.email_port or django_settings.EMAIL_PORT,
                username=school_settings.email_host_user or django_settings.EMAIL_HOST_USER,
                password=school_settings.email_host_password or django_settings.EMAIL_HOST_PASSWORD,
                use_tls=school_settings.email_use_tls,
                use_ssl=school_settings.email_use_ssl,
                fail_silently=self.fail_silently,
            )
        except Exception as e:
            # Log the error and fall back to global settings
            logger.warning(f"Failed to load tenant email settings: {e}. Using global settings.")
            return self._get_global_backend()

    def _get_global_backend(self):
        """Return email backend using global Django settings."""
        backend_path = getattr(
            django_settings,
            'DEFAULT_EMAIL_BACKEND',
            'django.core.mail.backends.console.EmailBackend'
        )

        # If global backend is console, use console
        if 'console' in backend_path.lower():
            return ConsoleBackend(fail_silently=self.fail_silently)

        # Otherwise use SMTP with global settings
        return DjangoSMTPBackend(
            host=getattr(django_settings, 'EMAIL_HOST', 'localhost'),
            port=getattr(django_settings, 'EMAIL_PORT', 587),
            username=getattr(django_settings, 'EMAIL_HOST_USER', ''),
            password=getattr(django_settings, 'EMAIL_HOST_PASSWORD', ''),
            use_tls=getattr(django_settings, 'EMAIL_USE_TLS', True),
            use_ssl=getattr(django_settings, 'EMAIL_USE_SSL', False),
            fail_silently=self.fail_silently,
        )

    def open(self):
        """Open connection to the mail server."""
        self._backend = self._get_backend()
        return self._backend.open()

    def close(self):
        """Close connection to the mail server."""
        if self._backend is not None:
            self._backend.close()
            self._backend = None

    def send_messages(self, email_messages):
        """Send one or more EmailMessage objects and return the number sent."""
        backend = self._get_backend()
        return backend.send_messages(email_messages)
