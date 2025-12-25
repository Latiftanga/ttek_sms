from django import forms
from django.db.models import Q  # Import Q directly here
from .models import Programme, Class, Subject, ClassSubject, AttendanceSession
from students.models import Student


class ProgrammeForm(forms.ModelForm):
    """Form for creating/editing SHS programmes."""
    class Meta:
        model = Programme
        fields = ['name', 'code', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., General Arts'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g., ART'}),
            'description': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional description'}),
        }


class ClassForm(forms.ModelForm):
    """Form for creating/editing classes."""

    LEVEL_NUMBER_CHOICES = [('', 'Select level')] + [(i, str(i)) for i in range(1, 7)]

    level_number = forms.ChoiceField(choices=LEVEL_NUMBER_CHOICES)

    class Meta:
        model = Class
        fields = [
            'level_type', 'level_number', 'section', 
            'programme', 'capacity', 'class_teacher', 'is_active'
        ]
        widgets = {
            'section': forms.TextInput(attrs={'placeholder': 'A, B, C...'}),
            'capacity': forms.NumberInput(attrs={'min': 1, 'max': 100}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['programme'].queryset = Programme.objects.filter(is_active=True)
        self.fields['programme'].required = False
        
        try:
            from teachers.models import Teacher
            self.fields['class_teacher'].queryset = Teacher.objects.filter(status='active').order_by('first_name')
            self.fields['class_teacher'].label = "Form Tutor / Class Teacher"
        except ImportError:
            pass

    def clean_level_number(self):
        value = self.cleaned_data.get('level_number')
        if value:
            return int(value)
        return value

    def clean(self):
        cleaned_data = super().clean()
        level_type = cleaned_data.get('level_type')
        programme = cleaned_data.get('programme')
        level_number = cleaned_data.get('level_number')

        if level_type == Class.LevelType.SHS and not programme:
            self.add_error('programme', 'Programme is required for SHS classes.')

        if level_type != Class.LevelType.SHS and programme:
            cleaned_data['programme'] = None

        if level_type == Class.LevelType.KG and level_number and level_number > 2:
            self.add_error('level_number', 'KG only has levels 1-2.')
        elif level_type == Class.LevelType.PRIMARY and level_number and level_number > 6:
            self.add_error('level_number', 'Primary only has levels 1-6.')
        elif level_type == Class.LevelType.JHS and level_number and level_number > 3:
            self.add_error('level_number', 'JHS only has levels 1-3.')
        elif level_type == Class.LevelType.SHS and level_number and level_number > 3:
            self.add_error('level_number', 'SHS only has levels 1-3.')

        return cleaned_data


class SubjectForm(forms.ModelForm):
    """Form for creating/editing subjects."""
    class Meta:
        model = Subject
        fields = ['name', 'short_name', 'code', 'is_core', 'programmes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Mathematics'}),
            'short_name': forms.TextInput(attrs={'placeholder': 'e.g., MATH'}),
            'code': forms.TextInput(attrs={'placeholder': 'Optional code'}),
            'programmes': forms.CheckboxSelectMultiple(),
        }
        labels = {
            'is_core': 'Core Subject',
            'programmes': 'SHS Programmes (for electives)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['programmes'].queryset = Programme.objects.filter(is_active=True)
        self.fields['programmes'].required = False


class ClassSubjectForm(forms.ModelForm):
    """
    Form to assign a subject and teacher to a class.
    Filters out already assigned subjects.
    """
    class Meta:
        model = ClassSubject
        fields = ['subject', 'teacher', 'periods_per_week']
        widgets = {
            'periods_per_week': forms.NumberInput(attrs={'min': 1, 'max': 10}),
        }

    def __init__(self, *args, class_instance=None, **kwargs):
        super().__init__(*args, **kwargs)

        # 1. Teacher Filter
        try:
            from teachers.models import Teacher
            self.fields['teacher'].queryset = Teacher.objects.filter(status='active').order_by('first_name')
            self.fields['teacher'].label = "Subject Teacher"
        except ImportError:
            pass

        # 2. Subject Filter
        if class_instance:
            query = Q(is_active=True)

            # For SHS classes, filter by programme if applicable
            if class_instance.level_type == Class.LevelType.SHS and class_instance.programme:
                query &= (Q(is_core=True) | Q(programmes=class_instance.programme))

            # Exclude Already Assigned
            existing_subjects = ClassSubject.objects.filter(
                class_assigned=class_instance
            ).values_list('subject_id', flat=True)

            query &= ~Q(id__in=existing_subjects)

            self.fields['subject'].queryset = Subject.objects.filter(query).distinct()
            self.fields['subject'].label = f"Select Subject for {class_instance.name}"


class StudentEnrollmentForm(forms.Form):
    """
    Form to enroll existing students into a class.
    Uses a MultipleChoiceField so you can add multiple students at once.
    """
    students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.none(), # Populated in __init__
        widget=forms.CheckboxSelectMultiple, # Or SelectMultiple
        label="Select Students to Enroll"
    )

    def __init__(self, *args, class_instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        if class_instance:
            # Filter: Active students NOT in ANY class (unassigned students only)
            self.fields['students'].queryset = Student.objects.filter(
                status='active',
                current_class__isnull=True
            ).order_by('first_name', 'last_name')

            self.fields['students'].label = f"Enroll Students into {class_instance.name}"


class AttendanceSessionForm(forms.ModelForm):
    class Meta:
        model = AttendanceSession
        fields = ['date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'input input-bordered'})
        }
