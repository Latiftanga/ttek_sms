import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm


class LoginForm(AuthenticationForm):
    """Custom login form with email as username field."""

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            'autofocus': True,
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
        })
    )

    error_messages = {
        'invalid_login': "Invalid email or password. Please try again.",
        'inactive': "This account is inactive. Contact your administrator.",
    }

    def clean_username(self):
        """Normalize email to lowercase for case-insensitive login."""
        return self.cleaned_data.get('username', '').lower()


PHONE_RE = re.compile(r'^\+?[\d\s\-()]{7,17}$')


class ProfilePhoneForm(forms.Form):
    """Validate phone number for profile setup."""
    phone = forms.CharField(
        max_length=17,
        required=False,
    )
    address = forms.CharField(
        max_length=500,
        required=False,
    )

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if phone and not PHONE_RE.match(phone):
            raise forms.ValidationError('Enter a valid phone number.')
        return phone

    def clean_address(self):
        return self.cleaned_data.get('address', '').strip()