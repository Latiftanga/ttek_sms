from django import forms
from django.db.models import Q  # Import Q directly here
from .models import Programme, Class, Subject, ClassSubject, AttendanceSession, Period, TimetableEntry
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


class PeriodForm(forms.ModelForm):
    """Form for creating/editing school periods."""
    class Meta:
        model = Period
        fields = ['name', 'start_time', 'end_time', 'order', 'is_break', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Period 1, Break, Assembly'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'order': forms.NumberInput(attrs={'min': 0, 'max': 20}),
        }
        labels = {
            'is_break': 'Break Period (not for classes)',
            'order': 'Display Order',
        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if start_time and end_time and start_time >= end_time:
            raise forms.ValidationError('End time must be after start time.')

        return cleaned_data


class TimetableEntryForm(forms.ModelForm):
    """Form for creating/editing timetable entries."""
    class Meta:
        model = TimetableEntry
        fields = ['class_subject', 'period', 'weekday', 'is_double']
        labels = {
            'is_double': 'Double Period (spans 2 periods)',
        }

    def __init__(self, *args, class_instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_instance = class_instance

        # Filter periods to only active, non-break periods
        self.fields['period'].queryset = Period.objects.filter(
            is_active=True,
            is_break=False
        ).order_by('order')

        # Filter class subjects if class is provided
        if class_instance:
            self.fields['class_subject'].queryset = ClassSubject.objects.filter(
                class_assigned=class_instance
            ).select_related('subject', 'teacher')
            self.fields['class_subject'].label_from_instance = lambda obj: f"{obj.subject.name} ({obj.teacher.full_name if obj.teacher else 'No teacher'})"

    def clean(self):
        cleaned_data = super().clean()
        class_subject = cleaned_data.get('class_subject')
        period = cleaned_data.get('period')
        weekday = cleaned_data.get('weekday')
        is_double = cleaned_data.get('is_double', False)

        if class_subject and period and weekday:
            # Get list of periods to check (1 or 2 depending on double)
            periods_to_check = [period]

            if is_double:
                # Find the next period by order
                next_period = Period.objects.filter(
                    is_active=True,
                    is_break=False,
                    order__gt=period.order
                ).order_by('order').first()

                if not next_period:
                    raise forms.ValidationError(
                        f'Cannot create double period: no period exists after {period.name}.'
                    )
                periods_to_check.append(next_period)

            # Check for duplicate entries for all periods
            for check_period in periods_to_check:
                existing = TimetableEntry.objects.filter(
                    class_subject__class_assigned=class_subject.class_assigned,
                    period=check_period,
                    weekday=weekday
                )
                if self.instance.pk:
                    existing = existing.exclude(pk=self.instance.pk)

                if existing.exists():
                    raise forms.ValidationError(
                        f'This class already has a subject scheduled for {check_period.name} on {dict(TimetableEntry.Weekday.choices)[weekday]}.'
                    )

                # Also check if there's a double period that occupies this slot
                double_occupying = TimetableEntry.objects.filter(
                    class_subject__class_assigned=class_subject.class_assigned,
                    weekday=weekday,
                    is_double=True
                ).exclude(period=check_period)

                if self.instance.pk:
                    double_occupying = double_occupying.exclude(pk=self.instance.pk)

                for entry in double_occupying:
                    # Check if entry's next period is the one we're checking
                    entry_next = Period.objects.filter(
                        is_active=True,
                        is_break=False,
                        order__gt=entry.period.order
                    ).order_by('order').first()
                    if entry_next and entry_next.pk == check_period.pk:
                        raise forms.ValidationError(
                            f'{check_period.name} is occupied by a double period ({entry.class_subject.subject.name}).'
                        )

            # Check for teacher conflicts for all periods
            if class_subject.teacher:
                for check_period in periods_to_check:
                    teacher_conflict = TimetableEntry.objects.filter(
                        class_subject__teacher=class_subject.teacher,
                        period=check_period,
                        weekday=weekday
                    ).exclude(class_subject__class_assigned=class_subject.class_assigned)

                    if self.instance.pk:
                        teacher_conflict = teacher_conflict.exclude(pk=self.instance.pk)

                    if teacher_conflict.exists():
                        conflicting = teacher_conflict.first()
                        raise forms.ValidationError(
                            f'{class_subject.teacher.full_name} is already teaching {conflicting.class_subject.class_assigned.name} during {check_period.name}.'
                        )

        return cleaned_data
