from django import forms
from .models import SchoolSettings
from schools.models import School


class SchoolBasicInfoForm(forms.Form):
    """Form for basic school information (spans School and SchoolSettings models)."""
    name = forms.CharField(
        max_length=100,
        label='School Name',
        widget=forms.TextInput(attrs={'placeholder': 'School name'})
    )
    short_name = forms.CharField(
        max_length=20,
        required=False,
        label='Short Name',
        widget=forms.TextInput(attrs={'placeholder': 'Short name'})
    )
    display_name = forms.CharField(
        max_length=50,
        required=False,
        label='Display Name',
        widget=forms.TextInput(attrs={'placeholder': 'Display name'})
    )
    motto = forms.CharField(
        max_length=200,
        required=False,
        label='Motto',
        widget=forms.TextInput(attrs={'placeholder': 'School motto'})
    )


class SchoolBrandingForm(forms.ModelForm):
    """Form for school branding settings."""
    class Meta:
        model = SchoolSettings
        fields = ['logo', 'favicon', 'primary_color', 'secondary_color', 'accent_color']
        labels = {
            'logo': 'Logo',
            'favicon': 'Favicon',
            'primary_color': 'Primary',
            'secondary_color': 'Secondary',
            'accent_color': 'Accent',
        }
        widgets = {
            'logo': forms.FileInput(attrs={'accept': 'image/*'}),
            'favicon': forms.FileInput(attrs={'accept': 'image/*'}),
            'primary_color': forms.TextInput(attrs={'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'type': 'color'}),
            'accent_color': forms.TextInput(attrs={'type': 'color'}),
        }


class SchoolContactForm(forms.Form):
    """Form for school contact information."""
    email = forms.EmailField(
        required=False,
        label='Email',
        widget=forms.EmailInput(attrs={'placeholder': 'school@example.com'})
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        label='Phone',
        widget=forms.TextInput(attrs={'placeholder': '+233 XX XXX XXXX'})
    )
    address = forms.CharField(
        required=False,
        label='Address',
        widget=forms.Textarea(attrs={'placeholder': 'Street address', 'rows': 2})
    )
    digital_address = forms.CharField(
        max_length=50,
        required=False,
        label='Digital Address',
        widget=forms.TextInput(attrs={'placeholder': 'e.g., GA-123-4567'})
    )
    city = forms.CharField(
        max_length=100,
        required=False,
        label='City',
        widget=forms.TextInput(attrs={'placeholder': 'City'})
    )
    region = forms.CharField(
        max_length=100,
        required=False,
        label='Region',
        widget=forms.TextInput(attrs={'placeholder': 'Region'})
    )


class SchoolAdminForm(forms.Form):
    """Form for school administration details."""
    headmaster_name = forms.CharField(
        max_length=100,
        required=False,
        label="Head's Name",
        widget=forms.TextInput(attrs={'placeholder': "Head's full name"})
    )
    headmaster_title = forms.CharField(
        max_length=50,
        required=False,
        label="Head's Title",
        widget=forms.TextInput(attrs={'placeholder': 'e.g., Headmaster, Principal'})
    )
