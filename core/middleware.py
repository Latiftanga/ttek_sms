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
        if tenant:
            logger.info(f'[TenantDebug] Path: {request.path}, Tenant: {tenant.schema_name}, Name: {tenant.name}')
            logger.info(f'[TenantDebug] URLConf: {request.urlconf if hasattr(request, "urlconf") else "default"}')
        else:
            logger.warning(f'[TenantDebug] Path: {request.path}, No tenant resolved!')

        return self.get_response(request)
