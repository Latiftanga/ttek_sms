import re
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Teacher, ProfessionalDevelopment, TeacherDocument


def validate_phone_number(phone):
    """
    Validate and normalize phone number.
    Accepts formats like: 0241234567, +233241234567, 233241234567
    Returns normalized phone number or raises ValidationError.
    """
    if not phone:
        return phone

    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', phone)

    # Remove leading + if present
    if cleaned.startswith('+'):
        cleaned = cleaned[1:]

    # Handle Ghana numbers (can be extended for other countries)
    if cleaned.startswith('233'):
        cleaned = '0' + cleaned[3:]

    # Validate length
    if len(cleaned) < 10:
        raise forms.ValidationError(_("Phone number too short (minimum 10 digits)"))
    if len(cleaned) > 15:
        raise forms.ValidationError(_("Phone number too long (maximum 15 digits)"))

    # Validate it contains only digits
    if not cleaned.isdigit():
        raise forms.ValidationError(_("Phone number should contain only digits"))

    return cleaned


class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        # We can list fields explicitly to control order
        fields = [
            'title', 'first_name', 'middle_name', 'last_name', 'gender',
            'date_of_birth', 'staff_id', 'status',
            'subject_specialization', 'employment_date',
            'phone_number', 'email', 'address', 'photo', 'nationality'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'employment_date': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_phone_number(self):
        """Validate and normalize phone number."""
        phone = self.cleaned_data.get('phone_number')
        if phone:
            return validate_phone_number(phone)
        return phone


class ProfessionalDevelopmentForm(forms.ModelForm):
    """Form for creating/editing professional development activities."""

    class Meta:
        model = ProfessionalDevelopment
        fields = [
            'title', 'activity_type', 'provider', 'description',
            'start_date', 'end_date', 'hours', 'status',
            'certificate_number', 'certificate_expiry', 'certificate_file',
            'notes'
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'certificate_expiry': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'hours': forms.NumberInput(attrs={'step': '0.5', 'min': '0'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError(_("End date cannot be before start date."))

        return cleaned_data


class TeacherDocumentForm(forms.ModelForm):
    """Form for uploading/editing teacher documents."""

    class Meta:
        model = TeacherDocument
        fields = [
            'title', 'document_type', 'file', 'description',
            'issue_date', 'expiry_date'
        ]
        widgets = {
            'issue_date': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Check file size (max 10MB)
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError(_("File size must be under 10MB."))
            # Check file extension
            ext = file.name.split('.')[-1].lower()
            allowed_extensions = ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx']
            if ext not in allowed_extensions:
                raise forms.ValidationError(
                    _("File type not allowed. Accepted: PDF, JPG, PNG, DOC, DOCX")
                )
        return file