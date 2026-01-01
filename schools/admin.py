import re
from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from django_tenants.utils import schema_context, get_public_schema_name
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings
import logging

from .models import School, Domain, Region, District

User = get_user_model()
logger = logging.getLogger(__name__)


# =============================================================================
# Region & District Admin
# =============================================================================

class DistrictInline(admin.TabularInline):
    model = District
    extra = 1
    fields = ('name',)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'district_count')
    search_fields = ('name', 'code')
    ordering = ('name',)
    inlines = [DistrictInline]

    def district_count(self, obj):
        return obj.districts.count()
    district_count.short_description = 'Districts'


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ('name', 'region', 'region_code')
    list_filter = ('region',)
    search_fields = ('name', 'region__name')
    ordering = ('region', 'name')

    def region_code(self, obj):
        return obj.region.code
    region_code.short_description = 'Region Code'


# =============================================================================
# School Admin
# =============================================================================

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
        help_text="Initial password (min 8 characters)",
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
            if not re.match(r'^[a-z][a-z0-9_]*$', schema_name):
                raise ValidationError(
                    "Must start with a letter and contain only lowercase letters, numbers, and underscores. "
                    "NO hyphens (-) or spaces allowed."
                )

            # 3. Check minimum length
            if len(schema_name) < 3:
                raise ValidationError("Schema name must be at least 3 characters.")

            # 4. Check reserved names
            reserved = ['public', 'www', 'admin', 'postgres', 'api', 'app', 'mail', 'ftp']
            if schema_name in reserved:
                raise ValidationError(f"The name '{schema_name}' is reserved.")

        return schema_name

    def clean_admin_password(self):
        password = self.cleaned_data.get('admin_password')
        if password and not self.instance.pk:
            try:
                validate_password(password)
            except ValidationError as e:
                if not settings.DEBUG:
                    raise forms.ValidationError(e.messages)
        return password


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0
    max_num = 3
    min_num = 1
    fields = ('domain', 'is_primary')
    verbose_name = "Domain"
    verbose_name_plural = "Domains"


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    form = SchoolCreationForm
    inlines = [DomainInline]

    # List View Configuration
    list_display = (
        'name',
        'schema_name',
        'get_domain_link',
        'city',
        'region',
        'headmaster_name',
        'get_status_badge',
        'created_on'
    )
    list_display_links = ('name',)
    list_filter = ('region', 'created_on')
    search_fields = ('name', 'short_name', 'schema_name', 'city', 'headmaster_name', 'email')
    date_hierarchy = 'created_on'
    ordering = ('-created_on',)

    # Form Configuration
    fieldsets = (
        ('School Identity', {
            'fields': ('name', 'short_name', 'schema_name'),
            'description': 'Basic identification for the school tenant.'
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'address', 'digital_address', 'city', 'region'),
            'classes': ('collapse',),
        }),
        ('Administration', {
            'fields': ('headmaster_title', 'headmaster_name'),
            'classes': ('collapse',),
        }),
        ('Principal Account', {
            'fields': ('admin_email', 'admin_password'),
            'description': 'Create login credentials for the school principal. Only shown when creating a new school.',
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('created_on', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    readonly_fields = ('created_on', 'updated_at')

    # Custom Methods for List Display
    def get_domain_link(self, obj):
        domain = obj.domains.filter(is_primary=True).first() or obj.domains.first()
        if domain:
            port = ":8000" if settings.DEBUG else ""
            protocol = "http" if settings.DEBUG else "https"
            url = f"{protocol}://{domain.domain}{port}"

            return format_html(
                '<a href="{}" target="_blank" title="Open school portal">'
                '<strong>{}</strong> <span style="font-size:10px;">↗</span></a>',
                url, domain.domain
            )
        return format_html('<span style="color:#999;">No domain</span>')
    get_domain_link.short_description = "Portal URL"
    get_domain_link.admin_order_field = 'domains__domain'

    def get_status_badge(self, obj):
        # Check if schema exists (school is active)
        return format_html(
            '<span style="background:#22c55e;color:white;padding:2px 8px;'
            'border-radius:10px;font-size:11px;">Active</span>'
        )
    get_status_badge.short_description = "Status"

    # Form Visibility
    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj:  # Editing existing school - hide principal account section
            fieldsets = [fs for fs in fieldsets if fs[0] != 'Principal Account']
        return fieldsets

    # Save Logic
    def save_model(self, request, obj, form, change):
        """Save school in public schema and create admin user"""

        with schema_context(get_public_schema_name()):
            is_new = obj.pk is None

            super().save_model(request, obj, form, change)

            if is_new:
                admin_email = form.cleaned_data.get('admin_email')
                admin_password = form.cleaned_data.get('admin_password')

                if admin_email and admin_password and obj.auto_create_schema:
                    try:
                        with schema_context(obj.schema_name):
                            if not User.objects.filter(email=admin_email).exists():
                                User.objects.create_school_admin(
                                    email=admin_email,
                                    password=admin_password
                                )
                                self.message_user(
                                    request,
                                    f"✓ School '{obj.name}' created with admin account: {admin_email}"
                                )
                    except Exception as e:
                        logger.error(f"Failed to create admin for {obj.name}: {e}")
                        self.message_user(
                            request,
                            f"⚠ School created, but admin account failed: {e}",
                            level='error'
                        )

    def delete_model(self, request, obj):
        with schema_context(get_public_schema_name()):
            super().delete_model(request, obj)

    def get_queryset(self, request):
        with schema_context(get_public_schema_name()):
            return super().get_queryset(request).prefetch_related('domains')


# =============================================================================
# Admin Site Customization
# =============================================================================

admin.site.site_header = "TTEK SMS Platform Admin"
admin.site.site_title = "TTEK SMS Admin"
admin.site.index_title = "School Management Dashboard"
