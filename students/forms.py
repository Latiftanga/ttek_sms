from django import forms
from django.utils.translation import gettext_lazy as _
from academics.models import Class
from .models import Student, Guardian


class BulkImportForm(forms.Form):
    """Form for bulk importing students from Excel/CSV."""
    file = forms.FileField(
        help_text="Upload an Excel (.xlsx) or CSV file"
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            ext = file.name.split('.')[-1].lower()
            if ext not in ['xlsx', 'csv']:
                raise forms.ValidationError("Only .xlsx and .csv files are supported.")
        return file


class GuardianForm(forms.ModelForm):
    """Form for creating/editing guardians."""
    phone_number = forms.CharField(
        label=_("Phone Number"),
        widget=forms.TextInput(attrs={'placeholder': 'Phone number', 'required': True})
    )
    class Meta:
        model = Guardian
        fields = [
            'full_name', 'phone_number', 'email', 'occupation', 'address'
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'Full name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email (optional)'}),
            'occupation': forms.TextInput(attrs={'placeholder': 'Occupation (optional)'}),
            'address': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Address (optional)'}),
        }


class StudentForm(forms.ModelForm):
    """Form for creating/editing individual students (without guardian fields)."""

    class Meta:
        model = Student
        fields = [
            # Personal info
            'first_name', 'last_name', 'other_names',
            'date_of_birth', 'gender', 'photo',
            'address', 'phone',
            # Admission
            'admission_number', 'admission_date',
            # Enrollment
            'current_class',
            # Status
            'status', 'is_active',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last name'}),
            'other_names': forms.TextInput(attrs={'placeholder': 'Other names (optional)'}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Student address'}),
            'phone': forms.TextInput(attrs={'placeholder': 'Phone number (optional)'}),
            'admission_number': forms.TextInput(attrs={'placeholder': 'e.g., STU-2024-001'}),
            'admission_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active classes
        self.fields['current_class'].queryset = Class.objects.filter(is_active=True)
        self.fields['current_class'].required = False


class StudentGuardianForm(forms.Form):
    """Form for adding a guardian to a student."""
    guardian = forms.ModelChoiceField(
        queryset=Guardian.objects.all(),
        required=True,
        widget=forms.HiddenInput()
    )
    relationship = forms.ChoiceField(
        choices=Guardian.Relationship.choices,
        initial=Guardian.Relationship.GUARDIAN
    )
    is_primary = forms.BooleanField(required=False, initial=False)
    is_emergency_contact = forms.BooleanField(required=False, initial=True)
