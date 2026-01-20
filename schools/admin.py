import re
from django import forms
from django.contrib import admin
from django_tenants.utils import schema_context, get_public_schema_name
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.conf import settings
from django.http import JsonResponse
from django.urls import path
import logging

from .models import School, Domain, Region, District

User = get_user_model()
logger = logging.getLogger(__name__)


# Region Admin
class DistrictInline(admin.TabularInline):
    model = District
    extra = 1


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')
    inlines = [DistrictInline]


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ('name', 'region')
    list_filter = ('region',)
    search_fields = ('name',)


# School Admin
class SchoolCreationForm(forms.ModelForm):
    """Form for creating schools with admin user."""

    admin_email = forms.EmailField(
        required=False,
        label="Principal Email",
        help_text="Email for the school administrator"
    )
    admin_password = forms.CharField(
        required=False,
        label="Principal Password",
        widget=forms.PasswordInput()
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
        schema_name = self.cleaned_data.get('schema_name')
        if schema_name:
            schema_name = schema_name.lower()
            if not re.match(r'^[a-z][a-z0-9_]*$', schema_name):
                raise ValidationError("Must start with a letter and contain only lowercase letters, numbers, and underscores.")
            if len(schema_name) < 3:
                raise ValidationError("Schema name must be at least 3 characters.")
            reserved = ['public', 'www', 'admin', 'postgres', 'api', 'app']
            if schema_name in reserved:
                raise ValidationError(f"'{schema_name}' is reserved.")
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
    extra = 1
    min_num = 1


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    form = SchoolCreationForm
    inlines = [DomainInline]
    list_display = ('name', 'schema_name', 'education_system', 'created_on')
    list_filter = ('education_system',)
    search_fields = ('name', 'schema_name')

    def get_fieldsets(self, request, obj=None):
        if obj:
            # Editing existing school
            return (
                (None, {'fields': ('name', 'short_name', 'schema_name', 'education_system', 'enabled_levels')}),
                ('Contact', {'fields': ('email', 'phone', 'address', 'city')}),
                ('Location', {'fields': ('location_region', 'location_district')}),
            )
        # Creating new school
        return (
            (None, {'fields': ('name', 'short_name', 'schema_name', 'education_system', 'enabled_levels')}),
            ('Contact', {'fields': ('email', 'phone', 'address', 'city')}),
            ('Location', {'fields': ('location_region', 'location_district')}),
            ('Principal Account', {'fields': ('admin_email', 'admin_password')}),
        )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ('schema_name',)
        return ()

    def save_model(self, request, obj, form, change):
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
                                self.message_user(request, f"School '{obj.name}' created with admin: {admin_email}")
                    except Exception as e:
                        logger.error(f"Failed to create admin for {obj.name}: {e}")
                        self.message_user(request, f"School created, but admin account failed: {e}", level='error')

    def delete_model(self, request, obj):
        with schema_context(get_public_schema_name()):
            super().delete_model(request, obj)

    def get_queryset(self, request):
        with schema_context(get_public_schema_name()):
            return super().get_queryset(request)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('get-districts/<int:region_id>/', self.admin_site.admin_view(self.get_districts_for_region), name='schools_school_get_districts'),
        ]
        return custom_urls + urls

    def get_districts_for_region(self, request, region_id):
        districts = District.objects.filter(region_id=region_id).order_by('name')
        return JsonResponse([{'id': d.id, 'name': d.name} for d in districts], safe=False)
