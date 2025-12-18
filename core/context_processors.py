from django.db import connection


def school_branding(request):
    """
    Add school branding/settings to template context.
    Makes 'school' available in all templates.
    Only loads for tenant schemas (not public).
    """
    # Check if we're on a tenant schema (not public)
    schema_name = getattr(connection, 'schema_name', 'public')
    if schema_name == 'public':
        return {'school': None}

    try:
        from .models import SchoolSettings
        school = SchoolSettings.load()
    except Exception:
        # Table doesn't exist yet or other error
        school = None

    return {'school': school}


def academic_session(request):
    """
    Add current academic session to template context.
    Makes 'current_session' and 'current_term' available in all templates.
    """
    # Check if we're on a tenant schema
    schema_name = getattr(connection, 'schema_name', 'public')
    if schema_name == 'public':
        return {'current_session': None, 'current_term': None}

    # TODO: Implement when AcademicSession model exists
    return {
        'current_session': None,
        'current_term': None,
    }
