from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.http import JsonResponse
from core.views import service_worker, offline, manifest


def health_check(request):
    """Health check endpoint for load balancers and monitoring."""
    return JsonResponse({'status': 'healthy'})


urlpatterns = [
    # PWA / Offline support (tenant-aware - each school gets their own branded PWA)
    path('sw.js', service_worker, name='service_worker'),
    path('manifest.json', manifest, name='manifest'),
    path('offline/', offline, name='offline'),

    path('health/', health_check, name='health_check'),
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
