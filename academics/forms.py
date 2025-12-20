from django import forms
from .models import Programme, Class, Subject


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
        fields = ['level_type', 'level_number', 'section', 'programme', 'capacity', 'is_active']
        widgets = {
            'section': forms.TextInput(attrs={'placeholder': 'A, B, C...'}),
            'capacity': forms.NumberInput(attrs={'min': 1, 'max': 100}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['programme'].queryset = Programme.objects.filter(is_active=True)
        self.fields['programme'].required = False

    def clean_level_number(self):
        """Convert level_number to integer."""
        value = self.cleaned_data.get('level_number')
        if value:
            return int(value)
        return value

    def clean(self):
        cleaned_data = super().clean()
        level_type = cleaned_data.get('level_type')
        programme = cleaned_data.get('programme')
        level_number = cleaned_data.get('level_number')

        # SHS requires a programme
        if level_type == Class.LevelType.SHS and not programme:
            self.add_error('programme', 'Programme is required for SHS classes.')

        # Basic levels don't need programme
        if level_type != Class.LevelType.SHS and programme:
            cleaned_data['programme'] = None

        # Validate level numbers
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
        fields = ['name', 'short_name', 'code', 'is_core', 'for_kg', 'for_primary', 'for_jhs', 'for_shs', 'programmes', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g., Mathematics'}),
            'short_name': forms.TextInput(attrs={'placeholder': 'e.g., MATH'}),
            'code': forms.TextInput(attrs={'placeholder': 'Optional code'}),
            'programmes': forms.CheckboxSelectMultiple(),
        }
        labels = {
            'is_core': 'Core Subject',
            'for_kg': 'KG',
            'for_primary': 'Primary',
            'for_jhs': 'JHS',
            'for_shs': 'SHS',
            'programmes': 'SHS Programmes (for electives)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['programmes'].queryset = Programme.objects.filter(is_active=True)
        self.fields['programmes'].required = False
