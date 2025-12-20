from django import forms
from academics.models import Class
from .models import Student


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


class StudentForm(forms.ModelForm):
    """Form for creating/editing individual students."""

    class Meta:
        model = Student
        fields = [
            # Personal info
            'first_name', 'last_name', 'other_names',
            'date_of_birth', 'gender', 'photo',
            'address', 'phone',
            # Guardian info
            'guardian_name', 'guardian_phone', 'guardian_email',
            'guardian_relationship', 'guardian_address',
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
            'guardian_name': forms.TextInput(attrs={'placeholder': 'Guardian full name'}),
            'guardian_phone': forms.TextInput(attrs={'placeholder': 'Guardian phone'}),
            'guardian_email': forms.EmailInput(attrs={'placeholder': 'Guardian email (optional)'}),
            'guardian_address': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Guardian address'}),
            'admission_number': forms.TextInput(attrs={'placeholder': 'e.g., STU-2024-001'}),
            'admission_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active classes
        self.fields['current_class'].queryset = Class.objects.filter(is_active=True)
        self.fields['current_class'].required = False
