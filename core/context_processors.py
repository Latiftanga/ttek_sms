import logging
from django.core.cache import cache
from django.db import connection, ProgrammingError, OperationalError

logger = logging.getLogger(__name__)

# Cache TTL for context processor queries (seconds)
_CTX_CACHE_TTL = 60


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

    cache_key = f'ctx_school_settings:{schema_name}'
    school_settings = cache.get(cache_key)
    if school_settings is None:
        try:
            from .models import SchoolSettings
            school_settings = SchoolSettings.load()
            cache.set(cache_key, school_settings, _CTX_CACHE_TTL)
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

    ay_key = f'ctx_academic_year:{schema_name}'
    current_academic_year = cache.get(ay_key)
    if current_academic_year is None:
        try:
            from .models import AcademicYear
            current_academic_year = AcademicYear.get_current()
            if current_academic_year:
                cache.set(ay_key, current_academic_year, _CTX_CACHE_TTL)
        except (ProgrammingError, OperationalError):
            pass
        except Exception as e:
            logger.warning(f"Failed to load academic year: {e}")

    term_key = f'ctx_term:{schema_name}'
    current_term = cache.get(term_key)
    if current_term is None:
        try:
            from .models import Term
            current_term = Term.get_current()
            if current_term:
                cache.set(term_key, current_term, _CTX_CACHE_TTL)
        except (ProgrammingError, OperationalError):
            pass
        except Exception as e:
            logger.warning(f"Failed to load term: {e}")

    return {
        'current_academic_year': current_academic_year,
        'current_term': current_term,
    }
