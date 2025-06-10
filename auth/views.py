"""
Authentication views for the school management system
Fixed to work properly with base.html message system
"""
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.views import LoginView as BaseLoginView
from django.core.exceptions import ObjectDoesNotExist
from .forms import CustomLoginForm


class LoginView(BaseLoginView):
    """
    Custom login view with school context
    Uses Django messages for error/success feedback
    """
    form_class = CustomLoginForm
    template_name = 'auth/login.html'

    def dispatch(self, request, *args, **kwargs):
        """Handle domain-specific login logic"""
        # If user is already authenticated, redirect appropriately
        if self.redirect_authenticated_user and request.user.is_authenticated:
            redirect_to = self.get_success_url()
            if redirect_to == request.get_full_path():
                raise ValueError(
                    "Redirection loop for authenticated user detected. Check that "
                    "your LOGIN_REDIRECT_URL doesn't point to a login page."
                )
            return redirect(redirect_to)

        # Check domain context for proper portal access
        is_admin_portal = getattr(request, 'is_admin_portal', False)
        school = getattr(request, 'school', None)

        # Store portal context for template
        self.is_admin_portal = is_admin_portal
        self.school = school

        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        """Redirect to dashboard after successful login"""
        # Check if there's a 'next' parameter
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url

        # Default redirect to dashboard
        return reverse('dashboard:index')

    def get_context_data(self, **kwargs):
        """Add portal context to login form"""
        context = super().get_context_data(**kwargs)
        context.update({
            'is_admin_portal': getattr(self, 'is_admin_portal', False),
            'school': getattr(self, 'school', None),
            'current_domain': self.request.get_host(),
        })
        return context

    def form_valid(self, form):
        """Add custom logic after successful login"""
        user = form.get_user()
        is_admin_portal = getattr(self.request, 'is_admin_portal', False)
        school = getattr(self.request, 'school', None)

        # Perform the login
        login(self.request, user)

        # Add success message based on portal type
        if is_admin_portal:
            if user.is_superuser:
                messages.success(
                    self.request,
                    'Welcome to TTEK SMS Developer Portal!'
                )
            else:
                messages.warning(
                    self.request,
                    'Developer portal access requires superuser privileges.'
                )
        elif school:
            try:
                user_school = user.get_school()
                if user_school == school:
                    messages.success(
                        self.request,
                        f'Welcome back to {school.name}!'
                    )
                elif user.is_superuser:
                    messages.info(
                        self.request,
                        f'Accessing {school.name} as system administrator.'
                    )
                else:
                    messages.warning(
                        self.request,
                        f'Your account is not associated with {school.name}.'
                    )
            except (AttributeError, ObjectDoesNotExist):
                # Handle case where user doesn't have get_school method or school doesn't exist
                if user.is_superuser:
                    messages.info(
                        self.request,
                        f'Accessing {school.name} as system administrator.'
                    )
                else:
                    messages.warning(
                        self.request,
                        'Your account is not associated with any school.'
                    )
        else:
            messages.success(
                self.request,
                'Login successful! Welcome back.'
            )

        # Redirect to success URL
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        """Handle login failures using Django messages"""
        # Check if there are form errors
        if form.non_field_errors():
            # Use the first non-field error
            messages.error(
                self.request,
                form.non_field_errors()[0]
            )
        elif form.errors:
            # Generic error message for field errors
            messages.error(
                self.request,
                'Please correct the errors below and try again.'
            )
        else:
            # Fallback error message
            messages.error(
                self.request,
                'Invalid username or password. Please try again.'
            )

        # Return the form with errors
        return super().form_invalid(form)


def logout_view(request):
    """
    Custom logout view
    """
    school_name = 'the system'  # Default value

    if request.user.is_authenticated:
        try:
            user_school = request.user.get_school()
            if user_school:
                school_name = user_school.name
        except (AttributeError, ObjectDoesNotExist):
            # Handle case where user doesn't have get_school method or school doesn't exist
            pass

        logout(request)
        messages.success(
            request,
            f'You have been successfully logged out from {school_name}.'
        )
    else:
        messages.info(request, 'You were not logged in.')

    return redirect('auth:login')


@login_required
def profile_view(request):
    """
    User profile view
    """
    try:
        user_profile = request.user.get_profile()
    except (AttributeError, ObjectDoesNotExist):
        user_profile = None

    try:
        school = request.user.get_school()
    except (AttributeError, ObjectDoesNotExist):
        school = None

    try:
        user_role = request.user.get_role_display()
    except AttributeError:
        user_role = 'Unknown'

    context = {
        'user_profile': user_profile,
        'school': school,
        'user_role': user_role,
    }

    return render(request, 'auth/profile.html', context)