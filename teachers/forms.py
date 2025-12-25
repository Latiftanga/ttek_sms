from django import forms
from .models import Teacher

class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        # We can list fields explicitly to control order
        fields = [
            'title', 'first_name', 'middle_name', 'last_name', 'gender',
            'date_of_birth', 'staff_id', 'status', 
            'subject_specialization', 'employment_date',
            'phone_number', 'email', 'address', 'photo', 'nationality'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'employment_date': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }