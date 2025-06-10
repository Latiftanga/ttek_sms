# core/url_dispatcher.py
from django.urls import resolve, Resolver404
from django.http import Http404


class DomainURLDispatcher:
    """
    Dispatches URLs based on domain type to provide different
    URL patterns for main domain vs school domains
    """

    def __init__(self):
        # Import here to avoid circular imports
        from .urls import main_domain_urls, school_domain_urls, localhost_urls
        self.main_domain_urls = main_domain_urls
        self.school_domain_urls = school_domain_urls
        self.localhost_urls = localhost_urls

    def resolve_url(self, request, path):
        """
        Resolve URL based on domain type
        """
        # Determine which URL patterns to use
        if getattr(request, 'is_localhost', False):
            urlpatterns = self.localhost_urls
        elif getattr(request, 'is_main_domain', False):
            urlpatterns = self.main_domain_urls
        elif getattr(request, 'is_school_domain', False):
            urlpatterns = self.school_domain_urls
        else:
            # Fallback to main domain patterns
            urlpatterns = self.main_domain_urls

        # Try to resolve the path
        try:
            for pattern in urlpatterns:
                try:
                    match = pattern.resolve(path)
                    if match:
                        return match
                except Resolver404:
                    continue

            # If no pattern matches, raise 404
            raise Http404(f"No URL pattern found for path: {path}")

        except Exception as e:
            raise Http404(f"URL resolution error: {str(e)}")


# Create a global instance
url_dispatcher = DomainURLDispatcher()
