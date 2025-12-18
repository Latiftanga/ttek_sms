from django import forms
from .models import SchoolSettings

class SchoolSettingsForm(forms.ModelForm):
    class Meta:
        model = SchoolSettings
        fields = ['display_name', 'motto', 'primary_color', 'logo']
        
        widgets = {
            'display_name': forms.TextInput(attrs={
                'class': 'input input-md w-full', # daisyUI input class
                'placeholder': 'Start typing...'  # Placeholder is required for float effect
            }),
            'motto': forms.TextInput(attrs={
                'class': 'input input-md w-full',
                'placeholder': 'Excellence...'
            }),
            'primary_color': forms.TextInput(attrs={
                'type': 'color',
                'class': 'input input-bordered p-1 h-12 w-24 cursor-pointer',
            }),
        }