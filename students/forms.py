import re
from django import forms
from django.utils.translation import gettext_lazy as _
from academics.models import Class
from core.models import AcademicYear
from .models import Student, Guardian, House, Exeat, HouseMaster


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
    # Ghana: +233XXXXXXXXX (10 digits after country code) or 0XXXXXXXXX (10 digits)
    if cleaned.startswith('233'):
        cleaned = '0' + cleaned[3:]  # Convert to local format

    # Validate length (most phone numbers are 10-15 digits)
    if len(cleaned) < 10:
        raise forms.ValidationError(_("Phone number too short (minimum 10 digits)"))
    if len(cleaned) > 15:
        raise forms.ValidationError(_("Phone number too long (maximum 15 digits)"))

    # Validate it contains only digits
    if not cleaned.isdigit():
        raise forms.ValidationError(_("Phone number should contain only digits"))

    return cleaned


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

    def clean_phone_number(self):
        """Validate and normalize phone number."""
        phone = self.cleaned_data.get('phone_number')
        normalized = validate_phone_number(phone)

        # Check for uniqueness (excluding current instance if editing)
        qs = Guardian.objects.filter(phone_number=normalized)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("A guardian with this phone number already exists."))

        return normalized


class StudentForm(forms.ModelForm):
    """Form for creating/editing individual students (without guardian fields)."""

    # Maximum photo size in bytes (5MB)
    MAX_PHOTO_SIZE = 5 * 1024 * 1024

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
            # House
            'house',
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

        # Hide house field for schools without houses support
        from core.models import SchoolSettings
        school_settings = SchoolSettings.load()
        if school_settings.has_houses:
            self.fields['house'].queryset = House.objects.filter(is_active=True)
            self.fields['house'].required = False
        else:
            del self.fields['house']

    def clean_photo(self):
        """Validate photo file size."""
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'size'):
            if photo.size > self.MAX_PHOTO_SIZE:
                raise forms.ValidationError(
                    f"Photo size exceeds 5MB limit. Please upload a smaller image."
                )
        return photo

    def clean_phone(self):
        """Validate and normalize student phone number (optional field)."""
        phone = self.cleaned_data.get('phone')
        if phone:
            return validate_phone_number(phone)
        return phone


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


class HouseForm(forms.ModelForm):
    """Form for creating/editing houses."""
    class Meta:
        model = House
        fields = ['name', 'color', 'color_code', 'motto', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Blue House, Nkrumah House'}),
            'color': forms.TextInput(attrs={'placeholder': 'e.g., Blue, Red, Green'}),
            'color_code': forms.TextInput(attrs={'type': 'color', 'class': 'h-10'}),
            'motto': forms.TextInput(attrs={'placeholder': 'House motto (optional)'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Description (optional)'}),
        }


class ExeatForm(forms.ModelForm):
    """Form for creating/editing exeat requests."""

    class Meta:
        model = Exeat
        fields = [
            'student', 'exeat_type', 'reason', 'destination',
            'departure_date', 'departure_time',
            'expected_return_date', 'expected_return_time',
            'contact_phone', 'contact_person'
        ]
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Reason for exeat'}),
            'destination': forms.TextInput(attrs={'placeholder': 'Where student is going'}),
            'departure_date': forms.DateInput(attrs={'type': 'date'}),
            'departure_time': forms.TimeInput(attrs={'type': 'time'}),
            'expected_return_date': forms.DateInput(attrs={'type': 'date'}),
            'expected_return_time': forms.TimeInput(attrs={'type': 'time'}),
            'contact_phone': forms.TextInput(attrs={'placeholder': 'Emergency contact phone'}),
            'contact_person': forms.TextInput(attrs={'placeholder': 'Contact person name (optional)'}),
        }

    def __init__(self, *args, students=None, **kwargs):
        super().__init__(*args, **kwargs)
        if students is not None:
            self.fields['student'].queryset = students

    def clean(self):
        cleaned_data = super().clean()
        departure_date = cleaned_data.get('departure_date')
        expected_return_date = cleaned_data.get('expected_return_date')

        if departure_date and expected_return_date:
            if expected_return_date < departure_date:
                raise forms.ValidationError(
                    _("Return date cannot be before departure date.")
                )
        return cleaned_data


class ExeatApprovalForm(forms.Form):
    """Form for approving/rejecting exeat."""
    action = forms.ChoiceField(choices=[
        ('approve', _('Approve')),
        ('recommend', _('Recommend')),
        ('reject', _('Reject')),
    ])
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'Reason for rejection'})
    )


class HouseMasterForm(forms.ModelForm):
    """Form for assigning a teacher as housemaster."""

    class Meta:
        model = HouseMaster
        fields = ['teacher', 'house', 'academic_year', 'is_senior']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Default to current academic year
        current_year = AcademicYear.get_current()
        if current_year:
            self.fields['academic_year'].initial = current_year

        # Only show active houses
        self.fields['house'].queryset = House.objects.filter(is_active=True)

        # Get teachers
        from teachers.models import Teacher
        self.fields['teacher'].queryset = Teacher.objects.filter(
            status='active'
        ).select_related('user').order_by('last_name', 'first_name')

    def clean(self):
        cleaned_data = super().clean()
        teacher = cleaned_data.get('teacher')
        house = cleaned_data.get('house')
        academic_year = cleaned_data.get('academic_year')
        is_senior = cleaned_data.get('is_senior')

        if teacher and house and academic_year:
            # Check for existing assignment for this house/year
            existing = HouseMaster.objects.filter(
                house=house,
                academic_year=academic_year,
                is_active=True
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(
                    _("This house already has a housemaster for this academic year.")
                )

            # Check if teacher already assigned to another house
            teacher_assignment = HouseMaster.objects.filter(
                teacher=teacher,
                academic_year=academic_year,
                is_active=True
            )
            if self.instance.pk:
                teacher_assignment = teacher_assignment.exclude(pk=self.instance.pk)
            if teacher_assignment.exists():
                raise forms.ValidationError(
                    _("This teacher is already assigned to another house.")
                )

            # If marking as senior, check there isn't another senior
            if is_senior:
                senior_exists = HouseMaster.objects.filter(
                    academic_year=academic_year,
                    is_senior=True,
                    is_active=True
                )
                if self.instance.pk:
                    senior_exists = senior_exists.exclude(pk=self.instance.pk)
                if senior_exists.exists():
                    raise forms.ValidationError(
                        _("There is already a senior housemaster for this academic year.")
                    )

        return cleaned_data
