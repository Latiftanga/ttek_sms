from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.http import JsonResponse


def health_check(request):
    """Health check endpoint for load balancers and monitoring."""
    return JsonResponse({'status': 'healthy'})


def tenant_test(request):
    """Test to check if tenant URLconf is being used."""
    return JsonResponse({'urlconf': 'config.urls (TENANT)', 'path': request.path})


urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('tenant-test/', tenant_test, name='tenant_test'),
    path('', include('core.urls')),
    path('', include('accounts.urls')),
    path('academics/', include('academics.urls')),
    path('students/', include('students.urls')),
    path('teachers/', include('teachers.urls')),
    path('communications/', include('communications.urls')),
    path('gradebook/', include('gradebook.urls')),
    path('finance/', include('finance.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]
