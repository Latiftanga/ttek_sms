from django import forms
from .models import SchoolSettings, AcademicYear, Term


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
    motto = forms.CharField(
        max_length=200,
        required=False,
        label='Motto',
        widget=forms.TextInput(attrs={'placeholder': 'School motto'})
    )


class SchoolBrandingForm(forms.Form):
    """Form for school branding settings (stored on School model in public schema)."""
    logo = forms.ImageField(
        required=False,
        label='Logo',
        widget=forms.FileInput(attrs={'accept': 'image/*'})
    )
    favicon = forms.ImageField(
        required=False,
        label='Favicon',
        widget=forms.FileInput(attrs={'accept': 'image/*'})
    )
    primary_color = forms.CharField(
        max_length=7,
        required=False,
        label='Primary',
        widget=forms.TextInput(attrs={'type': 'color'})
    )
    secondary_color = forms.CharField(
        max_length=7,
        required=False,
        label='Secondary',
        widget=forms.TextInput(attrs={'type': 'color'})
    )
    accent_color = forms.CharField(
        max_length=7,
        required=False,
        label='Accent',
        widget=forms.TextInput(attrs={'type': 'color'})
    )


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


class AcademicSettingsForm(forms.ModelForm):
    """Form for academic period settings."""
    class Meta:
        model = SchoolSettings
        fields = ['academic_period_type']
        labels = {
            'academic_period_type': 'Academic Period Type',
        }


class SMSSettingsForm(forms.ModelForm):
    """Form for SMS configuration settings."""
    class Meta:
        model = SchoolSettings
        fields = ['sms_enabled', 'sms_backend', 'sms_api_key', 'sms_sender_id']
        labels = {
            'sms_enabled': 'Enable SMS',
            'sms_backend': 'SMS Provider',
            'sms_api_key': 'API Key',
            'sms_sender_id': 'Sender ID (Optional)',
        }
        widgets = {
            'sms_api_key': forms.PasswordInput(attrs={
                'placeholder': 'Enter your Arkesel API key',
                'autocomplete': 'off',
            }),
            'sms_sender_id': forms.TextInput(attrs={
                'placeholder': 'Max 11 characters (uses school name if empty)',
                'maxlength': '11',
            }),
        }
        help_texts = {
            'sms_api_key': 'Get your API key from https://sms.arkesel.com/user/sms-api/info',
            'sms_sender_id': 'Leave empty to use school name',
        }


class EmailSettingsForm(forms.ModelForm):
    """Form for email configuration settings."""
    class Meta:
        model = SchoolSettings
        fields = [
            'email_enabled', 'email_backend', 'email_host', 'email_port',
            'email_use_tls', 'email_use_ssl', 'email_host_user',
            'email_host_password', 'email_from_address', 'email_from_name'
        ]
        labels = {
            'email_enabled': 'Enable Custom Email',
            'email_backend': 'Email Provider',
            'email_host': 'SMTP Host',
            'email_port': 'SMTP Port',
            'email_use_tls': 'Use TLS',
            'email_use_ssl': 'Use SSL',
            'email_host_user': 'Username',
            'email_host_password': 'Password',
            'email_from_address': 'From Email',
            'email_from_name': 'From Name',
        }
        widgets = {
            'email_host': forms.TextInput(attrs={
                'placeholder': 'e.g., smtp.gmail.com',
            }),
            'email_port': forms.NumberInput(attrs={
                'placeholder': '587',
            }),
            'email_host_user': forms.TextInput(attrs={
                'placeholder': 'your-email@example.com',
            }),
            'email_host_password': forms.PasswordInput(attrs={
                'placeholder': 'Enter your email password',
                'autocomplete': 'off',
            }),
            'email_from_address': forms.EmailInput(attrs={
                'placeholder': 'noreply@yourschool.com',
            }),
            'email_from_name': forms.TextInput(attrs={
                'placeholder': 'Your School Name',
            }),
        }


class AcademicYearForm(forms.ModelForm):
    """Form for creating/editing academic years."""
    class Meta:
        model = AcademicYear
        fields = ['name', 'start_date', 'end_date', 'is_current']
        labels = {
            'name': 'Academic Year Name',
            'start_date': 'Start Date',
            'end_date': 'End Date',
            'is_current': 'Set as Current',
        }
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., 2024/2025'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and start_date >= end_date:
            raise forms.ValidationError("End date must be after start date.")

        return cleaned_data


class TermForm(forms.ModelForm):
    """Form for creating/editing terms/semesters."""
    class Meta:
        model = Term
        fields = ['academic_year', 'name', 'term_number', 'start_date', 'end_date', 'is_current']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., First Term'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, period_type='term', **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['academic_year'].queryset = AcademicYear.objects.all()

        # Dynamic labels based on period type
        period_label = 'Semester' if period_type == 'semester' else 'Term'
        self.fields['academic_year'].label = 'Academic Year'
        self.fields['name'].label = f'{period_label} Name'
        self.fields['name'].widget.attrs['placeholder'] = f'e.g., First {period_label}'
        self.fields['term_number'].label = f'{period_label} Number'
        self.fields['start_date'].label = 'Start Date'
        self.fields['end_date'].label = 'End Date'
        self.fields['is_current'].label = 'Set as Current'

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        academic_year = cleaned_data.get('academic_year')

        if start_date and end_date and start_date >= end_date:
            raise forms.ValidationError("End date must be after start date.")

        # Validate term dates are within academic year
        if academic_year and start_date and end_date:
            if start_date < academic_year.start_date or end_date > academic_year.end_date:
                raise forms.ValidationError(
                    f"Dates must be within the academic year ({academic_year.start_date} - {academic_year.end_date})."
                )

        return cleaned_data
