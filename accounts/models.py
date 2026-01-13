import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_tenant_model


class UserManager(BaseUserManager):
    """
    Custom manager for users in both public and tenant schemas.
    
    - In PUBLIC schema: Creates platform administrators (superusers only)
    - In TENANT schemas: Creates school-specific users (NO superusers allowed)
    """

    def create_user(self, email, password=None, **extra_fields):
        """Base method for creating a generic user."""
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create a Platform Superuser (PUBLIC SCHEMA ONLY).
        
        This method should ONLY be called in the public schema.
        For tenant schemas, use create_school_admin() instead.
        """
        from django.db import connection
        
        # Enforce: Superusers can only be created in public schema
        if connection.schema_name != 'public':
            raise ValueError(_(
                'Superusers can only be created in the public schema (platform level). '
                'For school administrators, use User.objects.create_school_admin() instead.'
            ))
        
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)

    # --- TENANT-SPECIFIC ROLE HELPERS ---

    def create_school_admin(self, email, password=None, **extra_fields):
        """
        Create a School Administrator (Principal/Head).
        This is the highest level of access in a tenant schema.
        """
        from django.db import connection
        
        if connection.schema_name == 'public':
            raise ValueError(_(
                'School admins cannot be created in the public schema. '
                'Use create_superuser() for platform administrators.'
            ))
        
        extra_fields.setdefault('is_school_admin', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', False)  # Never a superuser
        return self.create_user(email, password, **extra_fields)

    def create_teacher(self, email, password=None, **extra_fields):
        """Create a Teacher. Only for tenant schemas."""
        from django.db import connection
        
        if connection.schema_name == 'public':
            raise ValueError(_('Teachers can only be created in tenant schemas.'))
        
        extra_fields.setdefault('is_teacher', True)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self.create_user(email, password, **extra_fields)

    def create_student(self, email, password=None, **extra_fields):
        """Create a Student. Only for tenant schemas."""
        from django.db import connection
        
        if connection.schema_name == 'public':
            raise ValueError(_('Students can only be created in tenant schemas.'))
        
        extra_fields.setdefault('is_student', True)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self.create_user(email, password, **extra_fields)

    def create_parent(self, email, password=None, **extra_fields):
        """Create a Parent. Only for tenant schemas."""
        from django.db import connection
        
        if connection.schema_name == 'public':
            raise ValueError(_('Parents can only be created in tenant schemas.'))
        
        extra_fields.setdefault('is_parent', True)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Universal User model used in both public and tenant schemas.
    
    PUBLIC SCHEMA:
    - Only superusers (platform administrators)
    - Manage all schools via Django admin
    
    TENANT SCHEMAS:
    - NO superusers allowed
    - School admins (highest level), teachers, students, parents
    - Completely isolated per school
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(_('email address'), unique=True)

    # --- SCHOOL ROLES (Tenant-specific only) ---
    is_school_admin = models.BooleanField(
        default=False,
        help_text=_('School administrator (Principal/Head) - highest access in tenant schema')
    )
    is_teacher = models.BooleanField(
        default=False,
        help_text=_('Teacher')
    )
    is_student = models.BooleanField(
        default=False,
        help_text=_('Student')
    )
    is_parent = models.BooleanField(
        default=False,
        help_text=_('Parent/Guardian')
    )

    # --- PASSWORD MANAGEMENT ---
    must_change_password = models.BooleanField(
        default=False,
        help_text=_('User must change password on next login')
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['-date_joined']

    def __str__(self):
        return self.email
    
    @property
    def is_in_public_schema(self):
        """Check if the current user is in the public schema."""
        from django.db import connection
        return connection.schema_name == 'public'
    
    @property
    def is_platform_admin(self):
        """
        Check if user is a platform administrator.
        Only superusers in public schema are platform admins.
        """
        return self.is_in_public_schema and self.is_superuser
    
    @property
    def role_label(self):
        """Helper to get a string representation of the user's role."""
        # Public schema - only platform admins
        if self.is_in_public_schema:
            return "Platform Admin" if self.is_superuser else "Platform User"
        
        # Tenant schema - school roles only
        if self.is_school_admin:
            return "School Admin"
        if self.is_teacher:
            return "Teacher"
        if self.is_student:
            return "Student"
        if self.is_parent:
            return "Parent"
        return "User"
    
    @property
    def is_school_staff(self):
        """Check if user is staff within a school (admin or teacher)."""
        return self.is_school_admin or self.is_teacher
    
    def get_school(self):
        """
        Get the school this user belongs to (if in tenant schema).
        Returns None if in public schema.
        """
        from django.db import connection
        if connection.schema_name == 'public':
            return None
        
        try:
            School = get_tenant_model()
            return School.objects.get(schema_name=connection.schema_name)
        except School.DoesNotExist:
            return None
    
    def has_role(self, role):
        """
        Check if user has a specific role.
        
        Args:
            role (str): One of 'platform_admin', 'school_admin', 'teacher', 'student', 'parent'
        """
        role_map = {
            'platform_admin': self.is_platform_admin,
            'school_admin': self.is_school_admin,
            'teacher': self.is_teacher,
            'student': self.is_student,
            'parent': self.is_parent,
        }
        return role_map.get(role, False)
    
    def save(self, *args, **kwargs):
        """
        Override save to enforce schema-specific rules.
        """
        from django.db import connection
        
        # Prevent superusers from being created in tenant schemas
        if connection.schema_name != 'public' and self.is_superuser:
            raise ValueError(_(
                'Superusers cannot exist in tenant schemas. '
                'Use is_school_admin=True for school administrators.'
            ))
        
        # Prevent school roles in public schema
        if connection.schema_name == 'public':
            if any([self.is_school_admin, self.is_teacher, self.is_student, self.is_parent]):
                raise ValueError(_(
                    'School-specific roles cannot be assigned in the public schema.'
                ))
        
        super().save(*args, **kwargs)
