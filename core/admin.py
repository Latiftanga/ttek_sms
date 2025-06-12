from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Tenant, User, Student, Teacher


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin for custom User model"""
    list_display = ['username', 'school', 'email',
                    'get_role_display', 'is_active', 'date_joined']
    list_filter = ['school', 'is_active', 'is_staff',
                   'is_teacher', 'is_student', 'is_admin', 'date_joined']
    search_fields = ['username', 'email', 'school__name']
    ordering = ['school', 'username']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('email',)}),
        ('School Assignment', {'fields': ('school',)}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'is_teacher', 'is_student', 'is_admin'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'school', 'is_teacher', 'is_student', 'is_admin'),
        }),
    )

    def get_queryset(self, request):
        """Filter users based on permissions"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Non-superusers can only see users from their school
        elif hasattr(request.user, 'school') and request.user.school:
            return qs.filter(school=request.user.school)
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Customize foreign key fields"""
        if db_field.name == "school":
            if request.user.is_superuser:
                kwargs["queryset"] = Tenant.objects.filter(
                    is_active=True).order_by('name')
            elif hasattr(request.user, 'school') and request.user.school:
                kwargs["queryset"] = Tenant.objects.filter(
                    id=request.user.school.id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Override save to handle school assignment"""
        # If user is not superuser, set school to current user's school
        if not request.user.is_superuser and hasattr(request.user, 'school'):
            obj.school = request.user.school
        super().save_model(request, obj, form, change)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """Admin for School/Tenant model"""
    list_display = [
        'name', 'code', 'school_type', 'region', 'domain_info',
        'is_active', 'student_count', 'teacher_count', 'view_logo'
    ]
    list_filter = ['school_type', 'ownership',
                   'region', 'is_active', 'has_boarding']
    search_fields = ['name', 'code', 'domain', 'subdomain', 'emis_code']
    prepopulated_fields = {'slug': ('name',)}

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'code', 'school_type', 'ownership', 'is_active')
        }),
        ('Domain Configuration', {
            'fields': ('domain', 'subdomain'),
            'description': 'Configure either custom domain OR subdomain (not both)'
        }),
        ('Registration Details', {
            'fields': ('emis_code', 'ges_number', 'establishment_date'),
            'classes': ('collapse',)
        }),
        ('Location', {
            'fields': ('region', 'district', 'town', 'digital_address', 'physical_address')
        }),
        ('Contact Information', {
            'fields': ('headmaster_name', 'email', 'phone_primary', 'phone_secondary', 'website')
        }),
        ('School Details', {
            'fields': ('logo', 'motto', 'has_boarding'),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = ['registration_date']

    def domain_info(self, obj):
        """Display domain information"""
        if obj.domain:
            return format_html('<strong>{}</strong>', obj.domain)
        elif obj.subdomain:
            return format_html('{}.ttek.com', obj.subdomain)
        return 'No domain configured'
    domain_info.short_description = 'Domain'

    def view_logo(self, obj):
        """Display logo thumbnail"""
        if obj.logo:
            return format_html(
                '<img src="{}" width="40" height="40" style="border-radius: 4px;" />',
                obj.logo.url
            )
        return "No Logo"
    view_logo.short_description = "Logo"

    def student_count(self, obj):
        """Display student count with link"""
        count = obj.get_student_count()
        url = reverse('admin:core_student_changelist') + \
            f'?school__id__exact={obj.id}'
        return format_html('<a href="{}">{} students</a>', url, count)
    student_count.short_description = "Students"

    def teacher_count(self, obj):
        """Display teacher count with link"""
        count = obj.get_teacher_count()
        url = reverse('admin:core_teacher_changelist') + \
            f'?school__id__exact={obj.id}'
        return format_html('<a href="{}">{} teachers</a>', url, count)
    teacher_count.short_description = "Teachers"

    def save_model(self, request, obj, form, change):
        """Override save to handle domain/subdomain logic"""
        super().save_model(request, obj, form, change)

        # Display success message with domain info
        if obj.domain:
            domain_msg = f"Custom domain: {obj.domain}"
        else:
            domain_msg = f"Subdomain: {obj.subdomain}.ttek.com"

        self.message_user(request, f"School saved successfully. {domain_msg}")


class SchoolFilterMixin:
    """Mixin to add school filtering to admin"""

    def get_queryset(self, request):
        """Filter queryset based on school"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # Add school-based filtering for non-superusers later
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Customize foreign key fields"""
        if db_field.name == "school":
            kwargs["queryset"] = Tenant.objects.filter(
                is_active=True).order_by('name')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Student)
class StudentAdmin(SchoolFilterMixin, admin.ModelAdmin):
    """Admin for Student model"""
    list_display = [
        'student_id', 'first_name', 'last_name', 'gender',
        'year_admitted', 'school', 'is_active', 'has_account'
    ]
    list_filter = ['school', 'gender', 'year_admitted', 'is_active']
    search_fields = [
        'student_id', 'first_name', 'last_name', 'email',
        'ghana_card_number', 'school__name'
    ]
    readonly_fields = ['student_id', 'created_at', 'updated_at']

    fieldsets = (
        ('Student Information', {
            'fields': ('school', 'student_id', 'year_admitted', 'is_active')
        }),
        ('Personal Details', {
            'fields': (
                'first_name', 'middle_name', 'last_name', 'gender',
                'date_of_birth', 'ghana_card_number'
            )
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'address')
        }),
        ('System Information', {
            'fields': ('user', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_account(self, obj):
        """Check if student has user account"""
        if obj.user:
            return format_html('<span style="color: green;">✓ Yes</span>')
        return format_html('<span style="color: red;">✗ No</span>')
    has_account.short_description = "Has Account"

    def save_model(self, request, obj, form, change):
        """Override save to display student ID"""
        super().save_model(request, obj, form, change)
        if not change:  # New student
            self.message_user(
                request,
                f"Student created successfully with ID: {obj.student_id}"
            )


@admin.register(Teacher)
class TeacherAdmin(SchoolFilterMixin, admin.ModelAdmin):
    """Admin for Teacher model"""
    list_display = [
        'teacher_id', 'first_name', 'last_name', 'gender',
        'school', 'is_active', 'has_account'
    ]
    list_filter = ['school', 'gender', 'is_active']
    search_fields = [
        'teacher_id', 'first_name', 'last_name', 'email',
        'ghana_card_number', 'school__name'
    ]
    readonly_fields = ['teacher_id', 'created_at', 'updated_at']

    fieldsets = (
        ('Teacher Information', {
            'fields': ('school', 'teacher_id', 'is_active')
        }),
        ('Personal Details', {
            'fields': (
                'first_name', 'middle_name', 'last_name', 'gender',
                'date_of_birth', 'ghana_card_number'
            )
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'address')
        }),
        ('System Information', {
            'fields': ('user', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_account(self, obj):
        """Check if teacher has user account"""
        if obj.user:
            return format_html('<span style="color: green;">✓ Yes</span>')
        return format_html('<span style="color: red;">✗ No</span>')
    has_account.short_description = "Has Account"

    def save_model(self, request, obj, form, change):
        """Override save to display teacher ID"""
        super().save_model(request, obj, form, change)
        if not change:  # New teacher
            self.message_user(
                request,
                f"Teacher created successfully with ID: {obj.teacher_id}"
            )


# Customize admin site header
admin.site.site_header = "School Management System"
admin.site.site_title = "School Admin"
admin.site.index_title = "Welcome to School Management System"
