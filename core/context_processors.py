import logging
from django.db import connection, ProgrammingError, OperationalError

logger = logging.getLogger(__name__)


def school_branding(request):
    """
    Add school branding to template context.
    'school' is the School model (connection.tenant) — has name, motto,
    logo, colors, contact info, and all branding fields.
    'school_settings' is SchoolSettings (tenant schema) — email config only.
    """
    schema_name = getattr(connection, 'schema_name', 'public')
    if schema_name == 'public':
        return {'school': None, 'school_settings': None, 'tenant': None}

    school = None
    school_settings = None

    try:
        school = getattr(connection, 'tenant', None)
    except Exception as e:
        logger.warning(f"Failed to get school: {e}")

    try:
        from .models import SchoolSettings
        school_settings = SchoolSettings.load()
    except (ProgrammingError, OperationalError):
        pass
    except Exception as e:
        logger.warning(f"Failed to load SchoolSettings: {e}")

    return {'school': school, 'school_settings': school_settings, 'tenant': school}


def academic_session(request):
    """
    Add current academic session to template context.
    Makes 'current_academic_year' and 'current_term' available in all templates.
    """
    # Check if we're on a tenant schema
    schema_name = getattr(connection, 'schema_name', 'public')
    if schema_name == 'public':
        return {'current_academic_year': None, 'current_term': None}

    current_academic_year = None
    current_term = None

    try:
        from .models import AcademicYear
        current_academic_year = AcademicYear.get_current()
    except (ProgrammingError, OperationalError):
        pass
    except Exception as e:
        logger.warning(f"Failed to load academic year: {e}")

    try:
        from .models import Term
        current_term = Term.get_current()
    except (ProgrammingError, OperationalError):
        pass
    except Exception as e:
        logger.warning(f"Failed to load term: {e}")

    return {
        'current_academic_year': current_academic_year,
        'current_term': current_term,
    }
