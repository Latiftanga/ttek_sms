from django.http import JsonResponse
from django.shortcuts import render
from django_tenants.middleware.main import TenantMainMiddleware
from django_tenants.utils import get_public_schema_name


class TenantNotFoundMiddleware(TenantMainMiddleware):
    """
    Custom tenant middleware that shows a friendly error page
    when a school/tenant is not found instead of showing the public site.
    """

    def no_tenant_found(self, request, hostname):
        """
        Called when no tenant is found for the given hostname.
        Shows a custom error page instead of raising Http404 or showing public.
        """
        # Allow certain paths to work without a tenant (for platform admin, etc.)
        allowed_paths = ['/health/', '/health', '/static/', '/favicon.ico']
        if any(request.path.startswith(path) for path in allowed_paths):
            # Fall back to public schema for these paths
            from django.db import connection
            from schools.models import School
            request.tenant = School.objects.filter(
                schema_name=get_public_schema_name()
            ).first()
            if request.tenant:
                connection.set_tenant(request.tenant)
                return None

        # Render the "school not found" page
        return render(request, 'core/school_not_found.html', {
            'hostname': hostname,
        }, status=404)

    def process_request(self, request):
        """
        Override to catch tenant not found and show custom page.
        """
        from django_tenants.utils import get_tenant_domain_model
        from django.db import connection

        hostname = self.hostname_from_request(request)
        domain_model = get_tenant_domain_model()

        try:
            tenant = self.get_tenant(domain_model, hostname)
        except domain_model.DoesNotExist:
            # No tenant found - show custom error page
            response = self.no_tenant_found(request, hostname)
            if response:
                return response
            # If no_tenant_found returned None, continue with request
            return None

        tenant.domain_url = hostname
        request.tenant = tenant
        connection.set_tenant(tenant)
        self.setup_url_routing(request)


class HealthCheckMiddleware:
    """
    Middleware to handle health check requests before tenant resolution.

    This must be placed BEFORE TenantMainMiddleware in MIDDLEWARE settings
    to allow health checks to pass without requiring a valid tenant domain.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Handle health check before tenant middleware processes the request
        if request.path == '/health/' or request.path == '/health':
            return JsonResponse({'status': 'healthy'})

        return self.get_response(request)
