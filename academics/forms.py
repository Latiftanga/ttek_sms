from django import forms
from django.db.models import Q  # Import Q directly here
from .models import Programme, Class, Subject, ClassSubject, AttendanceSession, Period, TimetableEntry, Classroom
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

    LEVEL_NUMBER_CHOICES = [('', 'Select level')] + [(i, str(i)) for i in range(1, 10)]

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

        # Filter level_type choices based on school's education system setting
        try:
            from core.models import SchoolSettings
            school_settings = SchoolSettings.load()
            allowed_level_types = school_settings.get_allowed_level_types()
            allowed_values = [lt[0] for lt in allowed_level_types]

            # Filter level_type choices to only include allowed types
            original_choices = self.fields['level_type'].choices
            self.fields['level_type'].choices = [
                (value, label) for value, label in original_choices
                if value in allowed_values
            ]
        except Exception:
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

        if level_type == Class.LevelType.CRECHE and level_number and level_number > 2:
            self.add_error('level_number', 'Creche only has levels 1-2.')
        elif level_type == Class.LevelType.NURSERY and level_number and level_number > 2:
            self.add_error('level_number', 'Nursery only has levels 1-2.')
        elif level_type == Class.LevelType.KG and level_number and level_number > 2:
            self.add_error('level_number', 'KG only has levels 1-2.')
        elif level_type == Class.LevelType.BASIC and level_number and level_number > 9:
            self.add_error('level_number', 'Basic only has levels 1-9.')
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


class ClassroomForm(forms.ModelForm):
    """Form for creating/editing classrooms."""
    class Meta:
        model = Classroom
        fields = ['name', 'code', 'capacity', 'room_type', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Room 101, Science Lab 1'}),
            'code': forms.TextInput(attrs={'placeholder': 'e.g., R101, LAB1'}),
            'capacity': forms.NumberInput(attrs={'min': 1, 'max': 500}),
        }
        labels = {
            'room_type': 'Room Type',
        }


class TimetableEntryForm(forms.ModelForm):
    """Form for creating/editing timetable entries with auto ClassSubject creation."""
    from teachers.models import Teacher

    # Replace class_subject with subject and teacher dropdowns
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(),
        required=True,
        label='Subject'
    )
    teacher = forms.ModelChoiceField(
        queryset=Teacher.objects.none(),
        required=True,
        label='Teacher'
    )
    classroom = forms.ModelChoiceField(
        queryset=Classroom.objects.none(),
        required=False,
        label='Classroom'
    )

    class Meta:
        model = TimetableEntry
        fields = ['period', 'weekday', 'is_double', 'classroom']
        labels = {
            'is_double': 'Double Period (spans 2 periods)',
        }

    def __init__(self, *args, class_instance=None, **kwargs):
        from teachers.models import Teacher
        super().__init__(*args, **kwargs)
        self.class_instance = class_instance

        # Filter periods to only active, non-break periods
        self.fields['period'].queryset = Period.objects.filter(
            is_active=True,
            is_break=False
        ).order_by('order')

        # Populate subject choices - all active subjects
        self.fields['subject'].queryset = Subject.objects.filter(
            is_active=True
        ).order_by('name')

        # Populate teacher choices - all active teachers
        self.fields['teacher'].queryset = Teacher.objects.filter(
            status='active'
        ).order_by('first_name', 'last_name')

        # Populate classroom choices - all active classrooms
        self.fields['classroom'].queryset = Classroom.objects.filter(
            is_active=True
        ).order_by('name')

        # For editing, pre-fill subject and teacher from existing entry
        if self.instance and self.instance.pk and self.instance.class_subject:
            self.fields['subject'].initial = self.instance.class_subject.subject
            self.fields['teacher'].initial = self.instance.class_subject.teacher

    def clean(self):
        cleaned_data = super().clean()
        subject = cleaned_data.get('subject')
        teacher = cleaned_data.get('teacher')
        period = cleaned_data.get('period')
        weekday = cleaned_data.get('weekday')
        is_double = cleaned_data.get('is_double', False)
        classroom = cleaned_data.get('classroom')

        if not self.class_instance:
            raise forms.ValidationError('Class instance is required.')

        if not (subject and teacher and period and weekday is not None):
            return cleaned_data

        weekday_int = int(weekday)
        weekday_name = dict(TimetableEntry.Weekday.choices)[weekday_int]
        exclude_pk = self.instance.pk if self.instance.pk else None

        # === BATCH FETCH ALL DATA UPFRONT (single queries) ===

        # 1. Get all periods ordered (for finding next period)
        all_periods = list(Period.objects.filter(
            is_active=True, is_break=False
        ).order_by('order').values('pk', 'order', 'name'))
        period_order_map = {p['pk']: (i, p) for i, p in enumerate(all_periods)}

        # Determine periods to check
        periods_to_check = [period]
        period_pks_to_check = [period.pk]

        if is_double:
            current_idx = period_order_map.get(period.pk, (None, None))[0]
            if current_idx is not None and current_idx + 1 < len(all_periods):
                next_period_data = all_periods[current_idx + 1]
                periods_to_check.append(type('Period', (), {'pk': next_period_data['pk'], 'name': next_period_data['name']})())
                period_pks_to_check.append(next_period_data['pk'])
            else:
                raise forms.ValidationError(
                    f'Cannot create double period: no period exists after {period.name}.'
                )

        # 2. Fetch ALL entries for this class on this weekday (single query)
        class_entries = list(TimetableEntry.objects.filter(
            class_subject__class_assigned=self.class_instance,
            weekday=weekday_int
        ).select_related('class_subject__subject', 'class_subject__teacher', 'period'))
        if exclude_pk:
            class_entries = [e for e in class_entries if e.pk != exclude_pk]

        # Build lookup structures for O(1) access
        entries_by_period = {}  # {period_pk: [entries]}
        entries_by_subject_period = set()  # {(subject_pk, period_pk)}
        double_entries = []  # entries that are double periods

        for entry in class_entries:
            period_pk = entry.period_id
            if period_pk not in entries_by_period:
                entries_by_period[period_pk] = []
            entries_by_period[period_pk].append(entry)
            entries_by_subject_period.add((entry.class_subject.subject_id, period_pk))
            if entry.is_double:
                double_entries.append(entry)

        # 3. Fetch teacher's OTHER class entries on this weekday (single query)
        teacher_other_entries = list(TimetableEntry.objects.filter(
            class_subject__teacher=teacher,
            weekday=weekday_int
        ).exclude(
            class_subject__class_assigned=self.class_instance
        ).select_related('class_subject__class_assigned', 'period'))
        if exclude_pk:
            teacher_other_entries = [e for e in teacher_other_entries if e.pk != exclude_pk]

        teacher_periods = {e.period_id: e for e in teacher_other_entries}

        # 4. Fetch classroom entries for OTHER classes on this weekday (single query)
        classroom_conflicts = {}
        if classroom:
            classroom_entries = list(TimetableEntry.objects.filter(
                classroom=classroom,
                weekday=weekday_int
            ).exclude(
                class_subject__class_assigned=self.class_instance
            ).select_related('class_subject__class_assigned', 'period'))
            if exclude_pk:
                classroom_entries = [e for e in classroom_entries if e.pk != exclude_pk]
            classroom_conflicts = {e.period_id: e for e in classroom_entries}

        # === VALIDATION USING PRE-FETCHED DATA ===

        for check_period in periods_to_check:
            check_period_pk = check_period.pk

            # 1. Check for same subject already in slot
            if (subject.pk, check_period_pk) in entries_by_subject_period:
                raise forms.ValidationError(
                    f'{subject.name} is already scheduled for {check_period.name} on {weekday_name}.'
                )

            # 2. Check for double period continuation conflicts
            if check_period_pk != period.pk:
                # Only check if not adding to a slot that already has entries (combined lesson)
                if period.pk not in entries_by_period:
                    for entry in double_entries:
                        # Find entry's next period
                        entry_idx = period_order_map.get(entry.period_id, (None, None))[0]
                        if entry_idx is not None and entry_idx + 1 < len(all_periods):
                            entry_next_pk = all_periods[entry_idx + 1]['pk']
                            if entry_next_pk == check_period_pk:
                                raise forms.ValidationError(
                                    f'{check_period.name} is occupied by a double period ({entry.class_subject.subject.name}).'
                                )

            # 3. Check teacher conflict (other classes)
            if check_period_pk in teacher_periods:
                conflict = teacher_periods[check_period_pk]
                raise forms.ValidationError(
                    f'{teacher.full_name} is already teaching {conflict.class_subject.class_assigned.name} during {check_period.name}.'
                )

            # 4. Check classroom conflict (other classes)
            if classroom and check_period_pk in classroom_conflicts:
                conflict = classroom_conflicts[check_period_pk]
                raise forms.ValidationError(
                    f'{classroom.name} is already booked for {conflict.class_subject.class_assigned.name} during {check_period.name}.'
                )

        # 5. Check combined lessons constraints (same slot)
        existing_in_slot = entries_by_period.get(period.pk, [])
        if existing_in_slot:
            # Check for same teacher in combined lessons
            for entry in existing_in_slot:
                if entry.class_subject.teacher_id == teacher.pk:
                    raise forms.ValidationError(
                        f'{teacher.full_name} is already teaching {entry.class_subject.subject.name} in this slot. '
                        f'Combined lessons run concurrently, so different teachers are required.'
                    )

            # Check duration mismatch
            existing_is_double = existing_in_slot[0].is_double
            if existing_is_double != is_double:
                if is_double:
                    raise forms.ValidationError(
                        'Cannot add a double period lesson to a slot with single period lessons. '
                        'Combined lessons must have the same duration.'
                    )
                else:
                    raise forms.ValidationError(
                        'Cannot add a single period lesson to a slot with double period lessons. '
                        'Combined lessons must have the same duration.'
                    )

        return cleaned_data

    def save(self, commit=True):
        """Save timetable entry, auto-creating ClassSubject if needed."""
        subject = self.cleaned_data.get('subject')
        teacher = self.cleaned_data.get('teacher')

        # Get or create ClassSubject for this class+subject combination
        class_subject, created = ClassSubject.objects.get_or_create(
            class_assigned=self.class_instance,
            subject=subject,
            defaults={'teacher': teacher}
        )

        # If ClassSubject exists but has a different teacher, update it
        # (This means the admin wants to change who teaches this subject)
        if not created and class_subject.teacher != teacher:
            class_subject.teacher = teacher
            class_subject.save()

        # Set the class_subject on the instance
        self.instance.class_subject = class_subject

        return super().save(commit=commit)
