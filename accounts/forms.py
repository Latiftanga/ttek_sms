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