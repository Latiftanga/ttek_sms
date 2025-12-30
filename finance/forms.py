from django import forms
from .models import (
    FeeType, FeeStructure, Scholarship, StudentScholarship,
    Invoice, Payment, PaymentGatewayConfig
)
from students.models import Student
from academics.models import Class
from core.models import AcademicYear, Term


class FeeTypeForm(forms.ModelForm):
    """Form for creating/editing fee types."""

    class Meta:
        model = FeeType
        fields = [
            'name', 'code', 'category', 'description',
            'is_recurring', 'is_mandatory', 'is_active',
            'applies_to_boarding', 'applies_to_day'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'e.g., Tuition Fee'
            }),
            'code': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'e.g., TUI001'
            }),
            'category': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Description of this fee type'
            }),
            'is_recurring': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'is_mandatory': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'applies_to_boarding': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'applies_to_day': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
        }


class FeeStructureForm(forms.ModelForm):
    """Form for creating/editing fee structures."""

    class Meta:
        model = FeeStructure
        fields = [
            'fee_type', 'class_assigned', 'level_type', 'programme',
            'academic_year', 'term', 'amount', 'due_date', 'is_active'
        ]
        widgets = {
            'fee_type': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'class_assigned': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'level_type': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'programme': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'academic_year': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'term': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'due_date': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['class_assigned'].queryset = Class.objects.filter(is_active=True)
        self.fields['class_assigned'].required = False
        self.fields['programme'].required = False
        self.fields['term'].required = False


class ScholarshipForm(forms.ModelForm):
    """Form for creating/editing scholarships."""

    class Meta:
        model = Scholarship
        fields = [
            'name', 'description', 'discount_type', 'discount_value',
            'applies_to_fee_types', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'e.g., Staff Child Scholarship'
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3
            }),
            'discount_type': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'discount_value': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'applies_to_fee_types': forms.CheckboxSelectMultiple(attrs={
                'class': 'checkbox checkbox-primary'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'checkbox checkbox-primary'
            }),
        }


class StudentScholarshipForm(forms.ModelForm):
    """Form for assigning scholarships to students."""

    class Meta:
        model = StudentScholarship
        fields = ['student', 'academic_year', 'reason', 'start_date', 'end_date']
        widgets = {
            'student': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'academic_year': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3,
                'placeholder': 'Reason for awarding this scholarship'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'date'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = Student.objects.filter(status='active').order_by('last_name', 'first_name')
        self.fields['end_date'].required = False


class InvoiceGenerateForm(forms.Form):
    """Form for generating invoices."""

    class_assigned = forms.ModelChoiceField(
        queryset=Class.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        }),
        label='Class'
    )
    student = forms.ModelChoiceField(
        queryset=Student.objects.filter(status='active'),
        required=False,
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        }),
        label='Or select individual student'
    )
    term = forms.ModelChoiceField(
        queryset=Term.objects.all(),
        widget=forms.Select(attrs={
            'class': 'select select-bordered w-full'
        })
    )
    due_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'class': 'input input-bordered w-full',
            'type': 'date'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        class_assigned = cleaned_data.get('class_assigned')
        student = cleaned_data.get('student')

        if not class_assigned and not student:
            raise forms.ValidationError('Please select either a class or a student.')

        return cleaned_data


class PaymentForm(forms.ModelForm):
    """Form for recording manual payments."""

    class Meta:
        model = Payment
        fields = [
            'invoice', 'amount', 'method',
            'payer_name', 'payer_phone', 'payer_email',
            'reference', 'transaction_date', 'notes'
        ]
        widgets = {
            'invoice': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'amount': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.01'
            }),
            'method': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
            'payer_name': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Name of person making payment'
            }),
            'payer_phone': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'e.g., 0244123456'
            }),
            'payer_email': forms.EmailInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'email@example.com'
            }),
            'reference': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Transaction reference number'
            }),
            'transaction_date': forms.DateTimeInput(attrs={
                'class': 'input input-bordered w-full',
                'type': 'datetime-local'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'textarea textarea-bordered w-full',
                'rows': 3
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show pending invoices
        self.fields['invoice'].queryset = Invoice.objects.filter(
            status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']
        ).select_related('student').order_by('-created_at')


class GatewayConfigForm(forms.ModelForm):
    """Form for configuring payment gateways."""

    class Meta:
        model = PaymentGatewayConfig
        fields = [
            'secret_key', 'public_key', 'webhook_secret',
            'merchant_id', 'encryption_key', 'merchant_account',
            'is_active', 'is_test_mode', 'is_primary',
            'transaction_charge_percentage', 'transaction_charge_fixed',
            'who_bears_charge'
        ]
        widgets = {
            'secret_key': forms.PasswordInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'sk_test_...',
                'autocomplete': 'off'
            }, render_value=True),
            'public_key': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'pk_test_...'
            }),
            'webhook_secret': forms.PasswordInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'whsec_...',
                'autocomplete': 'off'
            }, render_value=True),
            'merchant_id': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Merchant/Client ID'
            }),
            'encryption_key': forms.PasswordInput(attrs={
                'class': 'input input-bordered w-full',
                'autocomplete': 'off'
            }, render_value=True),
            'merchant_account': forms.TextInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': 'Merchant account'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'toggle toggle-primary'
            }),
            'is_test_mode': forms.CheckboxInput(attrs={
                'class': 'toggle toggle-warning'
            }),
            'is_primary': forms.CheckboxInput(attrs={
                'class': 'toggle toggle-success'
            }),
            'transaction_charge_percentage': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'transaction_charge_fixed': forms.NumberInput(attrs={
                'class': 'input input-bordered w-full',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0'
            }),
            'who_bears_charge': forms.Select(attrs={
                'class': 'select select-bordered w-full'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make encrypted fields not required
        self.fields['secret_key'].required = True
        self.fields['public_key'].required = False
        self.fields['webhook_secret'].required = False
        self.fields['merchant_id'].required = False
        self.fields['encryption_key'].required = False
        self.fields['merchant_account'].required = False
