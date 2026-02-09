import re
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Teacher, Promotion, Qualification


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
            'date_of_birth', 'ghana_card_number', 'ssnit_number',
            'staff_id', 'staff_category', 'status',
            'licence_number',
            'employment_date', 'date_posted_to_current_school',
            'phone_number', 'email', 'address', 'photo', 'nationality'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'employment_date': forms.DateInput(attrs={'type': 'date'}),
            'date_posted_to_current_school': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.TextInput(),
        }

    def clean_phone_number(self):
        """Validate and normalize phone number."""
        phone = self.cleaned_data.get('phone_number')
        if phone:
            return validate_phone_number(phone)
        return phone


class PromotionForm(forms.ModelForm):
    class Meta:
        model = Promotion
        fields = ['rank', 'date_promoted']
        widgets = {
            'date_promoted': forms.DateInput(attrs={'type': 'date'}),
        }


class QualificationForm(forms.ModelForm):
    class Meta:
        model = Qualification
        fields = ['title', 'institution', 'date_started', 'date_ended', 'status']
        widgets = {
            'date_started': forms.DateInput(attrs={'type': 'date'}),
            'date_ended': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        date_started = cleaned_data.get('date_started')
        date_ended = cleaned_data.get('date_ended')

        if date_started and date_ended and date_ended < date_started:
            raise forms.ValidationError(_("End date cannot be before start date."))

        return cleaned_data