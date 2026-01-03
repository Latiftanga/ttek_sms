from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from schools.views import public_home


def health_check(request):
    """Health check endpoint for load balancers and monitoring."""
    return JsonResponse({'status': 'healthy'})


def test_public(request):
    """Simple test to verify public URLconf is being used."""
    return JsonResponse({'status': 'public_urlconf_working', 'path': request.path})


def simple_home(request):
    """Simple home page to test if root URL works."""
    return JsonResponse({
        'status': 'ok',
        'message': 'TTEK SMS Platform - Public Home',
        'urlconf': 'urls_public'
    })


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path('test/', test_public, name='test_public'),
    path('', simple_home, name='public_home'),  # Temporarily use simple JSON response
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]
