from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from schools.views import public_home
from core.views import service_worker, offline, manifest


def health_check(request):
    """Health check endpoint for load balancers and monitoring."""
    return JsonResponse({'status': 'healthy'})


urlpatterns = [
    # PWA support (must be available on all domains)
    path('sw.js', service_worker, name='service_worker'),
    path('manifest.json', manifest, name='manifest'),
    path('offline/', offline, name='offline'),

    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path('', public_home, name='public_home'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]
