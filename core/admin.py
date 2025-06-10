from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import School, Teacher, Student

User = get_user_model()


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'code', 'school_type', 'region',
        'get_domain_display', 'student_count', 'teacher_count', 'is_active'
    ]
    list_filter = ['school_type', 'ownership', 'region', 'is_active']
    search_fields = ['name', 'code', 'email', 'phone_primary']
    readonly_fields = ['slug', 'created_at',
                       'updated_at', 'get_login_url_display']

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'code', 'school_type', 'ownership')
        }),
        ('Multi-Tenant Setup', {
            'fields': ('domain', 'subdomain', 'get_login_url_display'),
            'description': 'Configure how users will access this school. Provide either a custom domain OR subdomain.'
        }),
        ('Registration Details', {
            'fields': ('emis_code', 'ges_number', 'establishment_date')
        }),
        ('Location', {
            'fields': ('region', 'district', 'town', 'digital_address', 'physical_address')
        }),
        ('Contact Information', {
            'fields': ('headmaster_name', 'email', 'phone_primary', 'phone_secondary', 'website')
        }),
        ('School Identity', {
            'fields': ('logo', 'motto', 'has_boarding')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_domain_display(self, obj):
        if obj.domain:
            return format_html('<span style="color: green;">🌐 {}</span>', obj.domain)
        elif obj.subdomain:
            return format_html('<span style="color: blue;">📱 {}.ttek.com</span>', obj.subdomain)
        return '-'
    get_domain_display.short_description = 'Access Domain'

    def get_login_url_display(self, obj):
        if obj.get_tenant_domain:
            url = f"https://{obj.get_tenant_domain}/login/"
            return format_html('<a href="{}" target="_blank">{}</a>', url, url)
        return 'Not configured'
    get_login_url_display.short_description = 'Login URL'

    def student_count(self, obj):
        count = obj.students.filter(is_active=True).count()
        url = reverse('admin:core_student_changelist') + \
            f'?school__id__exact={obj.id}'
        return format_html('<a href="{}">{} students</a>', url, count)
    student_count.short_description = 'Students'

    def teacher_count(self, obj):
        count = obj.teachers.filter(is_active=True).count()
        url = reverse('admin:core_teacher_changelist') + \
            f'?school__id__exact={obj.id}'
        return format_html('<a href="{}">{} teachers</a>', url, count)
    teacher_count.short_description = 'Teachers'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        'username', 'get_full_name_display', 'email', 'user_type_display',
        'get_school_display', 'is_active', 'last_login', 'date_joined',
    ]
    list_filter = ['is_teacher', 'is_student',
                   'is_admin', 'is_active', ]
    search_fields = ['username', 'email']

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('email',)}),
        ('User Type', {
            'fields': ('is_teacher', 'is_student', 'is_admin'),
            'description': 'Select the user type. School association is managed through Teacher/Student profiles.'
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', ),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'is_teacher', 'is_student', 'is_admin'),
        }),
    )

    def user_type_display(self, obj):
        types = []
        if obj.is_superuser:
            types.append('<span style="color: red;">🔴 Superuser</span>')
        if obj.is_admin:
            types.append('<span style="color: orange;">🟠 Admin</span>')
        if obj.is_teacher:
            types.append('<span style="color: blue;">🔵 Teacher</span>')
        if obj.is_student:
            types.append('<span style="color: green;">🟢 Student</span>')
        return mark_safe(' | '.join(types)) if types else '-'
    user_type_display.short_description = 'User Type'

    def get_full_name_display(self, obj):
        profile = obj.get_profile()
        if profile:
            return profile.get_full_name()
        return obj.username
    get_full_name_display.short_description = 'Full Name'

    def get_school_display(self, obj):
        school = obj.get_school()
        if school:
            url = reverse('admin:core_school_change', args=[school.id])
            return format_html('<a href="{}">{}</a>', url, school.name)
        return '-'
    get_school_display.short_description = 'School'


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = [
        'get_full_name', 'teacher_id', 'school', 'has_user_account', 'user_account_status', 'is_active'
    ]
    list_filter = ['school', 'is_active', ]
    search_fields = ['first_name', 'last_name', 'teacher_id', 'qualification']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'middle_name', 'last_name', 'gender', 'date_of_birth')
        }),
        ('School Detail', {
            'fields': ('school',)
        }),
        ('Contact Information', {
            'fields': ('phone', 'email', 'address', 'ghana_card_number')
        }),
        ('User Account', {
            'fields': ('user',),
            'description': 'Link to user account for system access'
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_subjects_display(self, obj):
        if obj.subjects:
            subjects = obj.subjects[:3]  # Show first 3 subjects
            display = ', '.join([s.title() for s in subjects])
            if len(obj.subjects) > 3:
                display += f' (+{len(obj.subjects) - 3} more)'
            return display
        return '-'
    get_subjects_display.short_description = 'Subjects'

    # FIXED: Use boolean return for boolean field
    def has_user_account(self, obj):
        return obj.user is not None
    has_user_account.short_description = 'Has Account'
    has_user_account.boolean = True  # This works with boolean returns

    # SEPARATE: Use HTML display for status details
    def user_account_status(self, obj):
        if obj.user:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ {}</span>',
                obj.user.username
            )
        return format_html('<span style="color: red;">✗ No Account</span>')
    user_account_status.short_description = 'Account Status'

    # Admin actions
    actions = ['create_user_accounts', 'link_existing_users']

    def create_user_accounts(self, request, queryset):
        created_count = 0
        messages = []

        for teacher in queryset.filter(user__isnull=True):
            try:
                user, password = teacher.create_user_account()
                created_count += 1
                messages.append(
                    f'✓ {teacher.get_full_name()}: {user.username} / {password}')
            except Exception as e:
                messages.append(f'✗ {teacher.get_full_name()}: {str(e)}')

        if created_count:
            self.message_user(
                request, f'Successfully created {created_count} user accounts:')
            for msg in messages:
                self.message_user(request, msg)
        else:
            self.message_user(
                request, 'No user accounts were created. Check for errors above.', level='warning')
    create_user_accounts.short_description = "Create user accounts for selected teachers"

    def link_existing_users(self, request, queryset):
        linked_count = 0
        for teacher in queryset.filter(user__isnull=True):
            try:
                # Try to find a user with matching teacher_id
                user = User.objects.get(
                    username=teacher.teacher_id, is_teacher=True)
                if not hasattr(user, 'teacher_profile'):
                    teacher.user = user
                    teacher.save()
                    linked_count += 1
                    self.message_user(
                        request, f'✓ Linked {teacher.get_full_name()} to user {user.username}')
            except User.DoesNotExist:
                pass
            except User.MultipleObjectsReturned:
                self.message_user(
                    request, f'⚠ Multiple users found for {teacher.teacher_id}', level='warning')

        if linked_count:
            self.message_user(
                request, f'Successfully linked {linked_count} teachers to existing users')
        else:
            self.message_user(
                request, 'No teachers were linked. No matching users found.', level='warning')
    link_existing_users.short_description = "Link to existing users"


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = [
        'get_full_name', 'student_id', 'school', 'class_level',
        'year_admitted', 'has_user_account', 'user_account_status', 'is_active'
    ]
    list_filter = ['school', 'class_level', 'year_admitted', 'is_active']
    search_fields = ['first_name', 'last_name', 'student_id']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'middle_name', 'last_name', 'gender', 'date_of_birth')
        }),
        ('Academic Information', {
            'fields': ('school', 'student_id', 'class_level', 'year_admitted')
        }),
        ('Contact Information', {
            'fields': ('phone', 'email', 'address', 'ghana_card_number')
        }),
        ('User Account', {
            'fields': ('user',),
            'description': 'Link to user account for system access'
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    # FIXED: Use boolean return for boolean field
    def has_user_account(self, obj):
        return obj.user is not None
    has_user_account.short_description = 'Has Account'
    has_user_account.boolean = True

    # SEPARATE: Use HTML display for status details
    def user_account_status(self, obj):
        if obj.user:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ {}</span>',
                obj.user.username
            )
        return format_html('<span style="color: red;">✗ No Account</span>')
    user_account_status.short_description = 'Account Status'

    # Admin actions
    actions = ['create_user_accounts', 'link_existing_users']

    def create_user_accounts(self, request, queryset):
        created_count = 0
        messages = []

        for student in queryset.filter(user__isnull=True):
            try:
                user, password = student.create_user_account()
                created_count += 1
                messages.append(
                    f'✓ {student.get_full_name()}: {user.username} / {password}')
            except Exception as e:
                messages.append(f'✗ {student.get_full_name()}: {str(e)}')

        if created_count:
            self.message_user(
                request, f'Successfully created {created_count} user accounts:')
            for msg in messages:
                self.message_user(request, msg)
        else:
            self.message_user(
                request, 'No user accounts were created. Check for errors above.', level='warning')
    create_user_accounts.short_description = "Create user accounts for selected students"

    def link_existing_users(self, request, queryset):
        linked_count = 0
        for student in queryset.filter(user__isnull=True):
            try:
                # Try to find a user with matching student_id
                user = User.objects.get(
                    username=student.student_id, is_student=True)
                if not hasattr(user, 'student_profile'):
                    student.user = user
                    student.save()
                    linked_count += 1
                    self.message_user(
                        request, f'✓ Linked {student.get_full_name()} to user {user.username}')
            except User.DoesNotExist:
                pass
            except User.MultipleObjectsReturned:
                self.message_user(
                    request, f'⚠ Multiple users found for {student.student_id}', level='warning')

        if linked_count:
            self.message_user(
                request, f'Successfully linked {linked_count} students to existing users')
        else:
            self.message_user(
                request, 'No students were linked. No matching users found.', level='warning')
    link_existing_users.short_description = "Link to existing users"


# Customize admin site
admin.site.site_header = "TTEK School Management System"
admin.site.site_title = "TTEK SMS Admin"
admin.site.index_title = "Welcome to TTEK School Management System"
