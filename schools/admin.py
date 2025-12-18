import re
from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django_tenants.utils import schema_context, get_public_schema_name
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings
import logging

from .models import School, Domain

User = get_user_model()
logger = logging.getLogger(__name__)

class SchoolCreationForm(forms.ModelForm):
    """Custom form for creating schools with admin user"""
    
    admin_email = forms.EmailField(
        required=False,
        label="Principal Email",
        help_text="Email address for the school administrator",
        widget=forms.EmailInput(attrs={'placeholder': 'admin@school.com', 'class': 'vTextField'})
    )
    admin_password = forms.CharField(
        required=False,
        label="Principal Password",
        help_text="Initial password",
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••', 'class': 'vTextField'})
    )
    
    class Meta:
        model = School
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['admin_email'].required = True
            self.fields['admin_password'].required = True

    def clean_schema_name(self):
        """
        Validate schema name to prevent 500 errors.
        Must be lowercase, alphanumeric, or underscore. No hyphens.
        """
        schema_name = self.cleaned_data.get('schema_name')
        if schema_name:
            # 1. Force lowercase
            schema_name = schema_name.lower()
            
            # 2. Check strict regex (a-z, 0-9, _)
            if not re.match(r'^[a-z0-9_]+$', schema_name):
                raise ValidationError(
                    "Invalid format. Use only lowercase letters, numbers, and underscores. "
                    "NO hyphens (-) or spaces allowed."
                )
            
            # 3. Check reserved names
            if schema_name in ['public', 'www', 'admin', 'postgres']:
                raise ValidationError(f"The name '{schema_name}' is reserved.")
                
        return schema_name

    def clean_admin_password(self):
        password = self.cleaned_data.get('admin_password')
        if password and not self.instance.pk:
            try:
                validate_password(password)
            except ValidationError as e:
                # In development, we might want to be lenient, but good to keep
                if not settings.DEBUG:
                    raise forms.ValidationError(e.messages)
        return password


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0
    max_num = 1
    min_num = 1
    fields = ('domain', 'is_primary')
    verbose_name = "School Domain"


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    form = SchoolCreationForm
    inlines = [DomainInline]
    
    list_display = ('name', 'schema_name', 'get_domain_link', 'created_on')
    readonly_fields = ('created_on',)
    
    def get_domain_link(self, obj):
        domain = obj.domains.filter(is_primary=True).first() or obj.domains.first()
        if domain:
            # Handle standard ports for local dev vs prod
            port = ":8000" if settings.DEBUG else ""
            protocol = "http" if settings.DEBUG else "https"
            url = f"{protocol}://{domain.domain}{port}"
            
            return format_html(
                '<a href="{}" target="_blank" style="font-weight:bold;">{} ↗</a>',
                url, domain.domain
            )
        return "-"
    get_domain_link.short_description = "Domain"

    def save_model(self, request, obj, form, change):
        """Save school in public schema and create admin user"""
        
        # 1. Force Public Schema for the School Model
        with schema_context(get_public_schema_name()):
            is_new = obj.pk is None
            
            # This triggers the django-tenants 'create_schema' logic
            super().save_model(request, obj, form, change)

            # 2. Create Admin User (Only if new)
            if is_new:
                admin_email = form.cleaned_data.get('admin_email')
                admin_password = form.cleaned_data.get('admin_password')

                if admin_email and admin_password and obj.auto_create_schema:
                    try:
                        # 3. Switch to New Tenant Schema
                        with schema_context(obj.schema_name):
                            if not User.objects.filter(email=admin_email).exists():
                                User.objects.create_school_admin(
                                    email=admin_email,
                                    password=admin_password
                                )
                                self.message_user(request, f"Admin {admin_email} created successfully.")
                    except Exception as e:
                        logger.error(f"Failed to create admin for {obj.name}: {e}")
                        self.message_user(request, f"School created, but Admin User failed: {e}", level='error')
                        
    # Ensure deletions happen in public context
    def delete_model(self, request, obj):
        with schema_context(get_public_schema_name()):
            super().delete_model(request, obj)

    def get_queryset(self, request):
        with schema_context(get_public_schema_name()):
            return super().get_queryset(request)