from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """
    Middleware to force users to change their password on first login.
    Redirects users with must_change_password=True to the password change page.
    """

    # URL names that should be accessible even when password change is required
    ALLOWED_URL_NAMES = [
        'accounts:password_change',
        'accounts:logout',
        'admin:logout',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Check if user must change password
            if getattr(request.user, 'must_change_password', False):
                current_path = request.path

                # Build list of allowed paths from URL names
                allowed_paths = []
                for url_name in self.ALLOWED_URL_NAMES:
                    try:
                        allowed_paths.append(reverse(url_name))
                    except:
                        pass

                # Check if current path is allowed
                is_allowed = current_path in allowed_paths

                # Also allow static/media files
                if current_path.startswith('/static/') or current_path.startswith('/media/'):
                    is_allowed = True

                if not is_allowed:
                    # Redirect to password change
                    try:
                        password_change_url = reverse('accounts:password_change')
                    except:
                        password_change_url = '/accounts/password/change/'

                    return redirect(password_change_url)

        response = self.get_response(request)
        return response
