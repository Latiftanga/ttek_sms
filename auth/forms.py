"""
Fixed Forms for authentication - works with base.html messages
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate
from core.models import User


class CustomLoginForm(AuthenticationForm):
    """
    Custom login form with enhanced styling and validation
    Compatible with base.html message system
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your username',
            'autocomplete': 'username',
        }),
        label='Username'
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        }),
        label='Password'
    )

    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        }),
        label='Remember me'
    )

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.school = getattr(request, 'school', None) if request else None
        self.is_admin_portal = getattr(
            request, 'is_admin_portal', False) if request else False

        # Add Bootstrap classes and improve styling
        for field_name, field in self.fields.items():
            if field_name != 'remember_me':
                field.widget.attrs.update({
                    'class': 'form-control',
                })

        # Add validation classes if there are errors
        if hasattr(self, 'errors'):
            for field_name, field in self.fields.items():
                if field_name in self.errors and field_name != 'remember_me':
                    field.widget.attrs['class'] += ' is-invalid'
                elif field_name != 'remember_me':
                    field.widget.attrs['class'] += ' is-valid' if self.is_bound and not self.errors.get(
                        field_name) else ''

    def clean(self):
        """
        Custom validation with detailed error messages and school context
        """
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            # For admin portal, allow any user
            if self.is_admin_portal:
                try:
                    user = User.objects.get(username=username)
                    if not user.is_active:
                        raise forms.ValidationError(
                            "This account has been deactivated. Please contact your administrator."
                        )
                except User.DoesNotExist:
                    raise forms.ValidationError(
                        "Invalid username or password.")

            # For school portals, filter by school
            elif self.school:
                try:
                    # Filter users by school context
                    user = User.objects.get(
                        username=username, school=self.school)
                    if not user.is_active:
                        raise forms.ValidationError(
                            "This account has been deactivated. Please contact your school administrator."
                        )
                except User.DoesNotExist:
                    # Check if user exists in another school
                    if User.objects.filter(username=username).exists():
                        raise forms.ValidationError(
                            "This username is not registered for this school."
                        )
                    else:
                        raise forms.ValidationError(
                            "Invalid username or password.")

            # No school context and not admin portal
            else:
                raise forms.ValidationError(
                    "Unable to determine school context. Please try again."
                )

            # Authenticate user
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password
            )

            if self.user_cache is None:
                raise forms.ValidationError("Invalid username or password.")

            # Additional check for school association (except superusers and admin portal)
            if not self.user_cache.is_superuser and not self.is_admin_portal:
                if self.school:
                    user_school = self.user_cache.get_school()
                    if user_school != self.school:
                        raise forms.ValidationError(
                            "Your account is not authorized to access this school."
                        )
                else:
                    user_school = self.user_cache.get_school()
                    if not user_school:
                        raise forms.ValidationError(
                            "Your account is not associated with any school. Please contact support."
                        )

        return self.cleaned_data
