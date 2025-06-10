from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.conf import settings
from django.urls import reverse
from .models import School


class TenantMiddleware:
    """
    Enhanced multi-tenant middleware with better domain handling
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Define your main domain (where developer portal lives)
        self.main_domain = getattr(settings, 'MAIN_DOMAIN', 'ttek.com')

    def __call__(self, request):
        # Get the host from request
        host = request.get_host().lower()

        # Remove port if present (for development)
        if ':' in host:
            host = host.split(':')[0]

        # Initialize tenant and domain type
        school = None
        request.is_localhost = False
        request.is_main_domain = False
        request.is_school_domain = False

        # Handle localhost/127.0.0.1 specially
        if host in ['localhost', '127.0.0.1']:
            request.tenant = None
            request.is_localhost = True
            
        elif host == self.main_domain:
            # This is the main domain - for developer portal and landing
            request.tenant = None
            request.is_main_domain = True
            
        else:
            # Try to find school by domain or subdomain
            request.is_school_domain = True
            
            try:
                # First try exact domain match (custom domain)
                school = School.objects.get(domain=host, is_active=True)
            except School.DoesNotExist:
                # Try subdomain match
                if f'.{self.main_domain}' in host:
                    subdomain = host.replace(f'.{self.main_domain}', '')
                    try:
                        school = School.objects.get(
                            subdomain=subdomain, is_active=True)
                    except School.DoesNotExist:
                        pass

            # If no school found for this domain, raise 404
            if not school:
                raise Http404("School not found for this domain")

            request.tenant = school

        response = self.get_response(request)
        return response