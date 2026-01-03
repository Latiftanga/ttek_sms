import logging
from django.http import JsonResponse
from django.conf import settings

logger = logging.getLogger(__name__)


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


class TenantDebugMiddleware:
    """
    Debug middleware to log tenant resolution info.
    Place AFTER TenantMainMiddleware to see resolved tenant.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Log tenant info after TenantMainMiddleware has set it
        tenant = getattr(request, 'tenant', None)
        urlconf = getattr(request, 'urlconf', 'NOT SET')

        if tenant:
            print(f'[TenantDebug] Path: {request.path}')
            print(f'[TenantDebug] Tenant schema: {tenant.schema_name}')
            print(f'[TenantDebug] Tenant name: {tenant.name}')
            print(f'[TenantDebug] URLConf: {urlconf}')
        else:
            print(f'[TenantDebug] Path: {request.path} - NO TENANT RESOLVED!')
            print(f'[TenantDebug] Host: {request.get_host()}')

        return self.get_response(request)
