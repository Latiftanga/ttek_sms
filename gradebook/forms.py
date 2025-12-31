from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

from .models import (
    GradingSystem, GradeScale, AssessmentCategory,
    Assignment, Score, SubjectTermGrade, TermReport
)
from . import config


class GradingSystemForm(forms.ModelForm):
    """Form for creating/editing grading systems."""

    class Meta:
        model = GradingSystem
        fields = ['name', 'level', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
            'level': forms.Select(attrs={'class': 'select select-bordered w-full'}),
            'description': forms.Textarea(attrs={'class': 'textarea textarea-bordered w-full', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary'}),
        }


class GradeScaleForm(forms.ModelForm):
    """Form for creating/editing grade scales."""

    class Meta:
        model = GradeScale
        fields = [
            'grade_label', 'min_percentage', 'max_percentage',
            'aggregate_points', 'interpretation', 'is_pass', 'is_credit', 'order'
        ]
        widgets = {
            'grade_label': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'e.g., A1'}),
            'min_percentage': forms.NumberInput(attrs={'class': 'input input-bordered w-full', 'step': '0.01'}),
            'max_percentage': forms.NumberInput(attrs={'class': 'input input-bordered w-full', 'step': '0.01'}),
            'aggregate_points': forms.NumberInput(attrs={'class': 'input input-bordered w-full', 'min': '1', 'max': '9'}),
            'interpretation': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'e.g., Excellent'}),
            'is_pass': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary'}),
            'is_credit': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary'}),
            'order': forms.NumberInput(attrs={'class': 'input input-bordered w-full', 'min': '0'}),
        }

    def __init__(self, *args, grading_system=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.grading_system = grading_system
        # Set on instance for model validation in clean()
        if grading_system:
            self.instance.grading_system = grading_system

    def clean(self):
        cleaned_data = super().clean()
        min_pct = cleaned_data.get('min_percentage')
        max_pct = cleaned_data.get('max_percentage')
        aggregate_points = cleaned_data.get('aggregate_points')

        if min_pct is not None and max_pct is not None:
            if min_pct > max_pct:
                raise forms.ValidationError('Minimum percentage cannot be greater than maximum percentage.')
            if min_pct < 0 or max_pct > 100:
                raise forms.ValidationError('Percentages must be between 0 and 100.')

        # Validate aggregate_points uniqueness within grading system
        if aggregate_points is not None and self.grading_system:
            existing = GradeScale.objects.filter(
                grading_system=self.grading_system,
                aggregate_points=aggregate_points
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(
                    f'Aggregate points {aggregate_points} is already used by grade "{existing.first().grade_label}".'
                )

        return cleaned_data


class AssessmentCategoryForm(forms.ModelForm):
    """Form for creating/editing assessment categories."""

    class Meta:
        model = AssessmentCategory
        fields = ['name', 'short_name', 'percentage', 'order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'e.g., Class Score'}),
            'short_name': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'e.g., CA', 'maxlength': '10'}),
            'percentage': forms.NumberInput(attrs={'class': 'input input-bordered w-full', 'min': '0', 'max': '100'}),
            'order': forms.NumberInput(attrs={'class': 'input input-bordered w-full', 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'checkbox checkbox-primary'}),
        }

    def clean_percentage(self):
        percentage = self.cleaned_data.get('percentage')
        if percentage is not None:
            if percentage < 0 or percentage > 100:
                raise forms.ValidationError('Percentage must be between 0 and 100.')
        return percentage

    def clean_short_name(self):
        short_name = self.cleaned_data.get('short_name', '')
        return short_name.upper()


class AssignmentForm(forms.ModelForm):
    """Form for creating/editing assignments."""

    class Meta:
        model = Assignment
        fields = ['assessment_category', 'name', 'points_possible', 'date']
        widgets = {
            'assessment_category': forms.Select(attrs={'class': 'select select-bordered w-full'}),
            'name': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'e.g., Quiz 1'}),
            'points_possible': forms.NumberInput(attrs={'class': 'input input-bordered w-full', 'min': '1', 'value': '100'}),
            'date': forms.DateInput(attrs={'class': 'input input-bordered w-full', 'type': 'date'}),
        }

    def clean_points_possible(self):
        points = self.cleaned_data.get('points_possible')
        if points is not None and points < 1:
            raise forms.ValidationError('Points possible must be at least 1.')
        return points


class ScoreForm(forms.Form):
    """Form for entering individual scores."""
    student_id = forms.IntegerField(widget=forms.HiddenInput())
    assignment_id = forms.UUIDField(widget=forms.HiddenInput())
    points = forms.DecimalField(
        required=False,
        min_value=Decimal('0'),
        max_digits=6,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'input input-sm input-bordered w-16 text-center',
            'min': '0',
            'step': '0.01'
        })
    )

    def __init__(self, *args, max_points=Decimal('100'), **kwargs):
        super().__init__(*args, **kwargs)
        self.max_points = Decimal(str(max_points))
        self.fields['points'].validators.append(MaxValueValidator(self.max_points))
        self.fields['points'].widget.attrs['max'] = str(self.max_points)

    def clean_points(self):
        points = self.cleaned_data.get('points')
        if points is not None and points > self.max_points:
            raise forms.ValidationError(f'Maximum points is {self.max_points}.')
        return points


class TermReportRemarkForm(forms.ModelForm):
    """Form for editing term report remarks."""

    class Meta:
        model = TermReport
        fields = ['class_teacher_remark', 'head_teacher_remark']
        widgets = {
            'class_teacher_remark': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Class teacher remark...'
            }),
            'head_teacher_remark': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Head teacher remark...'
            }),
        }


class SubjectGradeRemarkForm(forms.ModelForm):
    """Form for editing subject-level teacher remarks."""

    class Meta:
        model = SubjectTermGrade
        fields = ['teacher_remark']
        widgets = {
            'teacher_remark': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Subject teacher remark...',
                'maxlength': '200'
            }),
        }


class BulkScoreImportForm(forms.Form):
    """Form for bulk importing scores from CSV/Excel."""

    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'file-input file-input-bordered w-full',
            'accept': '.csv,.xlsx,.xls'
        })
    )
    class_id = forms.IntegerField(widget=forms.HiddenInput())
    subject_id = forms.IntegerField(widget=forms.HiddenInput())

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if uploaded_file:
            # Validate file extension
            ext = uploaded_file.name.split('.')[-1].lower()
            if ext not in ['csv', 'xlsx', 'xls']:
                raise forms.ValidationError('Only CSV and Excel files are allowed.')

            # Validate file size
            if uploaded_file.size > config.MAX_FILE_SIZE:
                max_mb = config.MAX_FILE_SIZE / (1024 * 1024)
                raise forms.ValidationError(f'File size must be under {max_mb:.0f} MB.')

        return uploaded_file
