from django.http import JsonResponse
from django.shortcuts import render
from django_tenants.middleware.main import TenantMainMiddleware
from django_tenants.utils import get_public_schema_name


class TenantNotFoundMiddleware(TenantMainMiddleware):
    """
    Custom tenant middleware that shows a friendly error page
    when a school/tenant is not found instead of showing the public site.

    This ensures each school must be accessed via their specific subdomain,
    and prevents users from accidentally landing on the main domain.
    """

    @property
    def show_public_landing(self):
        """
        Whether to show a public landing page for main domains.
        Set SHOW_PUBLIC_LANDING=True in settings to enable.
        Default is False - shows "School Not Found" for all non-tenant domains.
        """
        from django.conf import settings
        return getattr(settings, 'SHOW_PUBLIC_LANDING', False)

    @property
    def public_domains(self):
        """Get list of domains that could show the public/landing page."""
        from django.conf import settings
        return getattr(settings, 'PUBLIC_DOMAINS', [
            'ttek-sms.com', 'www.ttek-sms.com', 'localhost', '127.0.0.1'
        ])

    def no_tenant_found(self, request, hostname):
        """
        Called when no tenant is found for the given hostname.
        Shows a custom error page instead of raising Http404 or showing public.
        """
        # Allow certain paths to work without a tenant (health checks, static files, PWA)
        allowed_paths = ['/health/', '/health', '/static/', '/favicon.ico', '/admin/', '/sw.js', '/manifest.json', '/offline/']
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
            'is_main_domain': self.is_public_domain(hostname),
        }, status=404)

    def is_public_domain(self, hostname):
        """
        Check if hostname is a known public/main domain (not a subdomain).
        """
        # Remove port if present
        hostname_without_port = hostname.split(':')[0].lower()

        # Check exact match with public domains
        if hostname_without_port in [d.lower() for d in self.public_domains]:
            return True

        # Check if it's localhost with port (but not subdomain.localhost)
        if hostname_without_port == 'localhost' or hostname_without_port == '127.0.0.1':
            return True

        return False

    def process_request(self, request):
        """
        Override to catch tenant not found and show custom page.

        Flow:
        1. Try to find tenant for hostname
        2. If found and NOT public schema -> use it (school tenant)
        3. If found and IS public schema:
           - If SHOW_PUBLIC_LANDING=True and is main domain -> show landing
           - Otherwise -> show "School Not Found"
        4. If not found -> show "School Not Found"
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
            return None

        # If this is the public schema tenant
        if tenant.schema_name == get_public_schema_name():
            # Only allow if: public landing is enabled AND it's a main domain
            if self.show_public_landing and self.is_public_domain(hostname):
                # Allow public landing page
                pass
            else:
                # Show "School Not Found" for:
                # - Non-existent subdomains that fell through to public
                # - Main domain when public landing is disabled
                response = self.no_tenant_found(request, hostname)
                if response:
                    return response

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
