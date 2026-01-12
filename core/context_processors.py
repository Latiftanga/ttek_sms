import logging
from django.db import connection, ProgrammingError, OperationalError

logger = logging.getLogger(__name__)


def school_branding(request):
    """
    Add school branding/settings to template context.
    Makes 'school' available in all templates.
    Only loads for tenant schemas (not public).
    """
    # Check if we're on a tenant schema (not public)
    schema_name = getattr(connection, 'schema_name', 'public')
    if schema_name == 'public':
        return {'school': None, 'tenant': None}

    school = None
    tenant = None

    # Get the tenant (School model from public schema)
    try:
        tenant = getattr(connection, 'tenant', None)
    except Exception as e:
        logger.warning(f"Failed to get tenant: {e}")

    # Get SchoolSettings (from tenant schema)
    try:
        from .models import SchoolSettings
        school = SchoolSettings.load()
    except (ProgrammingError, OperationalError):
        # Table doesn't exist yet (migrations not run)
        pass
    except Exception as e:
        logger.warning(f"Failed to load SchoolSettings: {e}")

    return {'school': school, 'tenant': tenant}


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
