import re
import secrets
import string
from datetime import datetime

import pandas as pd

from core.models import AcademicYear
from core.utils import (  # noqa: F401
    is_school_admin, admin_required, htmx_render,
)
from students.models import Enrollment


def generate_temp_password(length=10):
    """Generate a random temporary password."""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def normalize_phone_number(phone):
    """
    Normalize a phone number to local format.
    Accepts: 0241234567, +233241234567, 233241234567
    Returns (is_valid, normalized_phone, error_message) tuple.
    """
    if not phone:
        return False, None, "Phone number is required"

    cleaned = re.sub(r'[^\d+]', '', phone)
    if cleaned.startswith('+'):
        cleaned = cleaned[1:]
    if cleaned.startswith('233'):
        cleaned = '0' + cleaned[3:]

    if len(cleaned) < 10:
        return False, None, "Phone number too short (minimum 10 digits)"
    if len(cleaned) > 15:
        return False, None, "Phone number too long (maximum 15 digits)"
    if not cleaned.isdigit():
        return False, None, "Phone number should contain only digits"

    return True, cleaned, None


def create_enrollment_for_student(student):
    """Create an enrollment record for a student in the current academic year."""
    current_year = AcademicYear.get_current()
    if not current_year:
        return None, False

    class_to_use = student.current_class
    if not class_to_use:
        return None, False

    enrollment, created = Enrollment.objects.get_or_create(
        student=student,
        academic_year=current_year,
        defaults={
            'class_assigned': class_to_use,
            'status': Enrollment.Status.ACTIVE,
        }
    )
    return enrollment, created


def parse_date(value):
    """Parse date from various formats."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, 'date'):  # pandas Timestamp
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def clean_value(value):
    """Clean a cell value, handling NaN and empty strings."""
    if value is None:
        return ''
    if isinstance(value, float) and pd.isna(value):
        return ''
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()
