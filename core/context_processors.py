def tenant_context(request):
    """Add current tenant/school and domain context to templates"""
    school = getattr(request, 'tenant', None)

    context = {
        'current_school': school,
        'is_localhost': getattr(request, 'is_localhost', False),
        'is_main_domain': getattr(request, 'is_main_domain', False),
        'is_school_domain': getattr(request, 'is_school_domain', False),
    }

    # Add school-specific information
    if school:
        context.update({
            'school_url': school.get_full_url(),
            'school_domain': school.domain or f"{school.subdomain}.ttek.com",
        })

    # Add user context if authenticated
    if request.user.is_authenticated:
        user = request.user
        context.update({
            'user_role': user.get_role_display(),
            'user_profile': user.get_profile(),
            'is_admin': user.is_admin,
            'is_teacher': user.is_teacher,
            'is_student': user.is_student,
        })

        # Add user's school if different from current tenant
        user_school = user.get_school()
        if user_school:
            context['user_school'] = user_school

    return context


def site_context(request):
    """Add site-wide context"""
    from django.conf import settings

    return {
        'MAIN_DOMAIN': getattr(settings, 'MAIN_DOMAIN', 'ttek.com'),
        'SITE_NAME': getattr(settings, 'SITE_NAME', 'TTEK School Management System'),
        'SUPPORT_EMAIL': getattr(settings, 'SUPPORT_EMAIL', 'support@ttek.com'),
    }
