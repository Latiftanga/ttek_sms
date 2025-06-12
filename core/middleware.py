from django.http import HttpResponseNotFound, HttpResponse
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from .models import Tenant
import logging

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):
    """
    Middleware to resolve tenant based on domain/subdomain
    """

    def process_request(self, request):
        # Get the host from request
        host = request.get_host().lower()

        # Remove port number if present (for development)
        if ':' in host:
            host = host.split(':')[0]

        # Skip tenant resolution for admin, static files, and media during development
        if (request.path.startswith('/admin/') or
            request.path.startswith('/static/') or
                request.path.startswith('/media/')):
            request.tenant = None
            return None

        try:
            # Try to find tenant by domain or subdomain
            tenant = Tenant.objects.get_by_domain(host)
            request.tenant = tenant

            # Add tenant info to request for easy access
            request.school = tenant

        except Tenant.DoesNotExist:
            # Handle case where no tenant is found
            request.tenant = None
            request.school = None

            # For development, allow localhost without tenant
            if host in ['localhost', '127.0.0.1']:
                return None

            # Return 404 for unknown domains
            logger.warning(f"No tenant found for domain: {host}")
            return HttpResponse(
                f"<h1>School Not Found</h1><p>No school is configured for domain: {host}</p>",
                status=404
            )

        except Exception as e:
            logger.error(f"Error in TenantMiddleware: {e}")
            request.tenant = None
            request.school = None

        return None
