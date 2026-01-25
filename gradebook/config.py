"""
Configuration settings for the gradebook app.

These values can be overridden in Django settings by prefixing with GRADEBOOK_.
For example, to change MAX_FILE_SIZE:
    GRADEBOOK_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

All configuration values are lazily loaded to avoid Django setup issues.
"""
from decimal import Decimal


def _get_setting(name, default):
    """Get a gradebook setting from Django settings or use default."""
    from django.conf import settings
    return getattr(settings, f'GRADEBOOK_{name}', default)


# Define defaults as constants for direct use when Django settings are not needed
_DEFAULTS = {
    # File upload limits
    'MAX_FILE_SIZE': 5 * 1024 * 1024,  # 5 MB

    # Default grading thresholds
    'DEFAULT_PASS_MARK': Decimal('50.00'),
    'DEFAULT_CREDIT_MARK': Decimal('50.00'),
    'DEFAULT_MIN_AVERAGE_FOR_PROMOTION': Decimal('40.00'),

    # Bulk operation settings
    'BULK_UPDATE_BATCH_SIZE': 500,

    # Analytics and display limits
    'AUDIT_LOG_DISPLAY_LIMIT': 50,
    'TOP_PERFORMERS_LIMIT': 5,
    'AT_RISK_STUDENTS_LIMIT': 5,
    'TOP_SUBJECTS_LIMIT': 10,

    # SMS settings
    'SMS_MAX_LENGTH': 160,

    # Export settings
    'EXCEL_HEADER_COLOR': '4F46E5',

    # Celery task settings
    'TASK_MAX_RETRIES': 3,
    'TASK_RETRY_DELAY': 60,  # seconds

    # Ghana-specific defaults
    'GHANA_CA_PERCENTAGE': 30,
    'GHANA_EXAM_PERCENTAGE': 70,
    'WASSCE_AGGREGATE_SUBJECTS': 6,
}


class _ConfigProxy:
    """
    Lazy configuration proxy that loads settings only when accessed.
    This avoids Django setup issues during module import.
    """

    def __getattr__(self, name):
        if name in _DEFAULTS:
            return _get_setting(name, _DEFAULTS[name])
        raise AttributeError(f"Unknown config setting: {name}")


# Module-level proxy object for attribute access
_config = _ConfigProxy()


# For backwards compatibility and direct attribute access
def __getattr__(name):
    """Enable module-level attribute access via the config proxy."""
    return getattr(_config, name)
