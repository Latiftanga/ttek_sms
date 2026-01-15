from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch


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
                    except NoReverseMatch:
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
                    except NoReverseMatch:
                        password_change_url = '/accounts/password/change/'

                    return redirect(password_change_url)

        response = self.get_response(request)
        return response


class ProfileSetupMiddleware:
    """
    Middleware to force teachers and parents to complete profile setup.
    Redirects users with profile_setup_completed=False to the setup wizard.

    Only applies to:
    - Teachers (is_teacher=True)
    - Parents (is_parent=True)

    Does NOT apply to:
    - School admins
    - Platform admins (superusers)
    - Users who haven't changed their password yet (handled first by ForcePasswordChangeMiddleware)
    """

    ALLOWED_URL_NAMES = [
        'accounts:profile_setup',
        'accounts:profile_setup_step',
        'accounts:logout',
        'admin:logout',
    ]

    ALLOWED_PATH_PREFIXES = [
        '/static/',
        '/media/',
        '/accounts/profile-setup/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Skip if user must change password first (handled by ForcePasswordChangeMiddleware)
            if getattr(request.user, 'must_change_password', False):
                return self.get_response(request)

            # Only apply to teachers and parents
            is_applicable_user = (
                getattr(request.user, 'is_teacher', False) or
                getattr(request.user, 'is_parent', False)
            )

            # Check if profile setup is needed
            needs_setup = not getattr(request.user, 'profile_setup_completed', True)

            if is_applicable_user and needs_setup:
                current_path = request.path

                # Check if path is allowed
                is_allowed = False

                # Check URL names
                for url_name in self.ALLOWED_URL_NAMES:
                    try:
                        if current_path == reverse(url_name):
                            is_allowed = True
                            break
                    except NoReverseMatch:
                        pass

                # Check path prefixes
                for prefix in self.ALLOWED_PATH_PREFIXES:
                    if current_path.startswith(prefix):
                        is_allowed = True
                        break

                if not is_allowed:
                    try:
                        profile_setup_url = reverse('accounts:profile_setup')
                    except NoReverseMatch:
                        profile_setup_url = '/accounts/profile-setup/'

                    return redirect(profile_setup_url)

        return self.get_response(request)
